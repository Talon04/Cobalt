import asyncio

from app.core.builder import build_first_message_summary_prompt, build_full_prompt
from app.db.db_manager import (
    claim_job_async,
    get_pending_jobs_async,
    update_job_status_async,
    get_prompt_async,
    get_chat_async,
    is_first_user_prompt_async,
    save_chat_message_async,
    update_chat_title_async,
)
from app.core.logging import logger

from app.services.llm import ollama_service


job_streams: dict[int, asyncio.Queue] = {}
model_pull_task: asyncio.Task | None = None
model_pull_status: dict = {
    "running": False,
    "model": None,
    "error": None,
    "done": False,
}


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


async def run_model_pull_job(model_name: str) -> None:
    global model_pull_status
    model_pull_status = {
        "running": True,
        "model": model_name,
        "error": None,
        "done": False,
    }
    try:
        await ollama_service.pull_model(model_name)
        model_pull_status = {
            "running": False,
            "model": model_name,
            "error": None,
            "done": True,
        }
    except Exception:
        logger.exception("Error pulling model %s", model_name)
        model_pull_status = {
            "running": False,
            "model": model_name,
            "error": "Model pull failed. Check server logs for details.",
            "done": False,
        }


def start_model_pull(model_name: str) -> dict:
    global model_pull_task, model_pull_status
    if model_pull_task and not model_pull_task.done():
        return {
            "started": False,
            "model": model_pull_status.get("model"),
            "status": "already-running",
        }
    model_pull_status = {
        "running": False,
        "model": model_name,
        "error": None,
        "done": False,
    }
    model_pull_task = asyncio.create_task(run_model_pull_job(model_name))
    return {"started": True, "model": model_name, "status": "running"}


def get_model_pull_status() -> dict:
    return model_pull_status


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
            return (
                message.get("content") or chunk.get("content") or chunk.get("raw") or ""
            )
        return chunk.get("content") or chunk.get("raw") or ""
    else:
        return str(chunk)


def _normalize_summary_title(raw_title: str) -> str:
    cleaned = " ".join(raw_title.split())
    if not cleaned:
        return ""
    words = cleaned.split(" ")
    return " ".join(words[:4])[:255]


async def run_chat_job(job_id):
    try:
        claimed = await claim_job_async(job_id)
        if not claimed:
            logger.info("Skipping job %s because it is no longer queued", job_id)
            return

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
            await update_job_status_async(
                job_id, "failed", error="No chat found for prompt"
            )
            await _emit(job_id, {"type": "error", "error": "No chat found for prompt"})
            await _finish_stream(job_id)
            return

        logger.info(f"Building prompt for job {job_id}, chat {chat.id}")
        full_prompt = await build_full_prompt(chat_id=chat.id)
        should_summarize_title = (
            chat.title == "New chat"
            and prompt.role == "user"
            and bool(prompt.content)
            and await is_first_user_prompt_async(chat.id, prompt.id)
        )
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
                logger.debug(
                    f"Emitting chunk {chunk_count} ({len(content)} chars) for job {job_id}"
                )
                await _emit(job_id, {"type": "chunk", "content": content})

        logger.info(
            f"Streaming complete for job {job_id}, {chunk_count} chunks, {len(accumulated)} total chars"
        )
        await save_chat_message_async(chat.id, "assistant", accumulated, response_model)

        if should_summarize_title:
            try:
                summary_prompt = build_first_message_summary_prompt(prompt.content)
                summary = await ollama_service.summarize_first_message(summary_prompt)
                summary_title = _normalize_summary_title(summary)
                if summary_title:
                    await update_chat_title_async(chat.id, summary_title)
            except Exception:
                logger.exception(
                    "Failed to summarize first message for chat title (chat=%s)",
                    chat.id,
                )

        await update_job_status_async(job_id, "done")
        await _finish_stream(job_id)
        logger.info(f"Job {job_id} completed successfully")
    except Exception as e:
        logger.exception(f"Error processing job {job_id}")
        await update_job_status_async(job_id, "failed", error=str(e))
        await _emit(job_id, {"type": "error", "error": str(e)})
        await _finish_stream(job_id)
