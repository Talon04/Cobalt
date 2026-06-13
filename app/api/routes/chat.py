from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db import ChatThread, ChatMessage
from app.models.schemas import (
    ChatMessageSchema,
    ChatResponseSchema,
    ChatThreadCreateSchema,
    ChatThreadSchema,
    ChatMessageOutSchema,
)
from app.services.llm import ollama_service
from app.services.db import get_db

router = APIRouter()


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
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.chat_id == chat_id).order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    return result.scalars().all()

@router.post("/send", response_model=ChatResponseSchema)
async def send_message(msg: ChatMessageSchema, db: AsyncSession = Depends(get_db)):
    """Send message to LLM"""
    chat = await db.get(ChatThread, msg.chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    user_message = ChatMessage(chat_id=msg.chat_id, role=msg.role, content=msg.content, model=None)
    db.add(user_message)
    await db.commit()

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == msg.chat_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    history = [{"role": message.role, "content": message.content} for message in result.scalars().all()]
    
    response = await ollama_service.chat(history, stream=False)
    data = response.json()

    if response.status_code != 200:
        error_msg = data.get("error", "Unknown error from Ollama")
        return ChatResponseSchema(content=f"Error: {error_msg}. Model may need to be pulled.", chat_id=msg.chat_id)

    response_model = data.get("model", ollama_service.model)
    assistant_content = data.get("message", {}).get("content", "No response")
    assistant_message = ChatMessage(chat_id=msg.chat_id, role="assistant", content=assistant_content, model=response_model)
    if chat.title == "New chat" and msg.role == "user":
        chat.title = msg.content[:40] or "New chat"
    db.add(assistant_message)
    await db.commit()

    return ChatResponseSchema(content=assistant_content, chat_id=msg.chat_id)



@router.post("/send-stream")
async def send_message_stream(msg: ChatMessageSchema, db: AsyncSession = Depends(get_db)):
    """Stream LLM response back to the client as server-sent events.

    The endpoint streams incremental chunks from Ollama and, when complete,
    persists the assistant message to the DB.
    """
    chat = await db.get(ChatThread, msg.chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    user_message = ChatMessage(chat_id=msg.chat_id, role=msg.role, content=msg.content)
    db.add(user_message)
    await db.commit()

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == msg.chat_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    history = [{"role": message.role, "content": message.content} for message in result.scalars().all()]

    async def event_generator():
        accumulated = ""
        response_model = None
        sent_model = False
        try:
            async for chunk in ollama_service.stream_chat(history):
                # try to extract incremental content; Ollama may provide nested message fields
                content_piece = None
                if isinstance(chunk, dict):
                    response_model = response_model or chunk.get("model")
                    # common shape: {"message": {"content": "..."}, ...}
                    message = chunk.get("message") or {}
                    # some chunks include partial content under message.content
                    if isinstance(message, dict):
                        content_piece = message.get("content")
                    # fallback to thinking or raw
                    if not content_piece:
                        content_piece = chunk.get("thinking") or chunk.get("content") or chunk.get("raw")
                else:
                    content_piece = str(chunk)

                if response_model and not sent_model:
                    sent_model = True
                    yield f"data: {json.dumps({'type': 'meta', 'model': response_model})}\n\n"

                if content_piece:
                    accumulated += content_piece
                    payload = {"content": content_piece}
                    yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            err = {"error": str(e)}
            yield f"data: {json.dumps(err)}\n\n"
        # after streaming finishes, persist the full assistant message
        try:
            assistant_message = ChatMessage(chat_id=msg.chat_id, role="assistant", content=accumulated)
            if chat.title == "New chat" and msg.role == "user":
                chat.title = msg.content[:40] or "New chat"
            db.add(assistant_message)
            await db.commit()
        except Exception:
            # DB errors shouldn't break the stream; ignore here
            pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/pull-model")
async def pull_model():
    """Pull the configured Ollama model."""
    data = await ollama_service.pull_model()
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
