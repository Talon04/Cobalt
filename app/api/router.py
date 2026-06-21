from fastapi import APIRouter
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.tools import router as tools_router

router = APIRouter()
router.include_router(chat_router, prefix="/chat")
router.include_router(health_router, prefix="/api")
router.include_router(tools_router, prefix="/api")

