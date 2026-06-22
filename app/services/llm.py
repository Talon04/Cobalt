import asyncio
import json
from pathlib import Path
from threading import Lock

import httpx
from app.core.config import settings
from app.core.logging import logger, ModelNotFoundError


STANDARD_MODELS = [
    "qwen3:14b",
    "llama3.1:8b",
    "mistral:7b",
    "phi4",
]


class OllamaService:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model_store_path = Path(settings.ollama_model_store_path)
        self.model_config_lock = Lock()
        self.model = self._load_model()
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=300.0)
        self.pull_task: asyncio.Task | None = None
        self.pull_status = {
            "running": False,
            "model": None,
            "error": None,
            "done": False,
        }

    def _load_model(self) -> str:
        with self.model_config_lock:
            if not self.model_store_path.exists():
                return settings.ollama_model
            try:
                with self.model_store_path.open(encoding="utf-8") as handle:
                    stored = json.load(handle)
                if isinstance(stored, dict) and isinstance(stored.get("current_model"), str):
                    model = stored["current_model"].strip()
                    if model:
                        return model
            except Exception as e:
                logger.warning(f"Could not load model config from {self.model_store_path}: {e}")
        return settings.ollama_model

    def _save_model(self) -> None:
        with self.model_config_lock:
            try:
                self.model_store_path.parent.mkdir(parents=True, exist_ok=True)
                with self.model_store_path.open("w", encoding="utf-8") as handle:
                    json.dump({"current_model": self.model}, handle)
            except Exception as e:
                logger.error(f"Could not persist model config to {self.model_store_path}: {e}")

    def set_model(self, model: str) -> str:
        selected = model.strip()
        if not selected:
            raise ValueError("Model cannot be empty")
        self.model = selected
        self._save_model()
        return self.model

    async def list_installed_models(self) -> list[str]:
        try:
            resp = await self.client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            names: list[str] = []
            for model in models:
                if isinstance(model, dict) and isinstance(model.get("name"), str):
                    names.append(model["name"])
            return names
        except Exception as e:
            logger.warning(f"Could not fetch installed models from Ollama: {e}")
            return []

    async def chat(self, messages: list[dict], stream: bool = False):
        """Send message to Ollama"""
        try:
            resp = await self.client.post(
                "/api/chat", json={"model": self.model, "messages": messages, "stream": stream}
            )
            return resp
        except Exception as e:
            logger.error(f"Ollama error: {e} for: {self.model}")
            raise

    async def stream_chat(self, messages: list[dict]):
        try:
            async with self.client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "think": False,
                },
            ) as response:

                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        yield json.loads(line)
                    except Exception:
                        yield {"raw": line}

        except httpx.HTTPStatusError as e:
            logger.error(
                "Ollama returned %s for model %s",
                e.response.status_code,
                self.model,
            )

            raise ModelNotFoundError(self.model) \
                if e.response.status_code == 404 \
                else e

        except Exception:
            logger.exception("Ollama error")
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
