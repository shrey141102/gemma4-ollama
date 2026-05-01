"""
Summarize — POST /api/summarize

Summarize long text in various styles and lengths.
"""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

router = APIRouter(tags=["summarize"])

STYLE_PROMPTS = {
    "paragraph": "Provide a clear, flowing paragraph summary.",
    "bullets": "Provide the summary as concise bullet points (use - for each point).",
    "tldr": "Provide an extremely brief one-sentence TL;DR.",
}

LENGTH_GUIDES = {
    "short": "Keep it very concise — under 50 words.",
    "medium": "Aim for around 100-150 words.",
    "detailed": "Provide a thorough summary of 200-300 words, capturing key details.",
}


@router.post("/api/summarize")
async def summarize(request: Request):
    """
    Summarize text.

    Body:
      {
        "text": "...(long text)...",
        "style": "bullets",    // "paragraph" | "bullets" | "tldr"
        "max_length": "medium" // "short" | "medium" | "detailed"
      }
    """
    if not check_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    text = body.get("text", "")
    style = body.get("style", "paragraph")
    max_length = body.get("max_length", "medium")

    if not text:
        return JSONResponse(
            {"error": "Missing 'text' field"}, status_code=400
        )

    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["paragraph"])
    length_instruction = LENGTH_GUIDES.get(
        max_length, LENGTH_GUIDES["medium"]
    )

    system_prompt = (
        "You are a summarization assistant. "
        f"{style_instruction} {length_instruction} "
        "Focus on the most important information."
    )

    ollama_payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Summarize the following:\n\n{text}"},
        ],
        "stream": False,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": 0.3,
        },
    }

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
        data = r.json()

    return {
        "summary": data.get("message", {}).get("content", ""),
        "style": style,
        "model": MODEL_NAME,
        "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
    }
