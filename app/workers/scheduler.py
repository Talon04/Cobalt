from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import settings
from app.core.logging import logger

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler() if settings.scheduler_enabled else None
    
    def start(self):
        if self.scheduler:
            self.scheduler.start()
            logger.info("Scheduler started")
    
    def shutdown(self):
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Scheduler shutdown")
    
    def add_job(self, func, trigger, **kwargs):
        if self.scheduler:
            return self.scheduler.add_job(func, trigger, **kwargs)

scheduler_service = SchedulerService()
