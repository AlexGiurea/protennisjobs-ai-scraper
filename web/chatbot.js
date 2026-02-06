/**
 * Pro Tennis Jobs — Chatbot Widget
 * Self-contained: injects its own styles & DOM, then handles chat logic.
 */
(function () {
  "use strict";

  /* ── Configuration ─────────────────────────────────────────────── */
  const CHAT_ENDPOINT = "/api/chat";
  const SESSION_KEY = "ptj_chat_history";
  const MAX_HISTORY = 40; // max messages kept in context

  /* ── Styles ────────────────────────────────────────────────────── */
  const STYLE = document.createElement("style");
  STYLE.textContent = `
    /* Toggle button */
    .ptj-chat-toggle {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 9998;
      width: 58px;
      height: 58px;
      border-radius: 50%;
      border: none;
      background: linear-gradient(135deg, #4f46e5, #6366f1);
      color: #fff;
      cursor: pointer;
      box-shadow: 0 6px 24px rgba(79, 70, 229, 0.45);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.25s ease, box-shadow 0.25s ease;
    }
    .ptj-chat-toggle:hover {
      transform: scale(1.08);
      box-shadow: 0 8px 30px rgba(79, 70, 229, 0.55);
    }
    .ptj-chat-toggle svg { width: 26px; height: 26px; }

    /* Panel */
    .ptj-chat-panel {
      position: fixed;
      bottom: 96px;
      right: 24px;
      z-index: 9999;
      width: 390px;
      max-height: 540px;
      border-radius: 20px;
      background: #ffffff;
      box-shadow: 0 20px 60px rgba(15, 23, 42, 0.22);
      border: 1px solid #e2e8f0;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      opacity: 0;
      transform: translateY(16px) scale(0.96);
      pointer-events: none;
      transition: opacity 0.25s ease, transform 0.25s ease;
    }
    .ptj-chat-panel.is-open {
      opacity: 1;
      transform: translateY(0) scale(1);
      pointer-events: auto;
    }

    /* Header */
    .ptj-chat-header {
      background: linear-gradient(135deg, #4f46e5, #6366f1);
      color: #fff;
      padding: 16px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    .ptj-chat-header-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .ptj-chat-header-icon {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: rgba(255,255,255,0.2);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .ptj-chat-header-icon svg { width: 18px; height: 18px; }
    .ptj-chat-header h4 {
      margin: 0;
      font-size: 0.95rem;
      font-weight: 600;
    }
    .ptj-chat-header small {
      font-size: 0.75rem;
      opacity: 0.8;
    }
    .ptj-chat-close {
      background: none;
      border: none;
      color: #fff;
      cursor: pointer;
      padding: 4px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.15s;
    }
    .ptj-chat-close:hover { background: rgba(255,255,255,0.18); }
    .ptj-chat-close svg { width: 18px; height: 18px; }

    /* Messages area */
    .ptj-chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-height: 0;
      background: #f8fafc;
    }
    .ptj-chat-messages::-webkit-scrollbar { width: 5px; }
    .ptj-chat-messages::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      border-radius: 999px;
    }

    /* Bubbles */
    .ptj-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 16px;
      font-size: 0.9rem;
      line-height: 1.55;
      word-wrap: break-word;
      white-space: pre-wrap;
    }
    .ptj-msg-user {
      align-self: flex-end;
      background: linear-gradient(135deg, #4f46e5, #6366f1);
      color: #fff;
      border-bottom-right-radius: 4px;
    }
    .ptj-msg-assistant {
      align-self: flex-start;
      background: #ffffff;
      color: #1e293b;
      border: 1px solid #e2e8f0;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    }
    .ptj-msg-welcome {
      align-self: flex-start;
      background: linear-gradient(135deg, #eef2ff, #e0e7ff);
      color: #3730a3;
      border: 1px solid rgba(79, 70, 229, 0.15);
      border-bottom-left-radius: 4px;
      font-size: 0.88rem;
    }

    /* Typing indicator */
    .ptj-typing {
      align-self: flex-start;
      display: flex;
      gap: 5px;
      padding: 12px 16px;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      border-bottom-left-radius: 4px;
    }
    .ptj-typing span {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #94a3b8;
      animation: ptj-bounce 1.2s infinite ease-in-out;
    }
    .ptj-typing span:nth-child(2) { animation-delay: 0.15s; }
    .ptj-typing span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes ptj-bounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-6px); }
    }

    /* Input area */
    .ptj-chat-input-area {
      padding: 12px 14px;
      border-top: 1px solid #e2e8f0;
      display: flex;
      gap: 8px;
      background: #fff;
      flex-shrink: 0;
    }
    .ptj-chat-input {
      flex: 1;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 10px 14px;
      font-size: 0.9rem;
      color: #0f172a;
      outline: none;
      resize: none;
      min-height: 40px;
      max-height: 100px;
      line-height: 1.4;
      font-family: inherit;
    }
    .ptj-chat-input:focus {
      border-color: rgba(79, 70, 229, 0.5);
      box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.12);
    }
    .ptj-chat-input::placeholder { color: #94a3b8; }
    .ptj-chat-send {
      width: 40px;
      height: 40px;
      border-radius: 12px;
      border: none;
      background: linear-gradient(135deg, #4f46e5, #6366f1);
      color: #fff;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: transform 0.15s, opacity 0.15s;
      align-self: flex-end;
    }
    .ptj-chat-send:hover { transform: scale(1.06); }
    .ptj-chat-send:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .ptj-chat-send svg { width: 18px; height: 18px; }

    /* Clear button */
    .ptj-chat-clear {
      background: none;
      border: none;
      color: #94a3b8;
      font-size: 0.75rem;
      cursor: pointer;
      padding: 2px 6px;
      transition: color 0.15s;
    }
    .ptj-chat-clear:hover { color: #64748b; }

    /* Footer row */
    .ptj-chat-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 14px 8px;
      background: #fff;
    }
    .ptj-chat-footer small {
      color: #cbd5e1;
      font-size: 0.7rem;
    }

    /* Responsive */
    @media (max-width: 480px) {
      .ptj-chat-panel {
        right: 8px;
        left: 8px;
        bottom: 88px;
        width: auto;
        max-height: 70vh;
        border-radius: 16px;
      }
      .ptj-chat-toggle {
        bottom: 16px;
        right: 16px;
      }
    }
  `;
  document.head.appendChild(STYLE);

  /* ── SVG icons ─────────────────────────────────────────────────── */
  const ICON_CHAT = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>`;
  const ICON_CLOSE = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>`;
  const ICON_SEND = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M12 5l7 7-7 7"/></svg>`;
  const ICON_BOT = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5m-4.75-11.396c.251.023.501.05.75.082M12 21a8.966 8.966 0 01-5.982-2.275M12 21a8.966 8.966 0 005.982-2.275"/></svg>`;

  /* ── Build DOM ─────────────────────────────────────────────────── */
  // Toggle button
  const toggleBtn = document.createElement("button");
  toggleBtn.className = "ptj-chat-toggle";
  toggleBtn.setAttribute("aria-label", "Open chat assistant");
  toggleBtn.innerHTML = ICON_CHAT;

  // Panel
  const panel = document.createElement("div");
  panel.className = "ptj-chat-panel";
  panel.innerHTML = `
    <div class="ptj-chat-header">
      <div class="ptj-chat-header-left">
        <div class="ptj-chat-header-icon">${ICON_BOT}</div>
        <div>
          <h4>Ace</h4>
        </div>
      </div>
      <button class="ptj-chat-close" aria-label="Close chat">${ICON_CLOSE}</button>
    </div>
    <div class="ptj-chat-messages" id="ptj-chat-messages"></div>
    <div class="ptj-chat-input-area">
      <textarea class="ptj-chat-input" id="ptj-chat-input"
        placeholder="Ask about tennis jobs..." rows="1"></textarea>
      <button class="ptj-chat-send" id="ptj-chat-send" aria-label="Send message">${ICON_SEND}</button>
    </div>
    <div class="ptj-chat-footer">
      <small>Responses based on current database</small>
      <button class="ptj-chat-clear" id="ptj-chat-clear">Clear chat</button>
    </div>
  `;

  document.body.appendChild(toggleBtn);
  document.body.appendChild(panel);

  /* ── References ────────────────────────────────────────────────── */
  const messagesEl = panel.querySelector("#ptj-chat-messages");
  const inputEl = panel.querySelector("#ptj-chat-input");
  const sendBtn = panel.querySelector("#ptj-chat-send");
  const clearBtn = panel.querySelector("#ptj-chat-clear");
  const closeBtn = panel.querySelector(".ptj-chat-close");

  /* ── State ─────────────────────────────────────────────────────── */
  let isOpen = false;
  let isSending = false;
  let history = []; // { role, content }

  /* ── Helpers ───────────────────────────────────────────────────── */
  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  };

  const addBubble = (text, className) => {
    const div = document.createElement("div");
    div.className = `ptj-msg ${className}`;
    div.textContent = text;
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  };

  const showTyping = () => {
    const div = document.createElement("div");
    div.className = "ptj-typing";
    div.id = "ptj-typing-indicator";
    div.innerHTML = "<span></span><span></span><span></span>";
    messagesEl.appendChild(div);
    scrollToBottom();
  };

  const hideTyping = () => {
    const el = document.getElementById("ptj-typing-indicator");
    if (el) el.remove();
  };

  const saveHistory = () => {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(history));
    } catch {
      /* quota exceeded — ignore */
    }
  };

  const loadHistory = () => {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (raw) {
        history = JSON.parse(raw);
        history.forEach((msg) => {
          addBubble(
            msg.content,
            msg.role === "user" ? "ptj-msg-user" : "ptj-msg-assistant"
          );
        });
      }
    } catch {
      history = [];
    }
  };

  const showWelcome = () => {
    if (history.length === 0) {
      addBubble(
        "Hey there! I'm Ace, your tennis job assistant. " +
          "I have the full database at my fingertips.\n\n" +
          "Try asking things like:\n" +
          '  "What jobs are available in Florida?"\n' +
          '  "Which roles have the highest fit score?"\n' +
          '  "Are there any head coach positions?"',
        "ptj-msg-welcome"
      );
    }
  };

  /* ── Toggle panel ──────────────────────────────────────────────── */
  const openPanel = () => {
    isOpen = true;
    panel.classList.add("is-open");
    toggleBtn.innerHTML = ICON_CLOSE;
    toggleBtn.setAttribute("aria-label", "Close chat assistant");
    inputEl.focus();
  };

  const closePanel = () => {
    isOpen = false;
    panel.classList.remove("is-open");
    toggleBtn.innerHTML = ICON_CHAT;
    toggleBtn.setAttribute("aria-label", "Open chat assistant");
  };

  toggleBtn.addEventListener("click", () => {
    isOpen ? closePanel() : openPanel();
  });
  closeBtn.addEventListener("click", closePanel);

  /* ── Send message ──────────────────────────────────────────────── */
  const sendMessage = async () => {
    const text = inputEl.value.trim();
    if (!text || isSending) return;

    isSending = true;
    sendBtn.disabled = true;
    inputEl.value = "";
    inputEl.style.height = "auto";

    // Add user bubble
    addBubble(text, "ptj-msg-user");
    history.push({ role: "user", content: text });

    // Trim history if too long
    if (history.length > MAX_HISTORY) {
      history = history.slice(-MAX_HISTORY);
    }
    saveHistory();

    showTyping();

    try {
      const response = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
      });

      hideTyping();

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || "Something went wrong.");
      }

      const data = await response.json();
      const reply = (data.response || "").trim();

      if (reply) {
        // Strip citation annotations like 【4:0†source】
        const clean = reply.replace(/【[^】]*】/g, "").trim();
        addBubble(clean, "ptj-msg-assistant");
        history.push({ role: "assistant", content: clean });
        saveHistory();
      }
    } catch (err) {
      hideTyping();
      addBubble(
        "Sorry, I couldn't get a response right now. " + (err.message || "Please try again."),
        "ptj-msg-assistant"
      );
    } finally {
      isSending = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  };

  sendBtn.addEventListener("click", sendMessage);

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + "px";
  });

  /* ── Clear chat ────────────────────────────────────────────────── */
  clearBtn.addEventListener("click", () => {
    history = [];
    sessionStorage.removeItem(SESSION_KEY);
    messagesEl.innerHTML = "";
    showWelcome();
  });

  /* ── Init ──────────────────────────────────────────────────────── */
  // Always start fresh — no persisted history on page load
  sessionStorage.removeItem(SESSION_KEY);
  showWelcome();
})();
