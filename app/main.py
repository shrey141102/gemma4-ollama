"""
Gemma4 E2B — FastAPI Application

Mounts all API routes and serves the chat UI.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.routes import ask, chat, health

app = FastAPI(title="Gemma4 E2B API", version="1.0.0")

# ── API routes ──
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(ask.router)

# ── Static files (CSS, JS) ──
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Chat UI ──
@app.get("/", response_class=HTMLResponse)
async def ui():
    """Serve the chat interface."""
    return (STATIC_DIR / "index.html").read_text()
