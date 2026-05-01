/**
 * Gemma4 E2B — Chat UI Script
 *
 * Handles:
 *   - Markdown rendering (marked.js + highlight.js)
 *   - SSE streaming with thinking support
 *   - Image upload (file picker, paste, drag & drop)
 *   - Voice input (Web Speech API)
 *   - Message history management
 *   - Chat persistence (localStorage)
 *   - Copy message to clipboard
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

/** Copy the full text content of an AI message */
function copyMessage(btn) {
  const msgEl = btn.closest('.msg.ai');
  const contentEl = msgEl.querySelector('.content');
  // Get text content, stripping any HTML
  const text = contentEl.innerText || contentEl.textContent;
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    btn.querySelector('.copy-label').textContent = 'Copied!';
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.querySelector('.copy-label').textContent = 'Copy';
    }, 2000);
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

const COPY_BTN_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>' +
  '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>' +
  '</svg>';


// ══════════════════════════════════════════════
//  DOM references & state
// ══════════════════════════════════════════════

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
const imageInput = document.getElementById('image-input');
const imageBtn = document.getElementById('image-btn');
const micBtn = document.getElementById('mic-btn');
const imagePreview = document.getElementById('image-preview');
const previewImg = document.getElementById('preview-img');
const removeImageBtn = document.getElementById('remove-image');
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const newChatBtn = document.getElementById('new-chat-btn');
const chatListEl = document.getElementById('chat-list');

let history = [];
let streaming = false;
let stagedImageB64 = null; // Base64 image ready to send


// ══════════════════════════════════════════════
//  Chat persistence (localStorage)
// ══════════════════════════════════════════════

const STORAGE_KEY = 'gemma4_chats';
const ACTIVE_CHAT_KEY = 'gemma4_active_chat';

/** Generate a unique chat ID */
function generateChatId() {
  return 'chat_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
}

/** Load all saved chats from localStorage */
function loadChats() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** Save all chats to localStorage */
function saveChats(chats) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

/** Get the currently active chat ID */
function getActiveChatId() {
  return localStorage.getItem(ACTIVE_CHAT_KEY);
}

/** Set the active chat ID */
function setActiveChatId(id) {
  if (id) {
    localStorage.setItem(ACTIVE_CHAT_KEY, id);
  } else {
    localStorage.removeItem(ACTIVE_CHAT_KEY);
  }
}

/** Generate a title from the first user message */
function generateTitle(messages) {
  const firstUser = messages.find(m => m.role === 'user');
  if (!firstUser) return 'New Chat';
  const text = firstUser.content || '(image)';
  return text.length > 40 ? text.slice(0, 40) + '…' : text;
}

/** Save the current chat state */
function saveCurrentChat() {
  if (history.length === 0) return;

  const chats = loadChats();
  let chatId = getActiveChatId();

  if (!chatId) {
    chatId = generateChatId();
    setActiveChatId(chatId);
  }

  const existingIdx = chats.findIndex(c => c.id === chatId);
  const chatData = {
    id: chatId,
    title: generateTitle(history),
    messages: history,
    updatedAt: Date.now(),
  };

  if (existingIdx >= 0) {
    chats[existingIdx] = chatData;
  } else {
    chats.unshift(chatData);
  }

  saveChats(chats);
  renderChatList();
}

/** Delete a chat by ID */
function deleteChat(chatId) {
  let chats = loadChats();
  chats = chats.filter(c => c.id !== chatId);
  saveChats(chats);

  if (getActiveChatId() === chatId) {
    setActiveChatId(null);
    history = [];
    messagesEl.innerHTML = '';
    showWelcome();
  }

  renderChatList();
}

/** Load a specific chat into the view */
function loadChat(chatId) {
  const chats = loadChats();
  const chat = chats.find(c => c.id === chatId);
  if (!chat) return;

  setActiveChatId(chatId);
  history = chat.messages || [];

  // Re-render messages
  messagesEl.innerHTML = '';

  if (history.length === 0) {
    showWelcome();
  } else {
    for (const msg of history) {
      if (msg.role === 'user') {
        addMessage(msg.content, 'user', false, null, false);
      } else if (msg.role === 'assistant') {
        addMessage(msg.content, 'ai', false, null, false);
      }
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  renderChatList();
  closeSidebar();
}

/** Start a brand new chat */
function startNewChat() {
  // Save existing chat first
  saveCurrentChat();

  const chatId = generateChatId();
  setActiveChatId(chatId);
  history = [];
  messagesEl.innerHTML = '';
  showWelcome();
  renderChatList();
  closeSidebar();
  inputEl.focus();
}

/** Show the welcome screen */
function showWelcome() {
  messagesEl.innerHTML =
    '<div class="welcome">' +
    '<h2>Your own LLM, running in the cloud.</h2>' +
    '<p>Gemma4 E2B on Ollama — deployed on Render.com<br>' +
    'Supports text, images, and voice input.</p>' +
    '<div class="welcome-apis">' +
    '<code>POST /api/chat</code>' +
    '<code>POST /v1/chat/completions</code>' +
    '<code>POST /api/vision</code>' +
    '<code>POST /api/extract</code>' +
    '<code>POST /api/summarize</code>' +
    '<code>POST /api/code</code>' +
    '<code>POST /api/moderate</code>' +
    '<code>GET /ask?q=...</code>' +
    '</div></div>';
}

/** Format a timestamp for the chat list */
function formatTime(ts) {
  const d = new Date(ts);
  const now = new Date();
  const diff = now - d;
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (mins < 1) return 'Just now';
  if (mins < 60) return mins + 'm ago';
  if (hours < 24) return hours + 'h ago';
  if (days < 7) return days + 'd ago';
  return d.toLocaleDateString();
}

/** Render the chat list in the sidebar */
function renderChatList() {
  const chats = loadChats();
  const activeChatId = getActiveChatId();

  // Sort by most recently updated
  chats.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));

  if (chats.length === 0) {
    chatListEl.innerHTML =
      '<div style="padding: 20px; text-align: center; color: var(--text-dim); font-size: 12px; font-family: \'DM Mono\', monospace;">' +
      'No saved chats yet</div>';
    return;
  }

  chatListEl.innerHTML = chats.map(chat => {
    const isActive = chat.id === activeChatId;
    return (
      `<div class="chat-item${isActive ? ' active' : ''}" data-chat-id="${chat.id}" onclick="loadChat('${chat.id}')">` +
      `<span class="chat-item-icon">💬</span>` +
      `<div class="chat-item-text">` +
      `<div class="chat-item-title">${escapeHtml(chat.title || 'New Chat')}</div>` +
      `<div class="chat-item-time">${formatTime(chat.updatedAt)}</div>` +
      `</div>` +
      `<button class="chat-item-delete" onclick="event.stopPropagation(); deleteChat('${chat.id}')" title="Delete chat">🗑</button>` +
      `</div>`
    );
  }).join('');
}


// ══════════════════════════════════════════════
//  Sidebar toggle
// ══════════════════════════════════════════════

function toggleSidebar() {
  sidebar.classList.toggle('collapsed');
  if (!sidebar.classList.contains('collapsed')) {
    sidebarOverlay.classList.remove('hidden');
  } else {
    sidebarOverlay.classList.add('hidden');
  }
}

function closeSidebar() {
  if (window.innerWidth <= 768) {
    sidebar.classList.add('collapsed');
    sidebarOverlay.classList.add('hidden');
  }
}

sidebarToggle.addEventListener('click', toggleSidebar);
sidebarOverlay.addEventListener('click', () => {
  sidebar.classList.add('collapsed');
  sidebarOverlay.classList.add('hidden');
});
newChatBtn.addEventListener('click', startNewChat);


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
//  Image handling
// ══════════════════════════════════════════════

// File picker
imageBtn.addEventListener('click', () => imageInput.click());

imageInput.addEventListener('change', (e) => {
  if (e.target.files[0]) stageImage(e.target.files[0]);
});

// Remove staged image
removeImageBtn.addEventListener('click', clearStagedImage);

// Paste image from clipboard
inputEl.addEventListener('paste', (e) => {
  const items = e.clipboardData?.items;
  if (!items) return;
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault();
      stageImage(item.getAsFile());
      return;
    }
  }
});

// Drag & drop
let dragCounter = 0;
const dropOverlay = createDropOverlay();

document.addEventListener('dragenter', (e) => {
  e.preventDefault();
  dragCounter++;
  if (hasImageFile(e)) dropOverlay.classList.remove('hidden');
});

document.addEventListener('dragleave', (e) => {
  e.preventDefault();
  dragCounter--;
  if (dragCounter <= 0) {
    dragCounter = 0;
    dropOverlay.classList.add('hidden');
  }
});

document.addEventListener('dragover', (e) => e.preventDefault());

document.addEventListener('drop', (e) => {
  e.preventDefault();
  dragCounter = 0;
  dropOverlay.classList.add('hidden');
  const file = e.dataTransfer?.files[0];
  if (file && file.type.startsWith('image/')) {
    stageImage(file);
  }
});

function hasImageFile(e) {
  const types = e.dataTransfer?.types || [];
  return types.includes('Files');
}

function createDropOverlay() {
  const overlay = document.createElement('div');
  overlay.className = 'drop-overlay hidden';
  overlay.innerHTML =
    '<div class="drop-overlay-inner">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>' +
    '<circle cx="8.5" cy="8.5" r="1.5"></circle>' +
    '<polyline points="21 15 16 10 5 21"></polyline>' +
    '</svg>' +
    '<p>Drop image to attach</p>' +
    '</div>';
  document.body.appendChild(overlay);
  return overlay;
}

function stageImage(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    // Extract pure base64 (remove data:image/...;base64, prefix)
    stagedImageB64 = dataUrl.split(',')[1];
    previewImg.src = dataUrl;
    imagePreview.classList.remove('hidden');
    inputEl.focus();
  };
  reader.readAsDataURL(file);
}

function clearStagedImage() {
  stagedImageB64 = null;
  previewImg.src = '';
  imagePreview.classList.add('hidden');
  imageInput.value = '';
}


// ══════════════════════════════════════════════
//  Voice input (Web Speech API)
// ══════════════════════════════════════════════

let recognition = null;
let isRecording = false;

if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

  recognition.onresult = (e) => {
    let transcript = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript;
    }
    // Replace textarea content with transcript
    inputEl.value = transcript;
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 150) + 'px';
  };

  recognition.onend = () => {
    isRecording = false;
    micBtn.classList.remove('recording');
    micBtn.title = 'Voice input';
  };

  recognition.onerror = (e) => {
    console.warn('Speech recognition error:', e.error);
    isRecording = false;
    micBtn.classList.remove('recording');
  };

  micBtn.addEventListener('click', () => {
    if (isRecording) {
      recognition.stop();
    } else {
      recognition.start();
      isRecording = true;
      micBtn.classList.add('recording');
      micBtn.title = 'Listening... (click to stop)';
    }
  });
} else {
  // Browser doesn't support speech recognition
  micBtn.title = 'Voice input not supported in this browser';
  micBtn.style.opacity = '0.3';
  micBtn.style.cursor = 'not-allowed';
}


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
  if ((!text && !stagedImageB64) || streaming) return;

  // Remove welcome screen
  const welcome = messagesEl.querySelector('.welcome');
  if (welcome) welcome.remove();

  // Build the user message for the API
  const userMessage = { role: 'user', content: text || '(image)' };
  if (stagedImageB64) {
    userMessage.images = [stagedImageB64];
  }

  // Add user message to UI
  addMessage(text, 'user', false, stagedImageB64 ? previewImg.src : null);
  history.push(userMessage);

  // Clear input
  inputEl.value = '';
  inputEl.style.height = 'auto';
  const sentImageSrc = stagedImageB64 ? previewImg.src : null;
  clearStagedImage();

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

    // Save chat after each exchange
    saveCurrentChat();

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

function addMessage(text, role, isStreaming = false, imageSrc = null, withActions = true) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;

  if (role === 'ai') {
    const initial = isStreaming ? SHIMMER_HTML : renderMarkdown(text);
    const copyBtnHtml = withActions && !isStreaming && text
      ? `<div class="msg-actions">` +
        `<button class="msg-action-btn" onclick="copyMessage(this)" title="Copy response">` +
        COPY_BTN_SVG +
        `<span class="copy-label">Copy</span>` +
        `</button></div>`
      : '';

    el.innerHTML =
      '<div class="msg-header">' +
      '<div class="label">gemma4 e2b</div>' +
      copyBtnHtml +
      '</div>' +
      '<div class="content">' + initial + '</div>';

    // If streaming, add copy button once done
    if (isStreaming) {
      const observer = new MutationObserver(() => {
        // Check if streaming is complete by looking for absence of blink-cursor
        const contentEl = el.querySelector('.content');
        const hasCursor = contentEl?.querySelector('.blink-cursor');
        const hasContent = contentEl && contentEl.textContent.trim().length > 0;

        if (!hasCursor && hasContent && !el.querySelector('.msg-action-btn')) {
          const header = el.querySelector('.msg-header');
          if (header && !header.querySelector('.msg-actions')) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'msg-actions';
            actionsDiv.innerHTML =
              `<button class="msg-action-btn" onclick="copyMessage(this)" title="Copy response">` +
              COPY_BTN_SVG +
              `<span class="copy-label">Copy</span>` +
              `</button>`;
            header.appendChild(actionsDiv);
          }
          observer.disconnect();
        }
      });
      observer.observe(el, { childList: true, subtree: true, characterData: true });
    }
  } else {
    let html = '';
    // Show attached image in user message
    if (imageSrc) {
      html += '<div class="msg-image"><img src="' + imageSrc + '" alt="Attached image"></div>';
    }
    if (text) {
      html += escapeHtml(text);
    }
    el.innerHTML = html;
  }

  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}


// ══════════════════════════════════════════════
//  Initialize on page load
// ══════════════════════════════════════════════

(function init() {
  // Initialize sidebar state
  if (window.innerWidth <= 768) {
    sidebar.classList.add('collapsed');
  }

  // Render chat list
  renderChatList();

  // Load the last active chat, or show welcome
  const activeChatId = getActiveChatId();
  if (activeChatId) {
    const chats = loadChats();
    const activeChat = chats.find(c => c.id === activeChatId);
    if (activeChat && activeChat.messages && activeChat.messages.length > 0) {
      loadChat(activeChatId);
    } else {
      showWelcome();
    }
  }
})();
