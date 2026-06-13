# Cobalt - Stage 1

Minimal AI reasoning engine for infrastructure automation.

## Setup

```bash
docker-compose up
```

Then visit `http://localhost:8000`

## Architecture

- **FastAPI** - API server
- **SQLAlchemy** - ORM
- **Ollama** - LLM backend (Mistral default)
- **PostgreSQL** - Persistent storage
- **APScheduler** - Task scheduling

## Next

Stage 2: Prometheus integration, tool execution
Stage 3: GitHub API integration
Stage 4: Proxmox integration
