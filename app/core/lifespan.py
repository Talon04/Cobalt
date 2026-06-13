from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.logging import logger
from app.workers.scheduler import scheduler_service
from app.services.db import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Cobalt")
    await init_db()
    if scheduler_service:
        scheduler_service.start()
    yield
    logger.info("Shutting down Cobalt")
    if scheduler_service:
        scheduler_service.shutdown()
