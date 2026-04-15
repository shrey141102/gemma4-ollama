"""
Quick Q&A shorthand — GET /ask?q=...
"""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

router = APIRouter(tags=["ask"])


@router.get("/ask")
async def ask(q: str, request: Request):
    """Quick one-shot: GET /ask?q=What is gravity?"""
    if not check_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": q}],
                "stream": False,
                "options": {"num_ctx": NUM_CTX, "temperature": 0.7},
            },
        )
        data = r.json()

    return {
        "question": q,
        "answer": data.get("message", {}).get("content", ""),
        "model": MODEL_NAME,
    }
