from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.logging import logger
from app.workers.scheduler import scheduler_service
from app.services.db import init_db
from app.core import worker as core_worker
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Cobalt")
    await init_db()
    if scheduler_service:
        scheduler_service.start()
    # start worker loop as a background task
    app.state.worker_task = asyncio.create_task(core_worker.worker_loop())
    yield
    logger.info("Shutting down Cobalt")
    if scheduler_service:
        scheduler_service.shutdown()
    # stop worker loop
    try:
        app.state.worker_task.cancel()
        await app.state.worker_task
    except Exception:
        pass
