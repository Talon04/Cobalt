# Base worker class
class BaseWorker:
    async def run(self):
        raise NotImplementedError
