from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.models.db import Base, ChatPrompt, BackgroundJob, ChatThread
from app.services.db import SessionLocal as AsyncSessionLocal


# Sync engine for one-off operations in route handlers.
# Docker uses an asyncpg URL, so build a matching sync URL for sync sessions.
sync_database_url = settings.database_url.replace("+asyncpg", "+psycopg2")
engine = create_engine(sync_database_url, echo=settings.sqlalchemy_echo)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Create tables"""
    Base.metadata.create_all(bind=engine)

def get_db_session():
    return SessionLocal()

# Async functions for worker loop
async def get_pending_jobs_async(last_n):
    """Fetch pending jobs from the database (async)"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BackgroundJob)
            .where(BackgroundJob.status == "running")
            .order_by(BackgroundJob.created_at.asc())
            .limit(last_n)
        )
        jobs = result.scalars().all()
        return jobs

async def update_job_status_async(job_id, status, error=None):
    """Update the status of a background job (async)"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BackgroundJob).where(BackgroundJob.id == job_id)
        )
        job = result.scalars().first()
        if job:
            job.status = status
            if error:
                job.error = error
            await session.commit()

async def get_prompt_async(background_job_id):
    """Fetch the chat prompt associated with a background job (async)"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BackgroundJob).where(BackgroundJob.id == background_job_id)
        )
        job = result.scalars().first()
        if not job:
            return None
        
        result = await session.execute(
            select(ChatPrompt).where(ChatPrompt.id == job.prompt_id)
        )
        prompt = result.scalars().first()
        return prompt

async def get_chat_async(background_job_id):
    """Fetch the chat thread associated with a background job (async)"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BackgroundJob).where(BackgroundJob.id == background_job_id)
        )
        job = result.scalars().first()
        if not job:
            return None

        result = await session.execute(
            select(ChatPrompt).where(ChatPrompt.id == job.prompt_id)
        )
        prompt = result.scalars().first()
        if not prompt:
            return None

        result = await session.execute(
            select(ChatThread).where(ChatThread.id == prompt.chat_id)
        )
        chat = result.scalars().first()
        return chat

def save_prompt(prompt):
    """Save a chat message to the database."""
    if isinstance(prompt, dict):
        prompt_data = prompt
    else:
        prompt_data = {
            "chat_id": getattr(prompt, "chat_id", None),
            "role": getattr(prompt, "role", "user"),
            "content": getattr(prompt, "content", None),
            "model": getattr(prompt, "model", None),
        }

    prompt = ChatPrompt(
        chat_id=prompt_data["chat_id"],
        role=prompt_data.get("role", "user"),
        content=prompt_data["content"],
        model=prompt_data.get("model"),
    )
    session = get_db_session()
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    session.close()
    return prompt.id
async def get_chat_messages(chat_id):
    """Fetch all messages for a given chat thread"""

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ChatPrompt)
            .where(ChatPrompt.chat_id == chat_id)
            .order_by(ChatPrompt.created_at.asc(), ChatPrompt.id.asc())
        )
        return result.scalars().all()

async def save_chat_message_async(chat_id, role, content, model=None):
    """Persist a chat message using the async DB session."""

    async with AsyncSessionLocal() as session:
        message = ChatPrompt(
            chat_id=chat_id,
            role=role,
            content=content,
            model=model,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message


async def is_first_user_prompt_async(chat_id: int, prompt_id: int) -> bool:
    """Return True when the given prompt is the first user message in the chat."""

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count(ChatPrompt.id)).where(
                ChatPrompt.chat_id == chat_id,
                ChatPrompt.role == "user",
                ChatPrompt.id <= prompt_id,
            )
        )
        user_count = result.scalar_one()
        return user_count == 1


async def update_chat_title_async(chat_id: int, title: str) -> None:
    """Update a chat title with a normalized value."""

    normalized = " ".join(title.split())[:255]
    if not normalized:
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ChatThread).where(ChatThread.id == chat_id))
        chat = result.scalars().first()
        if not chat:
            return
        chat.title = normalized
        await session.commit()


def new_background_job(prompt_id):
    """Create a new background job entry in the database"""
    session = get_db_session()
    job = BackgroundJob(prompt_id=prompt_id, status="running")
    session.add(job)
    session.commit()
    session.refresh(job)
    session.close()
    return job.id
def get_pending_jobs(last_n):
    """Fetch pending jobs from the database"""
    session = get_db_session()
    jobs = session.query(BackgroundJob).filter(BackgroundJob.status == "running").order_by(BackgroundJob.created_at.asc()).limit(last_n).all()
    session.close()
    return jobs
def update_job_status(job_id, status, error=None):
    """Update the status of a background job"""
    from app.db.models import BackgroundJob
    session = get_db_session()
    job = session.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
    if job:
        job.status = status
        if error:
            job.error = error
        session.commit()
    session.close()
def get_job(job_id):
    """Fetch a background job by ID"""
    session = get_db_session()
    job = session.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
    session.close()
    return job
def get_chat(background_job_id):
    """Fetch the chat thread associated with a background job"""
    session = get_db_session()
    job = session.query(BackgroundJob).filter(BackgroundJob.id == background_job_id).first()
    if not job:
        session.close()
        return None

    prompt = session.query(ChatPrompt).filter(ChatPrompt.id == job.prompt_id).first()
    if not prompt:
        session.close()
        return None

    chat = session.query(ChatThread).filter(ChatThread.id == prompt.chat_id).first()
    session.close()
    return chat

def get_prompt(background_job_id):
    """Fetch the chat prompt associated with a background job"""
    session = get_db_session()
    job = session.query(BackgroundJob).filter(BackgroundJob.id == background_job_id).first()
    if not job:
        session.close()
        return None
    prompt = session.query(ChatPrompt).filter(ChatPrompt.id == job.prompt_id).first()
    session.close()
    return prompt
def get_chat(prompt_id):
    """Fetch the chat thread associated with a chat prompt"""
    session = get_db_session()
    prompt = session.query(ChatPrompt).filter(ChatPrompt.id == prompt_id).first()
    if not prompt:
        session.close()
        return None
    chat = session.query(ChatThread).filter(ChatThread.id == prompt.chat_id).first()
    session.close()
    return chat

class DBError(Exception):
    pass