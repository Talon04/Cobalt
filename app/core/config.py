from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    debug: bool = False

    database_url: str = "sqlite:///./cobalt.db"
    sqlalchemy_echo: bool = False

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:14b"
    ollama_model_store_path: str = "./model_config.json"
    ollama_runtime_settings_store_path: str = "./ollama_runtime_settings.json"
    ollama_keep_alive: str = "5m"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    scheduler_enabled: bool = True


settings = Settings()
