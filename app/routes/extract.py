"""
Structured Extraction — POST /api/extract

Extract structured JSON data from unstructured text using a JSON schema.
Uses Ollama's native `format` parameter for guaranteed valid output.
"""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

router = APIRouter(tags=["extract"])

EXTRACT_SYSTEM_PROMPT = (
    "You are a data extraction assistant. "
    "Extract the requested information from the provided text. "
    "Return ONLY the JSON object matching the schema. "
    "If a field cannot be determined from the text, use null."
)


@router.post("/api/extract")
async def extract(request: Request):
    """
    Extract structured data from unstructured text.

    Body:
      {
        "text": "John Smith, age 28, works at Google",
        "schema": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "company": {"type": "string"}
          },
          "required": ["name"]
        },
        "instructions": ""  // optional extra instructions
      }
    """
    if not check_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    text = body.get("text", "")
    schema = body.get("schema")
    instructions = body.get("instructions", "")

    if not text:
        return JSONResponse(
            {"error": "Missing 'text' field"}, status_code=400
        )
    if not schema:
        return JSONResponse(
            {"error": "Missing 'schema' field — provide a JSON schema"},
            status_code=400,
        )

    user_prompt = f"Extract data from the following text:\n\n---\n{text}\n---"
    if instructions:
        user_prompt += f"\n\nAdditional instructions: {instructions}"

    ollama_payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": schema,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": 0.1,  # Low temp for consistent extraction
        },
    }

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
        data = r.json()

    content = data.get("message", {}).get("content", "")

    # Parse the JSON response
    import json

    try:
        extracted = json.loads(content)
    except json.JSONDecodeError:
        extracted = {"raw": content, "parse_error": True}

    return {
        "data": extracted,
        "model": MODEL_NAME,
        "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
    }
