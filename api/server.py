"""
FastAPI server — the AI brain that runs inside Docker.

Endpoints:
  POST /chat          Send a message, get a response
  POST /events        Monitoring agent pushes activity events here
  POST /train         Trigger a training session
  POST /study         Start/end a study session
  POST /share         Share notes for co-learning
  GET  /stats         Memory and training stats
  GET  /ai-log        Recent AI autonomous actions
  GET  /health        Health check
  WS   /ws            WebSocket for the 3D UI (bidirectional chat with Neon)
  GET  /              Serves ui/index.html

The monitoring_agent.py on the host machine calls these endpoints.
All data stays on localhost — nothing goes to the internet
(NetworkGuard blocks all outbound connections inside the container too).
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Activate network guard before anything else
from security import activate_network_guard
activate_network_guard()

import asyncio
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List, Set
import uvicorn

from config import MODEL, TRAINING, MEMORY, PRIVACY, SECURITY, DEVICE
from model.transformer import CompanionModel
from model.tokenizer import BPETokenizer
from model.trainer import Trainer
from memory.experience_buffer import ExperienceBuffer
from memory.vector_store import VectorStore
from memory.encryption import EncryptionManager
from learning.continual_learner import ContinualLearner
from learning.co_learner import CoLearner
from learning.lora import inject_lora
from learning.scheduler import LearningScheduler
from summarizer.event_summarizer import EventSummarizer
from companion.chat import Chat
from companion.level_system import LevelSystem
from companion.persona import get_system_prompt, get_proactive_message
from companion.proactive_engine import ProactiveEngine
from companion.feedback_collector import FeedbackCollector
from privacy.consent_manager import ConsentManager
from security.audit_log import AuditLog
from security.ai_action_logger import AIActionLogger
from security.data_access_gate import DataAccessGate

app = FastAPI(
    title="AI Companion",
    description="Local self-learning AI — data never leaves this machine",
    version="1.0.0",
)

# Only allow requests from localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the UI from /ui path and root
_UI_DIR = os.path.join(BASE_DIR, "ui")
if os.path.isdir(_UI_DIR):
    app.mount("/ui", StaticFiles(directory=_UI_DIR), name="ui")


@app.get("/")
def serve_ui():
    index = os.path.join(_UI_DIR, "index.html")
    if os.path.exists(index):
        return RedirectResponse(url="/ui/index.html")
    return {"message": "AI Companion API running. UI not found."}


# ── WebSocket connection manager ─────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._active.add(ws)

    def disconnect(self, ws: WebSocket):
        self._active.discard(ws)

    async def send(self, ws: WebSocket, payload: dict):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            self.disconnect(ws)

    async def broadcast(self, payload: dict):
        dead = set()
        for ws in list(self._active):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.add(ws)
        self._active -= dead


_manager = ConnectionManager()


# ── Global system components (loaded at startup) ─────────────────────────────
_components: dict = {}


@app.on_event("startup")
async def startup():
    print("[Server] Loading AI Companion...")

    audit = AuditLog(SECURITY["audit_log_path"], SECURITY["audit_key_path"])
    ai_logger = AIActionLogger(audit_log=audit)
    data_gate = DataAccessGate(audit_log=audit, ai_logger=ai_logger)
    encryption = EncryptionManager(MEMORY["encryption_key_path"])

    buffer = ExperienceBuffer(
        MEMORY["db_path"], encryption=encryption,
        data_gate=data_gate, ai_logger=ai_logger,
    )
    vector_store = VectorStore(MEMORY["vector_index_path"], MEMORY["embed_dim"])

    tokenizer = BPETokenizer()
    tok_path = TRAINING["tokenizer_path"]
    if not os.path.exists(tok_path):
        raise RuntimeError("Tokenizer not found. Run setup.py first.")
    tokenizer.load(tok_path)

    model = CompanionModel(vocab_size=tokenizer.vocab_size, **MODEL).to(DEVICE)
    trainer = Trainer(model, tokenizer, device=DEVICE,
                      lr=TRAINING["lr"],
                      checkpoint_dir=TRAINING["checkpoint_dir"])
    trainer.load_checkpoint("latest")
    model, _ = inject_lora(model, rank=8, alpha=16.0)

    co_learner = CoLearner(buffer, ai_logger=ai_logger)
    summarizer = EventSummarizer()

    level_system = LevelSystem(MEMORY["level_path"], ai_logger=ai_logger)

    learner = ContinualLearner(
        model, trainer, buffer,
        ewc_lambda=TRAINING["ewc_lambda"],
        replay_ratio=TRAINING["replay_ratio"],
        device=DEVICE,
        ai_logger=ai_logger,
        level_system=level_system,
        get_study_minutes=co_learner.get_total_study_minutes,
    )
    scheduler = LearningScheduler(
        learner, buffer, summarizer, monitor_manager=None,
        train_hour=2,
        min_samples=TRAINING["min_texts_to_train"],
        ai_logger=ai_logger,
        data_gate=data_gate,
    )
    scheduler.start()

    chat = Chat(model, tokenizer, buffer, vector_store, device=DEVICE,
                level_system=level_system)
    feedback = FeedbackCollector(buffer)

    async def _proactive_send(content: str, emotion: str = "idle"):
        await _manager.broadcast({
            "type": "proactive",
            "content": content,
            "emotion": emotion,
        })

    proactive = ProactiveEngine(
        send_fn=_proactive_send,
        level_system=level_system,
        idle_threshold_sec=600,
        check_interval_sec=60,
    )
    proactive.start()

    _components.update({
        "chat": chat, "feedback": feedback, "buffer": buffer,
        "vector_store": vector_store, "learner": learner,
        "scheduler": scheduler, "summarizer": summarizer,
        "co_learner": co_learner, "level_system": level_system,
        "proactive": proactive,
        "audit": audit, "ai_logger": ai_logger,
    })

    audit.record("SERVER_START", f"API server started on {DEVICE}", severity="LOW")
    print(f"[Server] Ready — device={DEVICE} "
          f"experiences={buffer.stats()['total']}")


@app.on_event("shutdown")
async def shutdown():
    _components.get("proactive") and _components["proactive"].stop()
    _components.get("scheduler", None) and _components["scheduler"].stop()
    _components.get("audit") and _components["audit"].record(
        "SERVER_STOP", "Clean shutdown", severity="LOW"
    )


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    temperature: float = 0.8
    max_tokens: int = 200

class ChatResponse(BaseModel):
    response: str
    session_experiences: int

class EventBatch(BaseModel):
    events: List[dict]

class StudyRequest(BaseModel):
    topic: str
    action: str = "start"   # "start" or "end"

class ShareRequest(BaseModel):
    topic: str
    content: str

class FeedbackRequest(BaseModel):
    type: str          # "approve", "reject", "correct"
    correction: Optional[str] = None

class TrainRequest(BaseModel):
    force: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    stats = _components["buffer"].stats()
    return {
        "status": "ok",
        "device": DEVICE,
        "experiences": stats["total"],
        "network": "blocked",
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Empty message")
    response = _components["chat"].respond(
        req.message,
        temperature=req.temperature,
        max_new_tokens=req.max_tokens,
    )
    stats = _components["buffer"].stats()
    return ChatResponse(
        response=response,
        session_experiences=stats["total"],
    )


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    fb = _components["feedback"]
    if req.type == "approve":
        fb.submit_approval()
    elif req.type == "reject":
        fb.submit_rejection()
    elif req.type == "correct" and req.correction:
        fb.submit_correction(req.correction)
    else:
        raise HTTPException(400, "Invalid feedback type")
    return {"status": "ok"}


@app.post("/events")
def ingest_events(batch: EventBatch):
    """
    Called by monitoring_agent.py on the host.
    Pushes activity events into the summarizer for tonight's training.
    """
    summarizer = _components["summarizer"]
    ai_logger = _components["ai_logger"]
    for event in batch.events:
        summarizer.ingest(event)

        # If learning session detected on host, notify co-learner
        if event.get("type") in ("learning_session", "study_session_started"):
            _components["co_learner"].on_learning_session(event)

    if batch.events:
        ai_logger.data_write("event_queue", len(batch.events))

    return {"status": "ok", "ingested": len(batch.events)}


@app.post("/train")
def trigger_training(req: TrainRequest):
    _components["scheduler"].trigger_now()
    return {"status": "training session triggered"}


@app.post("/study")
def study(req: StudyRequest):
    co = _components["co_learner"]
    if req.action == "start":
        co.on_learning_session({
            "type": "study_session_started",
            "topic": req.topic,
            "duration_sec": 0,
            "manual": True,
        })
        return {"status": "study session started", "topic": req.topic}
    else:
        return {"status": "session noted", "topic": req.topic}


@app.post("/share")
def share(req: ShareRequest):
    concepts = _components["co_learner"].share_content(req.topic, req.content)
    return {"status": "ok", "concepts_extracted": concepts}


@app.get("/stats")
def stats():
    buf_stats = _components["buffer"].stats()
    learner = _components["learner"]
    co = _components["co_learner"]
    ls = _components["level_system"]
    experiences = buf_stats["total"]
    study_min = co.get_total_study_minutes()
    return {
        "memory": buf_stats,
        "learning": learner.get_learning_summary(),
        "total_study_minutes": study_min,
        "topics_studied": co.get_all_topics(),
        "level": ls.current_level,
        "level_status": ls.format_status(),
        "level_progress": ls.get_progress(experiences, learner.training_sessions, study_min),
    }


@app.get("/level")
def level():
    ls = _components["level_system"]
    co = _components["co_learner"]
    learner = _components["learner"]
    buf = _components["buffer"]
    experiences = buf.stats()["total"]
    study_min = co.get_total_study_minutes()
    return {
        "current": ls.current_level,
        "status": ls.format_status(),
        "all_levels": ls.all_levels_info(),
        "progress": ls.get_progress(experiences, learner.training_sessions, study_min),
    }


@app.get("/ai-log")
def ai_log(n: int = 20):
    return {"entries": _components["ai_logger"].get_recent(n)}


@app.get("/learning-stats")
def learning_stats(topic: str = None):
    return {"summary": _components["co_learner"].get_study_summary(topic)}


# ── WebSocket — real-time chat with Neon ─────────────────────────────────────

_last_ws_greeting: Optional[datetime] = None   # rate-limit: one greeting per hour max


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _last_ws_greeting
    await _manager.connect(ws)
    ls = _components.get("level_system")
    buf = _components.get("buffer")
    proactive = _components.get("proactive")

    # Send initial status so the UI can render Neon's current level/appearance
    if ls and buf:
        await _manager.send(ws, {
            "type": "status",
            "level": ls.current_level,
            "experiences": buf.stats().get("total", 0),
        })

    # Greet only on the first connection or after >1 h of silence
    now = datetime.now()
    if _last_ws_greeting is None or (now - _last_ws_greeting).total_seconds() > 3600:
        _last_ws_greeting = now
        period = "morning" if 6 <= now.hour < 17 else "evening"
        greeting = get_proactive_message(period, ls.current_level if ls else "adult")
        await _manager.send(ws, {
            "type": "proactive",
            "content": greeting,
            "emotion": "happy",
        })

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("type") != "message":
                continue

            user_text = (data.get("content") or "").strip()
            if not user_text:
                continue

            # Notify proactive engine the user is active
            if proactive:
                proactive.on_user_message()

            # Typing indicator
            await _manager.send(ws, {"type": "typing", "active": True})

            # Run the (blocking) model generation in a thread pool
            chat = _components["chat"]
            system_prompt = get_system_prompt(ls.current_level if ls else "adult")
            prefixed = f"{system_prompt}\n{user_text}"
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: chat.respond(prefixed, temperature=0.8, max_new_tokens=200),
            )

            # Turn off typing indicator
            await _manager.send(ws, {"type": "typing", "active": False})

            # Determine emotion from response content (simple heuristics)
            emotion = _infer_emotion(response)

            await _manager.send(ws, {
                "type": "message",
                "role": "neon",
                "content": response,
                "emotion": emotion,
            })

            # Update status after each message
            if ls and buf:
                await _manager.send(ws, {
                    "type": "status",
                    "level": ls.current_level,
                    "experiences": buf.stats().get("total", 0),
                })

    except WebSocketDisconnect:
        _manager.disconnect(ws)


def _infer_emotion(text: str) -> str:
    text_lower = text.lower()
    if any(w in text_lower for w in ("sorry", "hmm", "let me think", "not sure", "unclear")):
        return "thinking"
    if any(w in text_lower for w in ("great", "awesome", "yes!", "love", "exciting", "!")):
        return "happy"
    if any(w in text_lower for w in ("tired", "later", "sleep", "night", "rest")):
        return "sleepy"
    return "idle"


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)
