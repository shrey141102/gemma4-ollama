"""
Code Generation — POST /api/code

Generate, explain, review, or convert code.
"""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.auth import check_api_key
from app.config import MODEL_NAME, NUM_CTX, OLLAMA_URL

router = APIRouter(tags=["code"])

TASK_PROMPTS = {
    "generate": (
        "You are an expert programmer. Generate clean, well-commented, "
        "production-quality code for the given task. "
        "Include brief usage examples if appropriate."
    ),
    "explain": (
        "You are a code explanation expert. Explain the given code clearly "
        "and thoroughly. Cover what it does, how it works, and any "
        "important design decisions. Use examples where helpful."
    ),
    "review": (
        "You are a senior code reviewer. Review the given code for bugs, "
        "performance issues, security vulnerabilities, and style. "
        "Provide specific, actionable suggestions for improvement. "
        "Rate the code quality from 1-10."
    ),
    "convert": (
        "You are a code conversion expert. Convert the given code to the "
        "specified target language. Preserve the logic and behavior exactly. "
        "Use idiomatic patterns of the target language."
    ),
}


@router.post("/api/code")
async def code(request: Request):
    """
    Code generation, explanation, review, or conversion.

    Body:
      {
        "task": "generate",        // "generate" | "explain" | "review" | "convert"
        "prompt": "Binary search", // task description or question
        "language": "python",      // target language
        "source_code": ""          // for explain/review/convert tasks
      }
    """
    if not check_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    task = body.get("task", "generate")
    prompt = body.get("prompt", "")
    language = body.get("language", "")
    source_code = body.get("source_code", "")

    if not prompt and not source_code:
        return JSONResponse(
            {"error": "Provide 'prompt' and/or 'source_code'"},
            status_code=400,
        )

    system_prompt = TASK_PROMPTS.get(task, TASK_PROMPTS["generate"])

    # Build user message based on task
    user_msg = ""
    if task == "generate":
        lang_hint = f" in {language}" if language else ""
        user_msg = f"Generate code{lang_hint}: {prompt}"
    elif task == "explain":
        user_msg = f"Explain this code:\n\n```\n{source_code}\n```"
        if prompt:
            user_msg += f"\n\nSpecific question: {prompt}"
    elif task == "review":
        user_msg = f"Review this code:\n\n```\n{source_code}\n```"
        if prompt:
            user_msg += f"\n\nFocus on: {prompt}"
    elif task == "convert":
        target = language or "the target language"
        user_msg = (
            f"Convert this code to {target}:\n\n```\n{source_code}\n```"
        )
        if prompt:
            user_msg += f"\n\nAdditional requirements: {prompt}"
    else:
        user_msg = prompt

    ollama_payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": 0.2,  # Low temp for code accuracy
        },
    }

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
        data = r.json()

    return {
        "result": data.get("message", {}).get("content", ""),
        "task": task,
        "language": language,
        "model": MODEL_NAME,
        "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
    }
