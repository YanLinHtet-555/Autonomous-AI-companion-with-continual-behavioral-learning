/**
 * app.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Chat UI for Neon AI Companion.
 *
 * WebSocket protocol (JSON):
 *   INCOMING — { type: "message", role: "neon", content, emotion }
 *              { type: "proactive", content, emotion }
 *              { type: "typing", active: bool }
 *              { type: "status", level, experiences }
 *   OUTGOING — { type: "message", content }
 *
 * Responsibilities:
 *   • Manage WebSocket lifecycle with auto-reconnect
 *   • Render messages with typewriter effect for Neon's messages
 *   • Delegate emotion/level changes to neon-char.js
 *   • Keep status bar in sync
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { initNeon } from './neon-char.js';

// ── DOM references ────────────────────────────────────────────────────────────
const canvas        = document.getElementById('three-canvas');
const messagesEl    = document.getElementById('messages');
const typingEl      = document.getElementById('typing-indicator');
const inputEl       = document.getElementById('input');
const sendBtn       = document.getElementById('send-btn');
const statusText    = document.getElementById('status-text');
const statusDot     = document.getElementById('status-dot');
const connBadge     = document.getElementById('connection-badge');
const levelBadgeEl  = document.getElementById('neon-level-badge');

// ── Initialise the Three.js character ─────────────────────────────────────────
const neon = initNeon(canvas);

// ── State ──────────────────────────────────────────────────────────────────────
let socket            = null;
let reconnectTimer    = null;
let reconnectAttempts = 0;
const MAX_RECONNECT   = Infinity;   // keep trying forever
const BASE_DELAY_MS   = 1500;
const MAX_DELAY_MS    = 30000;

let currentLevel      = 'baby';
let currentExperiences = 0;

// Used to cancel any in-progress typewriter before the next message
let typewriterAbort = null;

// ── WebSocket connection ──────────────────────────────────────────────────────

const WS_URL = 'ws://localhost:8000/ws';

function connect() {
  clearTimeout(reconnectTimer);

  // Don't open if already open or connecting
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  setConnectionState('reconnecting');

  socket = new WebSocket(WS_URL);

  socket.addEventListener('open', () => {
    reconnectAttempts = 0;
    setConnectionState('connected');
  });

  socket.addEventListener('message', event => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      console.warn('[Neon] Received non-JSON message:', event.data);
      return;
    }
    handleIncoming(msg);
  });

  socket.addEventListener('close', () => {
    setConnectionState('disconnected');
    scheduleReconnect();
  });

  socket.addEventListener('error', () => {
    // The 'close' event fires right after, so reconnect is handled there.
  });
}

function scheduleReconnect() {
  reconnectAttempts++;
  // Exponential back-off capped at MAX_DELAY_MS
  const delay = Math.min(BASE_DELAY_MS * Math.pow(1.5, reconnectAttempts - 1), MAX_DELAY_MS);
  reconnectTimer = setTimeout(connect, delay);
}

function setConnectionState(state) {
  // state: 'connected' | 'disconnected' | 'reconnecting'
  statusDot.className   = state === 'connected' ? 'connected' : '';
  connBadge.className   = state;
  connBadge.textContent = state === 'connected'    ? 'ONLINE'
                        : state === 'reconnecting' ? 'RECONNECTING…'
                        : 'OFFLINE';
}

// ── Incoming message handler ──────────────────────────────────────────────────

function handleIncoming(msg) {
  switch (msg.type) {

    case 'message': {
      if (msg.role === 'neon' || !msg.role) {
        const emotion = msg.emotion || 'idle';
        neon.setEmotion('talking');
        appendNeonMessage(msg.content, false, () => {
          neon.setEmotion(SETTLED_EMOTION[emotion] || 'idle');
        });
      }
      break;
    }

    case 'proactive': {
      const emotion = msg.emotion || 'idle';
      appendProactiveDivider();
      neon.setEmotion('talking');
      appendNeonMessage(msg.content, false, () => {
        neon.setEmotion(SETTLED_EMOTION[emotion] || 'idle');
      });
      break;
    }

    case 'typing': {
      if (msg.active) {
        typingEl.hidden = false;
        neon.setEmotion('thinking');
      } else {
        typingEl.hidden = true;
      }
      scrollToBottom();
      break;
    }

    case 'status': {
      // Level or experience count updated
      if (msg.level)       updateLevel(msg.level);
      if (msg.experiences !== undefined) updateExperiences(msg.experiences);
      break;
    }

    default:
      console.warn('[Neon] Unknown message type:', msg.type);
  }
}

// Maps "arriving" emotion to what to show once the message is fully typed
const SETTLED_EMOTION = {
  idle:     'idle',
  happy:    'idle',
  thinking: 'idle',
  excited:  'idle',
  talking:  'idle',
  sleepy:   'sleepy',
};

// ── Outgoing messages ─────────────────────────────────────────────────────────

function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  // Disable input while sending
  inputEl.disabled = true;
  sendBtn.disabled = true;

  // Render user bubble immediately
  appendUserMessage(text);

  // Clear input
  inputEl.value = '';
  autoResizeInput();

  // Send over WebSocket if connected
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'message', content: text }));
  } else {
    // Not connected — show a local offline notice
    setTimeout(() => {
      appendNeonMessage('I\'m not connected right now. Reconnecting…', false, null);
    }, 300);
  }

  inputEl.disabled = false;
  sendBtn.disabled = false;
  inputEl.focus();
}

// ── Message rendering ─────────────────────────────────────────────────────────

/**
 * Insert a "Neon started chatting" divider for proactive messages.
 */
function appendProactiveDivider() {
  const div = document.createElement('div');
  div.className = 'proactive-divider';
  div.textContent = 'Neon started chatting';
  messagesEl.appendChild(div);
  scrollToBottom();
}

/**
 * Append a user message bubble (right-aligned, instant).
 * @param {string} content
 */
function appendUserMessage(content) {
  const row    = document.createElement('div');
  row.className = 'message-row user-row';

  const dot    = document.createElement('span');
  dot.className = 'avatar-dot user-dot';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = content;

  row.append(dot, bubble);
  messagesEl.appendChild(row);
  scrollToBottom();
}

/**
 * Append a Neon message with a typewriter reveal effect.
 * @param {string} content       — full message text
 * @param {boolean} instant      — skip typewriter if true
 * @param {Function|null} onDone — callback when typewriter finishes
 */
function appendNeonMessage(content, instant = false, onDone = null) {
  // Hide the typing indicator when a message arrives
  typingEl.hidden = true;

  // Abort any in-progress typewriter
  if (typewriterAbort) {
    typewriterAbort();
    typewriterAbort = null;
  }

  const row    = document.createElement('div');
  row.className = 'message-row neon-row';

  const dot    = document.createElement('span');
  dot.className = 'avatar-dot neon-dot';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  row.append(dot, bubble);
  messagesEl.appendChild(row);
  scrollToBottom();

  if (instant || !content) {
    bubble.textContent = content;
    if (onDone) onDone();
    return;
  }

  // Typewriter effect — ~30ms per character
  bubble.classList.add('typing-active');
  let index = 0;
  let aborted = false;

  typewriterAbort = () => {
    aborted = true;
    bubble.classList.remove('typing-active');
    bubble.textContent = content;  // snap to full content on abort
  };

  function typeNext() {
    if (aborted) return;
    if (index < content.length) {
      bubble.textContent = content.slice(0, index + 1);
      index++;
      scrollToBottom();
      setTimeout(typeNext, 28 + Math.random() * 10); // slight jitter feels natural
    } else {
      // Done
      bubble.classList.remove('typing-active');
      typewriterAbort = null;
      if (onDone) onDone();
    }
  }

  // Small delay so the bubble renders before typing starts
  setTimeout(typeNext, 80);
}

// ── Status / level helpers ────────────────────────────────────────────────────

function updateLevel(level) {
  currentLevel = level;
  neon.setLevel(level);
  document.body.dataset.level = level;

  const label = level.toUpperCase();
  levelBadgeEl.textContent = label;
  refreshStatusBar();
}

function updateExperiences(n) {
  currentExperiences = n;
  refreshStatusBar();
}

function refreshStatusBar() {
  const label = currentLevel.toUpperCase();
  statusText.textContent = `Neon · ${label} · ${currentExperiences} memories`;
}

// ── Input behaviour ───────────────────────────────────────────────────────────

// Auto-resize the textarea to fit content (up to CSS max-height)
function autoResizeInput() {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
}

inputEl.addEventListener('input', autoResizeInput);

// Enter = send, Shift+Enter = newline
inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener('click', sendMessage);

// ── Scroll helper ─────────────────────────────────────────────────────────────

function scrollToBottom() {
  // Use requestAnimationFrame to let the DOM update first
  requestAnimationFrame(() => {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}

// ── Welcome message (shown before WebSocket connects) ────────────────────────

function showWelcomeMessage() {
  appendNeonMessage(
    'Connecting to Neon… I\'ll be right with you.',
    false,
    null
  );
}

// ── Initialise ────────────────────────────────────────────────────────────────

showWelcomeMessage();
connect();

// Refresh status bar with initial values
refreshStatusBar();

neon.setEmotion('idle');
