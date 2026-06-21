from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    environment: str = "development"
    debug: bool = False
    
    database_url: str = "sqlite:///./cobalt.db"
    sqlalchemy_echo: bool = False
    
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:14b"
    
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    scheduler_enabled: bool = True
    
settings = Settings()
