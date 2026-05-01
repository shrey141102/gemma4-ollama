"""
Gemma4 E2B — FastAPI Application

Mounts all API routes and serves the chat UI.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.routes import (
    ask,
    chat,
    code,
    extract,
    health,
    moderate,
    openai_compat,
    summarize,
    vision,
)

app = FastAPI(
    title="Gemma4 E2B API",
    version="2.0.0",
    description=(
        "Self-hosted Gemma4 E2B on Ollama — "
        "Chat, Vision, Code, Summarize, Extract, Moderate. "
        "OpenAI-compatible at /v1/chat/completions."
    ),
)

# ── API routes ──
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(ask.router)
app.include_router(openai_compat.router)
app.include_router(extract.router)
app.include_router(summarize.router)
app.include_router(code.router)
app.include_router(vision.router)
app.include_router(moderate.router)

# ── Static files (CSS, JS) ──
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Chat UI ──
@app.get("/", response_class=HTMLResponse)
async def ui():
    """Serve the chat interface."""
    return (STATIC_DIR / "index.html").read_text()
