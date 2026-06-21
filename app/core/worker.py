import asyncio

from app.core.builder import build_full_prompt
from app.db.db_manager import (
    get_pending_jobs_async,
    update_job_status_async,
    get_prompt_async,
    get_chat_async,
    save_chat_message_async,
)
from app.core.logging import logger

from app.services.llm import ollama_service


job_streams: dict[int, asyncio.Queue] = {}


def register_job_stream(job_id: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    job_streams[job_id] = queue
    return queue


def _get_job_queue(job_id: int) -> asyncio.Queue | None:
    return job_streams.get(job_id)


async def _emit(job_id: int, payload: dict) -> None:
    queue = _get_job_queue(job_id)
    if queue:
        await queue.put(payload)


async def _finish_stream(job_id: int) -> None:
    queue = _get_job_queue(job_id)
    if queue:
        await queue.put({"type": "done"})
    job_streams.pop(job_id, None)


async def worker_loop():
    while True:
        try:
            jobs = await get_pending_jobs_async(5)
            for job in jobs:
                # schedule each job concurrently but limit concurrency if needed
                await run_chat_job(job.id)
        except Exception:
            logger.exception("Worker loop error")

        await asyncio.sleep(5)


def extract(chunk):
    """Extract content from an Ollama stream chunk."""
    if isinstance(chunk, dict):
        message = chunk.get("message") or {}
        if isinstance(message, dict):
            return message.get("content") or chunk.get("content") or chunk.get("raw") or ""
        return chunk.get("content") or chunk.get("raw") or ""
    else:
        return str(chunk)


async def run_chat_job(job_id):
    try:
        logger.info(f"Starting job {job_id}")
        
        prompt = await get_prompt_async(job_id)
        if not prompt:
            logger.error(f"No prompt found for job {job_id}")
            await update_job_status_async(job_id, "failed", error="No prompt found")
            await _emit(job_id, {"type": "error", "error": "No prompt found"})
            await _finish_stream(job_id)
            return

        chat = await get_chat_async(job_id)
        if not chat:
            logger.error(f"No chat found for job {job_id}")
            await update_job_status_async(job_id, "failed", error="No chat found for prompt")
            await _emit(job_id, {"type": "error", "error": "No chat found for prompt"})
            await _finish_stream(job_id)
            return

        logger.info(f"Building prompt for job {job_id}, chat {chat.id}")
        full_prompt = await build_full_prompt(chat_id=chat.id)
        accumulated = ""
        response_model = None
        sent_model = False
        chunk_count = 0

        logger.info(f"Starting streaming for job {job_id}")
        async for chunk in ollama_service.stream_chat(full_prompt):
            chunk_count += 1
            content = extract(chunk)
            if isinstance(chunk, dict):
                response_model = response_model or chunk.get("model")
            if response_model and not sent_model:
                sent_model = True
                logger.info(f"Emitting model {response_model} for job {job_id}")
                await _emit(job_id, {"type": "meta", "model": response_model})
            if content:
                accumulated += content
                logger.debug(f"Emitting chunk {chunk_count} ({len(content)} chars) for job {job_id}")
                await _emit(job_id, {"type": "chunk", "content": content})

        logger.info(f"Streaming complete for job {job_id}, {chunk_count} chunks, {len(accumulated)} total chars")
        await save_chat_message_async(chat.id, "assistant", accumulated, response_model)
        await update_job_status_async(job_id, "done")
        await _finish_stream(job_id)
        logger.info(f"Job {job_id} completed successfully")
    except Exception as e:
        logger.exception(f"Error processing job {job_id}")
        await update_job_status_async(job_id, "failed", error=str(e))
        await _emit(job_id, {"type": "error", "error": str(e)})
        await _finish_stream(job_id)
