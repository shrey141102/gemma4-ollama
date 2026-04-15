"""
Health check endpoint — used by Render's load balancer.
"""

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import OLLAMA_URL, MODEL_NAME

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Health check for Render."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            models = r.json().get("models", [])
            loaded = any(
                m["name"].startswith(MODEL_NAME.split(":")[0]) for m in models
            )
        return {"status": "ok", "model": MODEL_NAME, "loaded": loaded}
    except Exception as e:
        return JSONResponse(
            {"status": "error", "detail": str(e)}, status_code=503
        )
