from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from datetime import datetime

class Base(DeclarativeBase):
    pass

class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), default="New chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ChatPrompt", back_populates="chat", cascade="all, delete-orphan")

class ChatPrompt(Base):
    __tablename__ = "chat_prompts"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50))  # user, assistant
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    model=Column(String(100), nullable=True)  # Optional: to store which model generated the response

    chat = relationship("ChatThread", back_populates="messages")

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    task_type = Column(String(100))
    cron_expression = Column(String(100))
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(Integer, primary_key=True)
    job_id = Column(String(255), unique=True)
    status = Column(String(50))  # running, done, failed
    prompt_id = Column(Integer, ForeignKey("chat_prompts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error = Column(Text, nullable=True)

    #chat = relationship("ChatThread")
