"""
OpenAI-compatible API — /v1/chat/completions

Drop-in replacement for OpenAI's chat completions API.
Works with any OpenAI SDK, LangChain, Cursor, Continue, etc.
Just change the base_url to your server.
"""

import json
import time
import uuid

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

router = APIRouter(tags=["openai"])


def _make_id():
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


@router.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """
    OpenAI-compatible chat completions endpoint.

    Usage with OpenAI Python SDK:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://your-server.onrender.com/v1",
            api_key="your-key"
        )
        response = client.chat.completions.create(
            model="gemma4:e2b",
            messages=[{"role": "user", "content": "Hello!"}]
        )
    """
    if not check_api_key(request):
        return JSONResponse({"error": {"message": "unauthorized"}}, status_code=401)

    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    temperature = body.get("temperature", 0.7)
    max_tokens = body.get("max_tokens")

    # Map OpenAI params to Ollama
    options = {
        "num_ctx": NUM_CTX,
        "temperature": temperature,
    }
    if max_tokens:
        options["num_predict"] = max_tokens

    ollama_payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": stream,
        "options": options,
    }

    completion_id = _make_id()
    created = int(time.time())

    if stream:
        return StreamingResponse(
            _stream_openai_format(ollama_payload, completion_id, created),
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
        content = msg.get("content", "")

        # Estimate token counts from Ollama stats
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": MODEL_NAME,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


async def _stream_openai_format(payload: dict, completion_id: str, created: int):
    """Stream in OpenAI's SSE chunk format."""
    model = payload.get("model", MODEL_NAME)
    first_chunk = True

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST", f"{OLLAMA_URL}/api/chat", json=payload
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    error_msg = error_body.decode(errors="replace")
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": f"Error: {error_msg}"},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            ollama_chunk = json.loads(line)
                            content = ollama_chunk.get("message", {}).get(
                                "content", ""
                            )
                            done = ollama_chunk.get("done", False)

                            if content or first_chunk:
                                delta = {"content": content}
                                if first_chunk:
                                    delta["role"] = "assistant"
                                    first_chunk = False

                                chunk = {
                                    "id": completion_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": delta,
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                                yield f"data: {json.dumps(chunk)}\n\n"

                            if done:
                                # Final chunk with finish_reason
                                chunk = {
                                    "id": completion_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": model,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {},
                                            "finish_reason": "stop",
                                        }
                                    ],
                                }
                                yield f"data: {json.dumps(chunk)}\n\n"
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": f"Error: {str(e)}"},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"

    yield "data: [DONE]\n\n"


# OpenAI expects /v1/models to list available models
@router.get("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)."""
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": 0,
                "owned_by": "ollama",
            }
        ],
    }
