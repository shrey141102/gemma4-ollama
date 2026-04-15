"""
Chat API — POST /api/chat

Supports streaming (SSE) and non-streaming modes.
Includes Gemma 4 thinking support.
"""

import json

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

router = APIRouter(tags=["chat"])


@router.post("/api/chat")
async def chat(request: Request):
    """
    OpenAI-ish chat endpoint.

    Body:
      {
        "messages": [{"role": "user", "content": "Hello!"}],
        "stream": false,         // optional, default false
        "temperature": 0.7,      // optional
        "system": "You are..."   // optional system prompt
      }

    Headers:
      Authorization: Bearer <your-api-key>   (if API_KEY is set)
    """
    if not check_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    temperature = body.get("temperature", 0.7)
    system_prompt = body.get("system", "")

    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + messages

    ollama_payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": stream,
        "think": True,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": temperature,
        },
    }

    if stream:
        return StreamingResponse(
            _stream_response(ollama_payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    else:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/chat", json=ollama_payload
            )
            data = r.json()
        msg = data.get("message", {})
        return {
            "response": msg.get("content", ""),
            "thinking": msg.get("thinking", ""),
            "model": MODEL_NAME,
            "done": data.get("done", True),
            "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
        }


async def _stream_response(payload: dict):
    """Stream chunks as SSE events, including thinking tokens."""
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST", f"{OLLAMA_URL}/api/chat", json=payload
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    try:
                        error_msg = json.loads(error_body).get(
                            "error", "Ollama error"
                        )
                    except Exception:
                        error_msg = error_body.decode(errors="replace")
                    yield f"data: {json.dumps({'error': error_msg})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            msg = chunk.get("message", {})
                            thinking = msg.get("thinking", "")
                            content = msg.get("content", "")
                            if thinking:
                                yield f"data: {json.dumps({'thinking': thinking})}\n\n"
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                            if chunk.get("done"):
                                yield f"data: {json.dumps({'done': True})}\n\n"
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    yield "data: [DONE]\n\n"
