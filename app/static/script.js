/**
 * Gemma4 E2B — Chat UI Script
 *
 * Handles:
 *   - Markdown rendering (marked.js + highlight.js)
 *   - SSE streaming with thinking support
 *   - Message history management
 */

// ══════════════════════════════════════════════
//  Markdown configuration
// ══════════════════════════════════════════════

marked.setOptions({
  highlight: function (code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
});

// Custom renderer: code blocks get a language label + copy button
const renderer = new marked.Renderer();

renderer.code = function (obj) {
  const code = obj.text || obj;
  const lang = obj.lang || '';
  let highlighted;
  if (lang && hljs.getLanguage(lang)) {
    highlighted = hljs.highlight(code, { language: lang }).value;
  } else {
    highlighted = hljs.highlightAuto(code).value;
  }
  const langLabel = lang || 'code';
  return (
    `<pre><div class="code-header"><span>${langLabel}</span>` +
    `<button class="copy-btn" onclick="copyCode(this)">copy</button></div>` +
    `<code class="hljs">${highlighted}</code></pre>`
  );
};

marked.setOptions({ renderer });


// ══════════════════════════════════════════════
//  Utility functions
// ══════════════════════════════════════════════

function copyCode(btn) {
  const code = btn.closest('pre').querySelector('code').textContent;
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = 'copied!';
    setTimeout(() => (btn.textContent = 'copy'), 1500);
  });
}

function renderMarkdown(text) {
  try {
    return marked.parse(text);
  } catch {
    return text;
  }
}

function escapeHtml(text) {
  return text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const SHIMMER_HTML =
  '<div class="thinking-shimmer">' +
  '<div class="thinking-dots"><span></span><span></span><span></span></div>' +
  '<span class="shimmer-text">Thinking</span>' +
  '</div>';


// ══════════════════════════════════════════════
//  DOM references & state
// ══════════════════════════════════════════════

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');

let history = [];
let streaming = false;


// ══════════════════════════════════════════════
//  Input handling
// ══════════════════════════════════════════════

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


// ══════════════════════════════════════════════
//  Thinking block builder
// ══════════════════════════════════════════════

function buildThinkingHTML(thinkingText, isActive, startTime) {
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const iconClass = isActive ? 'thinking-icon active' : 'thinking-icon';
  const label = isActive ? 'Thinking...' : 'Thought for ' + elapsed + 's';
  const icon = isActive ? '\u2728' : '\u2713';
  const openAttr = isActive ? ' open' : '';

  let html = '<details class="thinking-block"' + openAttr + '>';
  html += '<summary>';
  html += '<span class="' + iconClass + '">' + icon + '</span>';
  html += '<span class="thinking-label">' + label + '</span>';
  if (!isActive) html += '<span class="thinking-time">' + elapsed + 's</span>';
  html += '</summary>';
  html += '<div class="thinking-content">' + escapeHtml(thinkingText) + '</div>';
  html += '</details>';
  return html;
}


// ══════════════════════════════════════════════
//  Full message HTML builder
// ══════════════════════════════════════════════

function buildMessageHTML(state) {
  let html = '';

  // Thinking section
  if (state.thinking) {
    html += buildThinkingHTML(state.thinking, state.isThinking, state.thinkingStartTime);
  } else if (state.isThinking && !state.content) {
    html += SHIMMER_HTML;
  }

  // Response content
  if (state.content) {
    html += renderMarkdown(state.content);
  }

  // Streaming cursor
  if (!state.isDone) {
    html += '<span class="blink-cursor">&#9608;</span>';
  }

  return html;
}


// ══════════════════════════════════════════════
//  Send message & handle streaming
// ══════════════════════════════════════════════

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

  // Add AI placeholder with thinking shimmer
  const aiEl = addMessage('', 'ai', true);
  const contentEl = aiEl.querySelector('.content');

  streaming = true;
  sendBtn.disabled = true;

  // Streaming state
  const state = {
    content: '',
    thinking: '',
    isDone: false,
    isThinking: true,
    thinkingStartTime: Date.now(),
  };

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
    let buffer = '';

    // Show initial thinking animation
    contentEl.innerHTML = buildMessageHTML(state);

    while (!state.isDone) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') {
          state.isDone = true;
          break;
        }

        let data;
        try { data = JSON.parse(payload); } catch { continue; }
        if (data.error) throw new Error(data.error);

        // Thinking tokens
        if (data.thinking) {
          state.thinking += data.thinking;
          contentEl.innerHTML = buildMessageHTML(state);
          const tc = contentEl.querySelector('.thinking-content');
          if (tc) tc.scrollTop = tc.scrollHeight;
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        // Content tokens
        if (data.content) {
          if (state.isThinking) {
            state.isThinking = false;
          }
          state.content += data.content;
          contentEl.innerHTML = buildMessageHTML(state);
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
      }
    }

    // Final render (no cursor, thinking collapsed)
    state.isDone = true;
    state.isThinking = false;
    contentEl.innerHTML = buildMessageHTML(state);

    if (state.content) {
      history.push({ role: 'assistant', content: state.content });
    }

    // Keep conversation history manageable
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


// ══════════════════════════════════════════════
//  Add message bubble to DOM
// ══════════════════════════════════════════════

function addMessage(text, role, isStreaming = false) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;

  if (role === 'ai') {
    const initial = isStreaming ? SHIMMER_HTML : text;
    el.innerHTML =
      '<div class="label">gemma4 e2b</div>' +
      '<div class="content">' + initial + '</div>';
  } else {
    el.textContent = text;
  }

  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}
