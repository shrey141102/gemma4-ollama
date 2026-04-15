"""
Health check endpoint — used by Render's load balancer.
Also includes a debug endpoint for testing Ollama's thinking support.
"""

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import OLLAMA_URL, MODEL_NAME, NUM_CTX

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


@router.get("/debug/think")
async def debug_think():
    """Debug: test what Ollama returns for thinking tokens."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": MODEL_NAME,
                    "messages": [{"role": "user", "content": "What is 2+2?"}],
                    "think": True,
                    "stream": False,
                    "options": {"num_ctx": NUM_CTX, "temperature": 0.7},
                },
            )
            data = r.json()
        msg = data.get("message", {})
        return {
            "raw_message_keys": list(msg.keys()),
            "thinking_field": msg.get("thinking", "<NOT PRESENT>"),
            "content_field": msg.get("content", "<NOT PRESENT>"),
            "content_has_think_tags": "<think>" in msg.get("content", ""),
            "full_raw_response": data,
        }
    except Exception as e:
        return {"error": str(e)}

