from pydantic import BaseModel
from pydantic import ConfigDict
from datetime import datetime


class ChatThreadCreateSchema(BaseModel):
    title: str | None = None


class ChatThreadUpdateSchema(BaseModel):
    title: str


class ChatThreadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime | None = None


class ChatMessageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: str
    content: str
    created_at: datetime


class ChatMessageSchema(BaseModel):
    chat_id: int
    role: str
    content: str


class ChatResponseSchema(BaseModel):
    role: str = "assistant"
    content: str
    chat_id: int | None = None
    model: str | None = None


class ModelSelectRequestSchema(BaseModel):
    model: str


class ModelPullRequestSchema(BaseModel):
    model: str | None = None


class OllamaSettingsSchema(BaseModel):
    keep_alive: str | None = None


class ScheduledTaskSchema(BaseModel):
    name: str
    task_type: str
    cron_expression: str
    enabled: bool = True
