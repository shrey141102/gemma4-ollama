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
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
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
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    try:
                        error_msg = json.loads(error_body).get("error", "Ollama error")
                    except Exception:
                        error_msg = error_body.decode(errors="replace")
                    yield f"data: {json.dumps({'error': error_msg})}\n\n"
                    yield "data: [DONE]\n\n"
                    return
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
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
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
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.1/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
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
    word-break: break-word;
  }
  .msg.user {
    align-self: flex-end;
    background: var(--user-bg);
    border-bottom-right-radius: 4px;
    color: #c7d2fe;
    white-space: pre-wrap;
  }
  .msg.ai {
    align-self: flex-start;
    background: var(--ai-bg);
    border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
    max-width: 800px;
    width: 100%;
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

  /* ── Blinking cursor ── */
  .blink-cursor {
    color: var(--accent);
    animation: blink 0.8s step-end infinite;
    font-weight: bold;
  }
  @keyframes blink {
    50% { opacity: 0; }
  }

  /* ── Markdown rendering ── */
  .msg.ai .content p { margin: 0 0 12px 0; }
  .msg.ai .content p:last-child { margin-bottom: 0; }
  .msg.ai .content h1, .msg.ai .content h2,
  .msg.ai .content h3, .msg.ai .content h4 {
    color: var(--text);
    margin: 20px 0 10px 0;
    line-height: 1.3;
  }
  .msg.ai .content h1:first-child, .msg.ai .content h2:first-child,
  .msg.ai .content h3:first-child, .msg.ai .content h4:first-child {
    margin-top: 4px;
  }
  .msg.ai .content h1 { font-size: 1.4em; }
  .msg.ai .content h2 { font-size: 1.25em; }
  .msg.ai .content h3 { font-size: 1.1em; color: var(--accent); }
  .msg.ai .content h4 { font-size: 1em; color: var(--text-dim); }

  .msg.ai .content pre {
    background: #0d0d14;
    border: 1px solid var(--border);
    border-radius: 10px;
    margin: 12px 0;
    padding: 0;
    overflow: hidden;
  }
  .msg.ai .content pre code {
    display: block;
    padding: 16px;
    overflow-x: auto;
    font-family: 'DM Mono', monospace;
    font-size: 13px;
    line-height: 1.5;
    background: transparent;
    color: var(--text);
    border: none;
    border-radius: 0;
  }
  .msg.ai .content code {
    font-family: 'DM Mono', monospace;
    font-size: 0.88em;
    background: var(--surface2);
    padding: 2px 7px;
    border-radius: 5px;
    color: #c7d2fe;
    border: 1px solid var(--border);
  }
  .msg.ai .content ul, .msg.ai .content ol {
    margin: 8px 0;
    padding-left: 24px;
  }
  .msg.ai .content li { margin: 4px 0; }
  .msg.ai .content li::marker { color: var(--accent); }
  .msg.ai .content blockquote {
    border-left: 3px solid var(--accent);
    margin: 12px 0;
    padding: 8px 16px;
    color: var(--text-dim);
    background: rgba(110, 231, 183, 0.04);
    border-radius: 0 8px 8px 0;
  }
  .msg.ai .content hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 16px 0;
  }
  .msg.ai .content table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 13px;
  }
  .msg.ai .content th, .msg.ai .content td {
    border: 1px solid var(--border);
    padding: 8px 12px;
    text-align: left;
  }
  .msg.ai .content th {
    background: var(--surface2);
    color: var(--accent);
    font-weight: 500;
  }
  .msg.ai .content strong { color: #fff; }
  .msg.ai .content a {
    color: var(--accent);
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.2s;
  }
  .msg.ai .content a:hover { border-bottom-color: var(--accent); }

  /* Code block language label */
  .code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .copy-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-dim);
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    padding: 3px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s;
  }
  .copy-btn:hover {
    color: var(--accent);
    border-color: var(--accent);
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
// Configure marked with highlight.js
marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
});

// Custom renderer for code blocks with language label + copy button
const renderer = new marked.Renderer();
renderer.code = function(obj) {
  const code = obj.text || obj;
  const lang = obj.lang || '';
  let highlighted;
  if (lang && hljs.getLanguage(lang)) {
    highlighted = hljs.highlight(code, { language: lang }).value;
  } else {
    highlighted = hljs.highlightAuto(code).value;
  }
  const langLabel = lang || 'code';
  return `<pre><div class="code-header"><span>${langLabel}</span><button class="copy-btn" onclick="copyCode(this)">copy</button></div><code class="hljs">${highlighted}</code></pre>`;
};
marked.setOptions({ renderer });

function copyCode(btn) {
  const code = btn.closest('pre').querySelector('code').textContent;
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = 'copied!';
    setTimeout(() => btn.textContent = 'copy', 1500);
  });
}

function renderMarkdown(text) {
  try {
    return marked.parse(text);
  } catch {
    return text;
  }
}

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

    if (!res.ok) {
      const errText = await res.text();
      throw new Error('Server error (' + res.status + '): ' + errText);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let full = '';
    let buffer = '';
    let isDone = false;

    while (!isDone) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') { isDone = true; break; }
        let data;
        try { data = JSON.parse(payload); } catch { continue; }
        if (data.error) throw new Error(data.error);
        if (data.content) {
          full += data.content;
          contentEl.innerHTML = renderMarkdown(full) + '<span class="blink-cursor">&#9608;</span>';
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
      }
    }

    // Final render without cursor
    contentEl.innerHTML = renderMarkdown(full);
    if (full) history.push({ role: 'assistant', content: full });

    // Keep conversation history manageable (last 20 messages)
    if (history.length > 20) history = history.slice(-20);

  } catch (err) {
    contentEl.innerHTML = '';
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
    el.innerHTML = `<div class="label">gemma4 e2b</div><div class="content">${text}</div>`;
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
