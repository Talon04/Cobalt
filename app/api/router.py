from fastapi import APIRouter

router = APIRouter()

# Routes registered here
from app.api.routes import health, chat, tools

router.include_router(health.router, tags=["health"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
