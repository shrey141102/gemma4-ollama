"""
Ollama Gemma4 E2B — API Server + Chat UI
Deploy on Render.com with 8GB RAM
"""

import os
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

app = FastAPI(title="Gemma4 E2B API", version="1.0.0")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("MODEL_NAME", "gemma4:e2b")
# Keep context small to fit in 8GB RAM
NUM_CTX = int(os.getenv("NUM_CTX", "8192"))
# Optional API key for basic auth (set in Render env vars)
API_KEY = os.getenv("API_KEY", "")


def check_api_key(request: Request) -> bool:
    """Simple API key check. If API_KEY env var is empty, auth is disabled."""
    if not API_KEY:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] == API_KEY
    key = request.query_params.get("api_key", "")
    return key == API_KEY


# ──────────────────────────────────────────────
#  Health / Status
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check for Render."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            models = r.json().get("models", [])
            loaded = any(m["name"].startswith(MODEL.split(":")[0]) for m in models)
        return {"status": "ok", "model": MODEL, "loaded": loaded}
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


# ──────────────────────────────────────────────
#  Chat API  (POST /api/chat)
# ──────────────────────────────────────────────

@app.post("/api/chat")
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
        "model": MODEL,
        "messages": messages,
        "stream": stream,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": temperature,
        },
    }

    if stream:
        return StreamingResponse(
            _stream_response(ollama_payload),
            media_type="text/event-stream",
        )
    else:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
            data = r.json()
        return {
            "response": data.get("message", {}).get("content", ""),
            "model": MODEL,
            "done": data.get("done", True),
            "total_duration_ms": data.get("total_duration", 0) // 1_000_000,
        }


async def _stream_response(payload: dict):
    """Stream chunks as SSE events."""
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield f"data: {json.dumps({'content': content})}\n\n"
                        if chunk.get("done"):
                            yield f"data: {json.dumps({'done': True})}\n\n"
                    except json.JSONDecodeError:
                        pass
    yield "data: [DONE]\n\n"


# ──────────────────────────────────────────────
#  Simple Q&A shorthand  (GET /ask?q=...)
# ──────────────────────────────────────────────

@app.get("/ask")
async def ask(q: str, request: Request):
    """Quick one-shot: GET /ask?q=What is gravity?"""
    if not check_api_key(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": q}],
                "stream": False,
                "options": {"num_ctx": NUM_CTX, "temperature": 0.7},
            },
        )
        data = r.json()

    return {
        "question": q,
        "answer": data.get("message", {}).get("content", ""),
        "model": MODEL,
    }


# ──────────────────────────────────────────────
#  Chat UI  (GET /)
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def ui():
    return CHAT_HTML


# ──────────────────────────────────────────────
#  The Chat UI HTML
# ──────────────────────────────────────────────

CHAT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gemma4 E2B — Chat</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a0c;
    --surface: #13131a;
    --surface2: #1c1c28;
    --border: #2a2a3a;
    --text: #e4e4ef;
    --text-dim: #8888a0;
    --accent: #6ee7b7;
    --accent-dim: #065f46;
    --user-bg: #1e1b4b;
    --ai-bg: #13131a;
    --danger: #f87171;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Header ── */
  header {
    padding: 16px 24px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
    background: var(--surface);
  }
  header .dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent);
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  header h1 {
    font-family: 'DM Mono', monospace;
    font-size: 15px;
    font-weight: 500;
    letter-spacing: 0.5px;
  }
  header h1 span { color: var(--accent); }
  header .badge {
    margin-left: auto;
    font-size: 11px;
    color: var(--text-dim);
    background: var(--surface2);
    padding: 4px 10px;
    border-radius: 100px;
    font-family: 'DM Mono', monospace;
  }

  /* ── Messages ── */
  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    scroll-behavior: smooth;
  }
  #messages::-webkit-scrollbar { width: 6px; }
  #messages::-webkit-scrollbar-track { background: transparent; }
  #messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .msg {
    max-width: 720px;
    width: fit-content;
    padding: 14px 18px;
    border-radius: 16px;
    font-size: 14.5px;
    line-height: 1.65;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .msg.user {
    align-self: flex-end;
    background: var(--user-bg);
    border-bottom-right-radius: 4px;
    color: #c7d2fe;
  }
  .msg.ai {
    align-self: flex-start;
    background: var(--ai-bg);
    border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
  }
  .msg.ai .label {
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 8px;
  }
  .msg.error {
    background: #1a0505;
    border: 1px solid #7f1d1d;
    color: var(--danger);
  }

  .typing-cursor::after {
    content: '▊';
    animation: blink 0.8s step-end infinite;
    color: var(--accent);
    margin-left: 2px;
  }
  @keyframes blink {
    50% { opacity: 0; }
  }

  /* ── Welcome ── */
  .welcome {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-dim);
  }
  .welcome h2 {
    font-family: 'DM Mono', monospace;
    font-size: 20px;
    color: var(--text);
    margin-bottom: 8px;
  }
  .welcome p { font-size: 13px; line-height: 1.6; }
  .welcome code {
    display: inline-block;
    margin-top: 12px;
    background: var(--surface2);
    padding: 6px 14px;
    border-radius: 6px;
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: var(--accent);
  }

  /* ── Input area ── */
  #input-area {
    padding: 16px 24px;
    border-top: 1px solid var(--border);
    background: var(--surface);
    flex-shrink: 0;
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }
  #input-area textarea {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    font-size: 14px;
    resize: none;
    min-height: 46px;
    max-height: 150px;
    outline: none;
    transition: border-color 0.2s;
  }
  #input-area textarea:focus { border-color: var(--accent); }
  #input-area textarea::placeholder { color: var(--text-dim); }
  #input-area button {
    background: var(--accent);
    border: none;
    border-radius: 12px;
    width: 46px;
    height: 46px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.15s, opacity 0.15s;
    flex-shrink: 0;
  }
  #input-area button:hover { transform: scale(1.05); }
  #input-area button:disabled { opacity: 0.3; cursor: not-allowed; transform: none; }
  #input-area button svg { width: 20px; height: 20px; }

  /* ── Footer ── */
  footer {
    text-align: center;
    padding: 8px;
    font-size: 11px;
    color: var(--text-dim);
    font-family: 'DM Mono', monospace;
    border-top: 1px solid var(--border);
    background: var(--bg);
  }
</style>
</head>
<body>

<header>
  <div class="dot"></div>
  <h1><span>gemma4</span>:e2b</h1>
  <div class="badge">Ollama · Render</div>
</header>

<div id="messages">
  <div class="welcome">
    <h2>Your own LLM, running in the cloud.</h2>
    <p>Gemma4 E2B on Ollama — deployed on Render.com<br>
    Type anything below to start chatting.</p>
    <code>POST /api/chat &nbsp;·&nbsp; GET /ask?q=...</code>
  </div>
</div>

<div id="input-area">
  <textarea id="input" rows="1" placeholder="Ask me anything..." autofocus></textarea>
  <button id="send" title="Send">
    <svg viewBox="0 0 24 24" fill="none" stroke="#0a0a0c" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <line x1="22" y1="2" x2="11" y2="13"></line>
      <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
    </svg>
  </button>
</div>

<footer>CPU inference — responses may take a few seconds · API docs at /docs</footer>

<script>
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
let history = [];
let streaming = false;

// Auto-resize textarea
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 150) + 'px';
});

// Send on Enter (Shift+Enter for newline)
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});
sendBtn.addEventListener('click', send);

async function send() {
  const text = inputEl.value.trim();
  if (!text || streaming) return;

  // Remove welcome screen
  const welcome = messagesEl.querySelector('.welcome');
  if (welcome) welcome.remove();

  // Add user message
  addMessage(text, 'user');
  history.push({ role: 'user', content: text });
  inputEl.value = '';
  inputEl.style.height = 'auto';

  // Add AI placeholder
  const aiEl = addMessage('', 'ai', true);
  const contentEl = aiEl.querySelector('.content');

  streaming = true;
  sendBtn.disabled = true;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: history, stream: true }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let full = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6);
        if (payload === '[DONE]') break;
        try {
          const data = JSON.parse(payload);
          if (data.content) {
            full += data.content;
            contentEl.textContent = full;
            messagesEl.scrollTop = messagesEl.scrollHeight;
          }
        } catch {}
      }
    }

    contentEl.classList.remove('typing-cursor');
    history.push({ role: 'assistant', content: full });

    // Keep conversation history manageable (last 20 messages)
    if (history.length > 20) history = history.slice(-20);

  } catch (err) {
    contentEl.classList.remove('typing-cursor');
    contentEl.textContent = 'Error: ' + err.message;
    aiEl.classList.add('error');
  }

  streaming = false;
  sendBtn.disabled = false;
  inputEl.focus();
}

function addMessage(text, role, isStreaming = false) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  if (role === 'ai') {
    el.innerHTML = `<div class="label">gemma4 e2b</div><div class="content ${isStreaming ? 'typing-cursor' : ''}">${text}</div>`;
  } else {
    el.textContent = text;
  }
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}
</script>
</body>
</html>
"""
