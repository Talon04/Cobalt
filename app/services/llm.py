import asyncio

import httpx
from app.core.config import settings
from app.core.logging import logger
import json

class OllamaService:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=300.0)
        self.pull_task: asyncio.Task | None = None
        self.pull_status = {
            "running": False,
            "model": None,
            "error": None,
            "done": False,
        }
    
    async def chat(self, messages: list[dict], stream: bool = False):
        """Send message to Ollama"""
        try:
            resp = await self.client.post(
                "/api/chat",
                json={"model": self.model, "messages": messages, "stream": stream}
            )
            return resp
        except Exception as e:
            logger.error(f"Ollama error: {e} for: {self.model}")
            raise

    async def stream_chat(self, messages: list[dict]):
        """Stream chat response from Ollama as an async generator yielding parsed JSON lines."""
        try:
            async with self.client.stream(
                "POST",
                "/api/chat",
                json={"model": self.model, "messages": messages, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    # Ollama streams JSON lines; try to parse
                    try:
                        chunk = json.loads(line)
                    except Exception:
                        # if not JSON, forward raw line
                        chunk = {"raw": line}
                    yield chunk
        except Exception as e:
            logger.error(f"Ollama error: {e} for: {self.model}")
            raise

    async def pull_model(self, model_name: str | None = None):
        """Pull a model into Ollama."""
        target_model = model_name or self.model
        self.pull_status = {
            "running": True,
            "model": target_model,
            "error": None,
            "done": False,
        }

        async def _run_pull() -> None:
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=None) as client:
                    async with client.stream(
                        "POST",
                        "/api/pull",
                        json={"name": target_model, "stream": True},
                    ) as response:
                        response.raise_for_status()
                        async for _ in response.aiter_lines():
                            pass
                self.pull_status.update({"running": False, "done": True, "error": None})
            except Exception as e:
                logger.error(f"Ollama pull error: {e}")
                self.pull_status.update({"running": False, "done": False, "error": str(e)})

        if self.pull_task and not self.pull_task.done():
            return {"started": False, "model": target_model, "status": "already-running"}

        self.pull_task = asyncio.create_task(_run_pull())
        return {"started": True, "model": target_model, "status": "running"}

    def pull_state(self) -> dict:
        return self.pull_status
    
    async def close(self):
        await self.client.aclose()

ollama_service = OllamaService()
