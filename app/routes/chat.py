"""
Chat API — POST /api/chat

Supports streaming (SSE) and non-streaming modes.
Includes Gemma 4 thinking support with fallback for older Ollama versions.
"""

import json
import logging
import re

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

logger = logging.getLogger(__name__)

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
        content = msg.get("content", "")
        thinking = msg.get("thinking", "")

        # Fallback: parse <think> tags from content if thinking field is empty
        if not thinking and content:
            content, thinking = _extract_think_tags(content)

        return {
            "response": content,
            "thinking": thinking,
            "model": MODEL_NAME,
            "done": data.get("done", True),
            "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
        }


def _extract_think_tags(text: str) -> tuple[str, str]:
    """
    Fallback: extract <think>...</think> blocks from content.
    Some Ollama versions embed thinking inside the content field
    rather than using a separate 'thinking' field.
    Returns (content_without_think, thinking_text).
    """
    pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    thinking_parts = pattern.findall(text)
    if thinking_parts:
        clean_content = pattern.sub("", text).strip()
        thinking_text = "\n".join(part.strip() for part in thinking_parts)
        return clean_content, thinking_text
    return text, ""


async def _stream_response(payload: dict):
    """Stream chunks as SSE events, including thinking tokens."""
    in_think_tag = False
    think_buffer = ""

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

                            # Primary: use the dedicated thinking field
                            if thinking:
                                yield f"data: {json.dumps({'thinking': thinking})}\n\n"

                            if content:
                                # Fallback: detect <think> tags in content stream
                                processed = _process_content_for_think_tags(
                                    content, in_think_tag, think_buffer
                                )
                                in_think_tag = processed["in_think_tag"]
                                think_buffer = processed["think_buffer"]

                                if processed["thinking_out"]:
                                    yield f"data: {json.dumps({'thinking': processed['thinking_out']})}\n\n"
                                if processed["content_out"]:
                                    yield f"data: {json.dumps({'content': processed['content_out']})}\n\n"

                                # If no fallback was triggered (no tags found),
                                # and no dedicated thinking field, send as content
                                if (
                                    not processed["thinking_out"]
                                    and not processed["content_out"]
                                    and not thinking
                                ):
                                    yield f"data: {json.dumps({'content': content})}\n\n"

                            if chunk.get("done"):
                                yield f"data: {json.dumps({'done': True})}\n\n"
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    yield "data: [DONE]\n\n"


def _process_content_for_think_tags(
    token: str, in_think_tag: bool, buffer: str
) -> dict:
    """
    Process a content token for inline <think> tags.
    Handles the case where tags span multiple tokens.
    Returns dict with: thinking_out, content_out, in_think_tag, think_buffer
    """
    result = {
        "thinking_out": "",
        "content_out": "",
        "in_think_tag": in_think_tag,
        "think_buffer": buffer,
    }

    combined = buffer + token

    # Check for opening tag
    if not in_think_tag:
        if "<think>" in combined:
            parts = combined.split("<think>", 1)
            if parts[0]:
                result["content_out"] = parts[0]
            result["in_think_tag"] = True
            result["think_buffer"] = parts[1] if len(parts) > 1 else ""
            # Check if closing tag is also in this chunk
            if "</think>" in result["think_buffer"]:
                think_parts = result["think_buffer"].split("</think>", 1)
                result["thinking_out"] = think_parts[0]
                result["content_out"] += think_parts[1] if len(think_parts) > 1 else ""
                result["in_think_tag"] = False
                result["think_buffer"] = ""
            return result
        elif "<" in token and not combined.endswith(">"):
            # Might be a partial tag, buffer it
            result["think_buffer"] = combined
            return result
        else:
            result["content_out"] = combined
            result["think_buffer"] = ""
            return result

    # Inside think tag — look for closing tag
    if "</think>" in combined:
        parts = combined.split("</think>", 1)
        result["thinking_out"] = parts[0]
        result["in_think_tag"] = False
        result["think_buffer"] = ""
        if parts[1]:
            result["content_out"] = parts[1]
    else:
        # Still inside thinking — emit what we have
        result["thinking_out"] = combined
        result["think_buffer"] = ""

    return result
