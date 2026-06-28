import json
from pathlib import Path
import re
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
        self.model_store_path = self._resolve_model_store_path(
            settings.ollama_model_store_path
        )
        self.runtime_settings_store_path = self._resolve_model_store_path(
            settings.ollama_runtime_settings_store_path
        )
        self.model_config_lock = Lock()
        self.model = self._load_model()
        self.runtime_settings = self._load_runtime_settings()
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=300.0)

    def _resolve_model_store_path(self, configured_path: str) -> Path:
        base_dir = Path.cwd().resolve()
        resolved = (base_dir / configured_path).resolve()
        if base_dir not in resolved.parents and resolved != base_dir:
            logger.warning(
                "Invalid model store path outside repository; falling back to ./model_config.json"
            )
            return (base_dir / "model_config.json").resolve()
        return resolved

    def _load_model(self) -> str:
        with self.model_config_lock:
            if not self.model_store_path.exists():
                return settings.ollama_model
            try:
                with self.model_store_path.open(encoding="utf-8") as handle:
                    stored = json.load(handle)
                if isinstance(stored, dict) and isinstance(
                    stored.get("current_model"), str
                ):
                    model = stored["current_model"].strip()
                    if model:
                        return model
            except Exception as e:
                logger.warning(
                    f"Could not load model config from {self.model_store_path}: {e}"
                )
        return settings.ollama_model

    def _save_model(self) -> None:
        with self.model_config_lock:
            try:
                self.model_store_path.parent.mkdir(parents=True, exist_ok=True)
                with self.model_store_path.open("w", encoding="utf-8") as handle:
                    json.dump({"current_model": self.model}, handle)
            except Exception as e:
                logger.error(
                    f"Could not persist model config to {self.model_store_path}: {e}"
                )

    def _normalize_keep_alive(self, value: str | None) -> str:
        cleaned = (value or "").strip()
        return cleaned or settings.ollama_keep_alive

    def _load_runtime_settings(self) -> dict:
        default_settings = {"keep_alive": settings.ollama_keep_alive}
        with self.model_config_lock:
            if not self.runtime_settings_store_path.exists():
                return default_settings
            try:
                with self.runtime_settings_store_path.open(encoding="utf-8") as handle:
                    stored = json.load(handle)
                if isinstance(stored, dict):
                    return {
                        "keep_alive": self._normalize_keep_alive(
                            stored.get("keep_alive")
                        )
                    }
            except Exception as e:
                logger.warning(
                    f"Could not load runtime config from {self.runtime_settings_store_path}: {e}"
                )
        return default_settings

    def _save_runtime_settings(self) -> None:
        with self.model_config_lock:
            try:
                self.runtime_settings_store_path.parent.mkdir(
                    parents=True, exist_ok=True
                )
                with self.runtime_settings_store_path.open(
                    "w", encoding="utf-8"
                ) as handle:
                    json.dump(self.runtime_settings, handle)
            except Exception as e:
                logger.error(
                    f"Could not persist runtime config to {self.runtime_settings_store_path}: {e}"
                )

    def get_runtime_settings(self) -> dict:
        return dict(self.runtime_settings)

    def update_runtime_settings(self, keep_alive: str | None = None) -> dict:
        self.runtime_settings["keep_alive"] = self._normalize_keep_alive(keep_alive)
        self._save_runtime_settings()
        return self.get_runtime_settings()

    def set_model(self, model: str) -> str:
        selected = model.strip()
        if not selected:
            raise ValueError("Model cannot be empty")
        if not re.fullmatch(r"[A-Za-z0-9._:/-]+", selected):
            raise ValueError("Model contains invalid characters")
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
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": stream,
                    "keep_alive": self.runtime_settings["keep_alive"],
                },
            )
            return resp
        except Exception as e:
            logger.error(f"Ollama error: {e} for: {self.model}")
            raise

    async def summarize_first_message(self, messages: list[dict]) -> str:
        try:
            resp = await self.client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "think": False,
                    "keep_alive": self.runtime_settings["keep_alive"],
                    "options": {"temperature": 0.1, "top_p": 0.2, "num_predict": 16},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message") if isinstance(data, dict) else None
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
            return ""
        except Exception as e:
            logger.error(f"Ollama summary error: {e} for: {self.model}")
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
                    "keep_alive": self.runtime_settings["keep_alive"],
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

            raise ModelNotFoundError(self.model) if e.response.status_code == 404 else e

        except Exception:
            logger.exception("Ollama streaming request failed")
            raise

    async def pull_model(self, model_name: str | None = None) -> str:
        """Pull a model into Ollama and return the model name when done."""
        target_model = model_name or self.model
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=None
            ) as client:
                async with client.stream(
                    "POST",
                    "/api/pull",
                    json={"name": target_model, "stream": True},
                ) as response:
                    response.raise_for_status()
                    async for _ in response.aiter_lines():
                        pass
        except Exception as e:
            logger.error(f"Ollama pull error: {e}")
            raise
        return target_model

    async def close(self):
        await self.client.aclose()


ollama_service = OllamaService()
