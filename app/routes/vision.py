"""
Vision — POST /api/vision

Analyze images using Gemma 4's multimodal capabilities.
Accepts base64-encoded images or image URLs.
"""

import base64

import httpx
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

router = APIRouter(tags=["vision"])


@router.post("/api/vision")
async def vision(request: Request):
    """
    Analyze an image with a natural language prompt.

    Body (JSON):
      {
        "image": "<base64 encoded image>",
        "prompt": "Describe what you see",
        "detail": "high"  // optional: "low" | "high"
      }
    """
    if not check_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    image_b64 = body.get("image", "")
    prompt = body.get("prompt", "Describe this image in detail.")

    if not image_b64:
        return JSONResponse(
            {"error": "Missing 'image' field — provide a base64-encoded image"},
            status_code=400,
        )

    # Strip data URI prefix if present (e.g., "data:image/png;base64,...")
    if "," in image_b64 and image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]

    ollama_payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
        "stream": False,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": 0.5,
        },
    }

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
        data = r.json()

    return {
        "description": data.get("message", {}).get("content", ""),
        "model": MODEL_NAME,
        "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
    }


@router.post("/api/vision/upload")
async def vision_upload(
    file: UploadFile = File(...),
    prompt: str = Form("Describe this image in detail."),
):
    """
    Analyze an uploaded image file.

    Multipart form:
      - file: image file (png, jpg, webp, gif)
      - prompt: analysis prompt (optional)
    """
    contents = await file.read()
    image_b64 = base64.b64encode(contents).decode("utf-8")

    ollama_payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
        "stream": False,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": 0.5,
        },
    }

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
        data = r.json()

    return {
        "description": data.get("message", {}).get("content", ""),
        "filename": file.filename,
        "model": MODEL_NAME,
        "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
    }
