"""
Content Moderation — POST /api/moderate

Analyze text for safety concerns and return structured ratings.
"""

import json

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

router = APIRouter(tags=["moderate"])

MODERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "safe": {"type": "boolean"},
        "confidence": {"type": "number"},
        "categories": {
            "type": "object",
            "properties": {
                "hate_speech": {"type": "boolean"},
                "violence": {"type": "boolean"},
                "sexual_content": {"type": "boolean"},
                "self_harm": {"type": "boolean"},
                "harassment": {"type": "boolean"},
                "illegal_activity": {"type": "boolean"},
            },
            "required": [
                "hate_speech",
                "violence",
                "sexual_content",
                "self_harm",
                "harassment",
                "illegal_activity",
            ],
        },
        "reason": {"type": "string"},
    },
    "required": ["safe", "confidence", "categories", "reason"],
}

MODERATION_PROMPT = (
    "You are a content moderation system. Analyze the given text for safety. "
    "Evaluate each category independently. "
    "Set 'safe' to true if the content is appropriate for general audiences. "
    "Set 'confidence' as a number between 0 and 1 indicating how confident you are. "
    "Provide a brief 'reason' explaining your assessment."
)


@router.post("/api/moderate")
async def moderate(request: Request):
    """
    Analyze text for content safety.

    Body:
      {
        "text": "some user-generated content"
      }

    Response:
      {
        "safe": true,
        "confidence": 0.95,
        "categories": {
          "hate_speech": false,
          "violence": false,
          "sexual_content": false,
          "self_harm": false,
          "harassment": false,
          "illegal_activity": false
        },
        "reason": "Content is a normal question about science."
      }
    """
    if not check_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    text = body.get("text", "")

    if not text:
        return JSONResponse(
            {"error": "Missing 'text' field"}, status_code=400
        )

    ollama_payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": MODERATION_PROMPT},
            {"role": "user", "content": f"Evaluate this content:\n\n{text}"},
        ],
        "stream": False,
        "format": MODERATION_SCHEMA,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": 0.1,
        },
    }

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
        data = r.json()

    content = data.get("message", {}).get("content", "")

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        result = {
            "safe": True,
            "confidence": 0.0,
            "categories": {
                "hate_speech": False,
                "violence": False,
                "sexual_content": False,
                "self_harm": False,
                "harassment": False,
                "illegal_activity": False,
            },
            "reason": "Could not parse moderation response",
            "raw": content,
        }

    return {
        **result,
        "model": MODEL_NAME,
        "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
    }
