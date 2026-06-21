import logging
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("cobalt")

class ModelNotFoundError(Exception):
    def __init__(self, model: str):
        self.model = model
        super().__init__(f"Model '{model}' not found")