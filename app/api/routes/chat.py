
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.db import ChatThread
from app.db.models.schemas import (
    ChatMessageSchema,
    ChatThreadCreateSchema,
    ChatThreadSchema,
    ChatMessageOutSchema,
    ModelPullRequestSchema,
    ModelSelectRequestSchema,
)
from app.services.llm import STANDARD_MODELS, ollama_service
from app.services.db import get_db
from app.core import worker as worker_service

router = APIRouter()


@router.post("")
async def chat(message: ChatMessageSchema, db: AsyncSession = Depends(get_db)):
    # Delegate to the streaming endpoint which handles SSE and persistence
    return await send_message_stream(message, db)
    
@router.get("/chats", response_model=list[ChatThreadSchema])
async def list_chats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatThread).order_by(ChatThread.updated_at.desc(), ChatThread.id.desc()))
    chats = result.scalars().all()
    return chats


@router.post("/chats", response_model=ChatThreadSchema)
async def create_chat(payload: ChatThreadCreateSchema | None = None, db: AsyncSession = Depends(get_db)):
    chat = ChatThread(title=(payload.title if payload and payload.title else "New chat"))
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("/chats/{chat_id}/messages", response_model=list[ChatMessageOutSchema])
async def get_chat_messages(chat_id: int, db: AsyncSession = Depends(get_db)):
    
    from app.db.db_manager import get_chat_messages
    messages = await get_chat_messages(chat_id)
    return messages


@router.post("/send")
async def send_message(prompt: ChatMessageSchema):
    from app.db.db_manager import save_prompt, new_background_job

    prompt_id = save_prompt(prompt)

    job_id = new_background_job(
        prompt_id=prompt_id,
    )

    return {"job_id": job_id}

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    from app.db.db_manager import get_job as db_get_job
    job = db_get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "prompt_id": job.prompt_id,
        "error": job.error,
    }



@router.post("/send-stream")
async def send_message_stream(msg: ChatMessageSchema, db: AsyncSession = Depends(get_db)):
    chat = await db.get(ChatThread, msg.chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    from app.db.db_manager import save_prompt, new_background_job
    from app.core.logging import logger

    prompt_id = save_prompt({
        "chat_id": msg.chat_id,
        "role": msg.role,
        "content": msg.content,
        "model": None,
    })

    job_id = new_background_job(prompt_id=prompt_id)
    logger.info(f"Created job {job_id} for prompt {prompt_id}")
    
    stream_queue = worker_service.register_job_stream(job_id)
    logger.info(f"Registered job stream for job {job_id}")

    # Schedule worker task and keep a reference to prevent GC
    task = asyncio.create_task(worker_service.run_chat_job(job_id))
    logger.info(f"Created worker task for job {job_id}")
    
    if not hasattr(worker_service, '_active_tasks'):
        worker_service._active_tasks = set()
    worker_service._active_tasks.add(task)
    task.add_done_callback(lambda t: worker_service._active_tasks.discard(t))
    logger.info(f"Task {job_id} added to active tasks set")

    async def event_generator():
        timeout = 300  # 5 minute timeout
        start_time = asyncio.get_event_loop().time()
        event_count = 0
        
        logger.info(f"Event generator started for job {job_id}")
        
        # Yield an immediate ACK to establish connection and give worker a chance to start
        yield f"data: {json.dumps({'type': 'connected', 'job_id': job_id})}\n\n"
        await asyncio.sleep(0.1)  # Give worker a brief moment to start
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                # Stream timeout, send disconnect signal
                logger.warning(f"Stream timeout for job {job_id} after {elapsed}s")
                yield f"data: {json.dumps({'type': 'stream_done'})}\n\n"
                break
                
            try:
                event = await asyncio.wait_for(stream_queue.get(), timeout=10.0)
                event_count += 1
                logger.debug(f"Event {event_count} for job {job_id}: {event.get('type')}")
            except asyncio.TimeoutError:
                # Timeout waiting for event; yield keepalive and retry
                logger.debug(f"No event for job {job_id} for 10s, sending keepalive")
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                continue
                
            event_type = event.get("type")

            if event_type == "meta" and event.get("model"):
                yield f"data: {json.dumps({'type': 'meta', 'model': event['model']})}\n\n"
                continue

            if event_type == "chunk" and event.get("content"):
                yield f"data: {json.dumps({'content': event['content']})}\n\n"
                continue

            if event_type == "error":
                yield f"data: {json.dumps({'error': event.get('error', 'UNKNOWN_ERROR')})}\n\n"
                continue

            if event_type == "done":
                logger.info(f"Stream done for job {job_id} after {event_count} events")
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/pull-model")
async def pull_model(payload: ModelPullRequestSchema | None = None):
    """Pull a model from Ollama."""
    requested_model = payload.model if payload else None
    data = await ollama_service.pull_model(requested_model)
    return {
        "ok": True,
        "model": data.get("model", ollama_service.model),
        "status": data.get("status", "unknown"),
        "started": data.get("started", False),
    }


@router.get("/pull-model/status")
async def pull_model_status():
    """Return the current model pull status."""
    return ollama_service.pull_state()


@router.get("/models")
async def list_models():
    installed_models = await ollama_service.list_installed_models()
    selectable_models: list[str] = []
    for model in installed_models + STANDARD_MODELS + [ollama_service.model]:
        if model and model not in selectable_models:
            selectable_models.append(model)
    return {
        "current_model": ollama_service.model,
        "installed_models": installed_models,
        "standard_models": STANDARD_MODELS,
        "models": selectable_models,
    }


@router.post("/models/select")
async def select_model(payload: ModelSelectRequestSchema):
    try:
        selected = ollama_service.set_model(payload.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "current_model": selected}
