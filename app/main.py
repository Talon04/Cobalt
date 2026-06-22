from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from app.api.router import router
from app.core.lifespan import lifespan
from app.core.logging import logger
from app.core.config import settings
from app.services.llm import ollama_service

app = FastAPI(title="Cobalt", lifespan=lifespan)

# Static files
try:
    app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")
except Exception as e:
    logger.warning(f"Could not mount static files: {e}")

# Routes
app.include_router(router)

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve UI"""
    with open("app/ui/templates/chat.html") as f:
        return f.read().replace("{{MODEL_NAME}}", ollama_service.model)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
