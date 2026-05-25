"""
AI Companion — Main Entry Point

SECURITY NOTE: NetworkGuard is activated on the very first import line.
No outbound network connection can be made after that point
without explicit /allow-network <host> command from you.

Usage:
    python main.py              start the companion
    python main.py --train-now  trigger learning session immediately
    python main.py --stats      show memory stats
    python main.py --audit      show audit log
    python main.py --security   show full security status
"""

import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ── SECURITY FIRST — activate network guard before any other import ──────────
from security import activate_network_guard
activate_network_guard()
# ─────────────────────────────────────────────────────────────────────────────

import torch
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from config import MODEL, TRAINING, MEMORY, MONITORING, PRIVACY, SECURITY, DEVICE
from model.transformer import CompanionModel
from model.tokenizer import BPETokenizer
from model.trainer import Trainer
from monitoring.monitor_manager import MonitorManager
from summarizer.event_summarizer import EventSummarizer
from memory.experience_buffer import ExperienceBuffer
from memory.vector_store import VectorStore
from memory.encryption import EncryptionManager
from learning.continual_learner import ContinualLearner
from learning.co_learner import CoLearner
from learning.lora import inject_lora
from learning.scheduler import LearningScheduler
from companion.chat import Chat
from companion.suggestion_engine import SuggestionEngine
from companion.feedback_collector import FeedbackCollector
from privacy.consent_manager import ConsentManager
from privacy.data_manager import DataManager
from security.audit_log import AuditLog
from security.access_control import AccessControl
from security.breach_detector import BreachDetector
from security.ai_action_logger import AIActionLogger
from security.data_access_gate import DataAccessGate, Mode as GateMode
from security import kill_switch
import security.network_guard as network_guard

console = Console()


def _stop_all(components: dict):
    """Stop all background threads — used by kill switch callback."""
    for key in ("monitor", "scheduler", "suggestions", "breach_detector"):
        obj = components.get(key)
        if obj is None:
            continue
        try:
            if key == "breach_detector":
                obj.stop_realtime()
            else:
                obj.stop()
        except Exception:
            pass


def load_system():
    console.print("[bold cyan]Loading AI Companion...[/bold cyan]")

    # ── 1. Security layer ────────────────────────────────────────────────
    audit = AuditLog(
        log_path=SECURITY["audit_log_path"],
        key_path=SECURITY["audit_key_path"],
    )
    network_guard._audit_callback = audit.callback

    ai_logger = AIActionLogger(
        audit_log=audit,
        print_callback=lambda msg: console.print(msg),
    )

    # DataAccessGate — only gates EXTERNAL operations (export, share).
    # Local learning, training, monitoring are always permitted.
    data_gate = DataAccessGate(audit_log=audit, ai_logger=ai_logger)

    access_ctrl = AccessControl(audit_log=audit)

    breach_detector = BreachDetector(
        watch_paths=SECURITY["protected_files"],
        manifest_path=SECURITY["breach_manifest_path"],
        audit_log=audit,
    )
    breach_detector.startup_check()
    breach_detector.start_realtime()

    audit.record("SYSTEM_START", "AI Companion starting up", severity="LOW")

    # ── 2. Privacy / consent ─────────────────────────────────────────────
    consent = ConsentManager(PRIVACY["consent_path"])
    if not consent.has_consented():
        console.print("[yellow]Run 'python setup.py' first.[/yellow]")
        sys.exit(1)

    # ── 3. Encryption ────────────────────────────────────────────────────
    encryption = EncryptionManager(MEMORY["encryption_key_path"])
    audit.record("ENCRYPTION_READY", "AES-256-CBC + PBKDF2 active", severity="LOW")

    # ── 4. Memory ────────────────────────────────────────────────────────
    buffer = ExperienceBuffer(
        MEMORY["db_path"],
        encryption=encryption,
        data_gate=data_gate,
        ai_logger=ai_logger,
    )
    vector_store = VectorStore(MEMORY["vector_index_path"], MEMORY["embed_dim"])
    breach_detector.update_manifest()

    # ── 5. Model ─────────────────────────────────────────────────────────
    tokenizer = BPETokenizer()
    if not os.path.exists(TRAINING["tokenizer_path"]):
        console.print("[red]Tokenizer not found. Run 'python setup.py' first.[/red]")
        sys.exit(1)
    tokenizer.load(TRAINING["tokenizer_path"])
    ai_logger.checkpoint_loaded("tokenizer")

    model = CompanionModel(vocab_size=tokenizer.vocab_size, **MODEL).to(DEVICE)
    trainer = Trainer(model, tokenizer, device=DEVICE,
                      lr=TRAINING["lr"],
                      checkpoint_dir=TRAINING["checkpoint_dir"])
    loaded = trainer.load_checkpoint("latest")
    if loaded:
        ai_logger.checkpoint_loaded("latest")
    else:
        console.print("[yellow]No checkpoint — run setup.py first.[/yellow]")
    model, _ = inject_lora(model, rank=8, alpha=16.0)

    # ── 6. Co-learning engine (created before monitor so monitor can reference it) ──
    co_learner = CoLearner(buffer, ai_logger=ai_logger)

    # ── 7. Monitoring ────────────────────────────────────────────────────
    privacy_cfg = consent.as_dict()
    summarizer = EventSummarizer()
    monitor = MonitorManager(
        MONITORING, privacy_cfg,
        on_event=summarizer.ingest,
        co_learner=co_learner,
    )

    # ── 7. Learning ──────────────────────────────────────────────────────
    learner = ContinualLearner(
        model, trainer, buffer,
        ewc_lambda=TRAINING["ewc_lambda"],
        replay_ratio=TRAINING["replay_ratio"],
        device=DEVICE,
        ai_logger=ai_logger,
    )
    scheduler = LearningScheduler(
        learner, buffer, summarizer, monitor,
        train_hour=2,
        min_samples=TRAINING["min_texts_to_train"],
        ai_logger=ai_logger,
        data_gate=data_gate,
    )

    # ── 8. Companion ─────────────────────────────────────────────────────
    chat = Chat(model, tokenizer, buffer, vector_store, device=DEVICE)
    feedback = FeedbackCollector(buffer)
    suggestions = SuggestionEngine(
        monitor, buffer,
        check_interval=300,
        on_suggestion=lambda s: (
            ai_logger.suggestion_made(s),
            console.print(Panel(
                f"[bold yellow]AI Suggestion:[/bold yellow] {s}",
                border_style="yellow",
            ))
        ),
    )
    data_mgr = DataManager(buffer, vector_store)

    audit.record("SYSTEM_READY", "All subsystems loaded", severity="LOW")
    console.print("[green]System ready.[/green]")
    console.print("[green]System ready.[/green]")

    components = {
        "model": model, "tokenizer": tokenizer, "trainer": trainer,
        "buffer": buffer, "vector_store": vector_store,
        "monitor": monitor, "summarizer": summarizer,
        "learner": learner, "scheduler": scheduler,
        "co_learner": co_learner,
        "chat": chat, "feedback": feedback, "suggestions": suggestions,
        "consent": consent, "data_mgr": data_mgr,
        "audit": audit, "access_ctrl": access_ctrl,
        "ai_logger": ai_logger, "data_gate": data_gate,
        "breach_detector": breach_detector,
    }
    return components


# ─────────────────────────────────────────────────────────────────────────────

def run_chat(c: dict):
    chat       = c["chat"]
    feedback   = c["feedback"]
    learner    = c["learner"]
    data_mgr   = c["data_mgr"]
    audit      = c["audit"]
    access     = c["access_ctrl"]
    ai_log     = c["ai_logger"]
    gate       = c["data_gate"]
    co_learner = c["co_learner"]
    monitor    = c["monitor"]

    console.print(Panel(
        Text.from_markup(
            "[bold green]AI Companion[/bold green]\n\n"
            "[dim]Watching, learning, and growing alongside you — locally only.[/dim]\n\n"
            "[cyan]Chat & feedback:[/cyan]\n"
            "  /approve / /reject          Feedback on last response\n"
            "  /correct <text>             Teach the AI the right answer\n"
            "  /history                    Last 5 exchanges\n\n"
            "[bold cyan]Co-learning (AI learns with you):[/bold cyan]\n"
            "  /study <topic>              Start a named study session\n"
            "  /study end                  End current study session\n"
            "  /share <topic> | <content>  Share notes/text for AI to learn\n"
            "  /quiz <topic>               AI quizzes you on a studied topic\n"
            "  /explain <concept>          AI explains a concept from your notes\n"
            "  /review <topic>             AI summarises what you learned together\n"
            "  /learning-log               All study sessions so far\n"
            "  /learning-stats             Study time per topic\n\n"
            "[cyan]Self-improvement:[/cyan]\n"
            "  /train                      Trigger AI self-training now\n"
            "  /stats                      Memory + training stats\n\n"
            "[yellow]Transparency:[/yellow]\n"
            "  /ai-log                     Everything AI did in background\n"
            "  /audit                      Full encrypted audit trail\n"
            "  /security                   Network + breach detector status\n"
            "  /gate-status                Data release gate status\n\n"
            "[yellow]Data release (blocked by default):[/yellow]\n"
            "  /permit <op>                Allow a pending export/share\n"
            "  /deny <op>                  Block a pending export/share\n"
            "  /allow-network <host>       Unlock one host (10 min)\n\n"
            "[bold red]Emergency:[/bold red]\n"
            "  /killswitch                 Wipe ALL data + keys (irreversible)\n"
            "  /wipe-data                  Wipe memory only, keep model\n\n"
            "  [dim]/privacy  /quit[/dim]"
        ),
        title="AI Companion — Local & Private", border_style="green"
    ))

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # ── quit ──────────────────────────────────────────────────────────
        if cmd in ("/quit", "/exit", "/q"):
            audit.record("SYSTEM_STOP", "User quit", severity="LOW")
            break

        # ── learning ──────────────────────────────────────────────────────
        elif cmd == "/train":
            console.print("[cyan]Triggering learning session...[/cyan]")
            c["scheduler"].trigger_now()

        elif cmd == "/stats":
            data_mgr.show_stats()
            console.print(f"[dim]{learner.get_learning_summary()}[/dim]")

        # ── feedback ──────────────────────────────────────────────────────
        elif cmd == "/approve":
            feedback.submit_approval()
            console.print("[green]Approved — reinforced.[/green]")

        elif cmd == "/reject":
            feedback.submit_rejection()
            console.print("[red]Rejected — noted.[/red]")

        elif cmd.startswith("/correct "):
            feedback.submit_correction(user_input[9:].strip())

        elif cmd == "/history":
            for u, a in chat.get_history()[-5:]:
                console.print(f"[dim]You:[/dim] {u}")
                console.print(f"[dim]AI :[/dim] {a}\n")

        # ── co-learning ───────────────────────────────────────────────────
        elif cmd.startswith("/study "):
            topic = user_input[7:].strip()
            if topic.lower() == "end":
                monitor.learning_detector.end_study_session()
                console.print("[cyan]Study session ended.[/cyan]")
            else:
                monitor.learning_detector.start_study_session(topic)
                console.print(
                    Panel(
                        f"[bold cyan]Study session started: {topic}[/bold cyan]\n"
                        f"The AI is learning this topic alongside you.\n"
                        f"Use [bold]/share {topic} | your notes[/bold] to share content.\n"
                        f"Use [bold]/study end[/bold] when you're done.",
                        border_style="cyan",
                    )
                )

        elif cmd.startswith("/share "):
            rest = user_input[7:].strip()
            if "|" in rest:
                topic, content = rest.split("|", 1)
                topic = topic.strip()
                content = content.strip()
            else:
                topic = monitor.learning_detector.get_current_topic() or "general"
                content = rest
            if content:
                concepts = co_learner.share_content(topic, content)
                console.print(
                    f"[cyan]Shared with AI for topic '[bold]{topic}[/bold]'.[/cyan]"
                )
                if concepts:
                    console.print(
                        f"[dim]Key concepts extracted: {', '.join(concepts[:8])}[/dim]"
                    )
            else:
                console.print("[yellow]Usage: /share <topic> | <your notes>[/yellow]")

        elif cmd.startswith("/quiz "):
            topic = user_input[6:].strip()
            prompt = co_learner.build_quiz_prompt(topic)
            if "No recorded study" in co_learner.get_study_summary(topic):
                console.print(
                    f"[yellow]No study sessions found for '{topic}'. "
                    f"Start with /study {topic}[/yellow]"
                )
            else:
                response = chat._generate(prompt, temperature=0.9, max_new_tokens=200)
                console.print(
                    Panel(
                        f"[bold cyan]Quiz — {topic}[/bold cyan]\n\n{response}",
                        border_style="cyan",
                    )
                )

        elif cmd.startswith("/explain "):
            concept = user_input[9:].strip()
            current_topic = monitor.learning_detector.get_current_topic()
            prompt = co_learner.build_explain_prompt(concept, current_topic or "")
            response = chat._generate(prompt, temperature=0.7, max_new_tokens=300)
            console.print(
                Panel(
                    f"[bold cyan]{concept}[/bold cyan]\n\n{response}",
                    border_style="cyan",
                )
            )

        elif cmd.startswith("/review "):
            topic = user_input[8:].strip()
            summary = co_learner.get_study_summary(topic)
            console.print(f"[dim]{summary}[/dim]\n")
            prompt = co_learner.build_review_prompt(topic)
            response = chat._generate(prompt, temperature=0.7, max_new_tokens=300)
            console.print(
                Panel(
                    f"[bold cyan]Review: {topic}[/bold cyan]\n\n{response}",
                    border_style="cyan",
                )
            )

        elif cmd == "/learning-log":
            sessions = monitor.learning_detector.get_session_log(limit=20)
            if not sessions:
                console.print("[dim]No study sessions recorded yet.[/dim]")
            else:
                console.print("\n[bold cyan]Study Session Log:[/bold cyan]")
                for s in sessions:
                    ts = s["timestamp"][:16]
                    dur = round(s.get("duration_sec", 0) / 60, 1)
                    topic = s.get("topic", "?")
                    console.print(f"  [{ts}]  {dur:5.1f} min  {topic}")
            current = monitor.learning_detector.get_current_topic()
            if current:
                console.print(f"\n  [cyan]Currently studying: {current}[/cyan]")

        elif cmd == "/learning-stats":
            console.print(f"\n[bold cyan]Learning Stats:[/bold cyan]")
            console.print(co_learner.get_study_summary())
            today_min = monitor.learning_detector.total_study_time_today()
            total_min = co_learner.get_total_study_minutes()
            console.print(
                f"\n  Today       : {today_min:.1f} minutes\n"
                f"  All time    : {total_min:.1f} minutes"
            )

        # ── privacy ───────────────────────────────────────────────────────
        elif cmd == "/privacy":
            c["consent"].show()

        # ── security status ───────────────────────────────────────────────
        elif cmd == "/security":
            network_guard.status()
            console.print(f"[dim]Audit stats: {audit.get_stats()}[/dim]")
            console.print(f"[dim]Suspicious events: {ai_log.get_suspicious_count()}[/dim]")
            gate.show_status()
            audit.record("SECURITY_STATUS_VIEWED", "user viewed security status",
                         severity="LOW")

        elif cmd == "/audit":
            audit.show(last_n=30, min_severity="LOW")

        elif cmd == "/audit high":
            audit.show(last_n=50, min_severity="HIGH")

        elif cmd == "/ai-log":
            ai_log.show(n=30)

        elif cmd == "/ai-log suspicious":
            ai_log.show(n=30, action_type="SUSPICIOUS")

        # ── data release gate (export / share only) ───────────────────────
        elif cmd == "/gate-status":
            gate.show_status()

        elif cmd.startswith("/permit-session "):
            op = user_input[16:].strip()
            gate.permit(op, session_wide=True)

        elif cmd.startswith("/permit "):
            op = user_input[8:].strip()
            gate.permit(op, session_wide=False)

        elif cmd.startswith("/deny "):
            op = user_input[6:].strip()
            gate.deny(op)

        # ── network control ───────────────────────────────────────────────
        elif cmd.startswith("/allow-network "):
            host = user_input[15:].strip()
            if host:
                network_guard.allow_host(host, duration_minutes=10)
                audit.record("USER_NETWORK_UNLOCK", f"host={host}", severity="MEDIUM")

        elif cmd.startswith("/block-network "):
            host = user_input[15:].strip()
            if host:
                network_guard.revoke_host(host)
                audit.record("USER_NETWORK_BLOCK", f"host={host}", severity="LOW")

        # ── access control tokens ─────────────────────────────────────────
        elif cmd.startswith("/authorize "):
            operation = user_input[11:].strip()
            token = access.request_token(operation, ttl_seconds=60)
            if token != "not_required":
                console.print(f"[yellow]Token: [bold]{token}[/bold] (60s)[/yellow]")

        elif cmd.startswith("/confirm "):
            parts = user_input[9:].strip().split(maxsplit=1)
            if len(parts) == 2:
                token, operation = parts
                granted = access.authorize(token, operation)
                if granted and operation == "delete_all":
                    data_mgr.delete_all(confirm=True)
                    audit.record("DATA_DELETED_ALL", "user deleted all data",
                                 severity="HIGH")

        # ── KILL SWITCH ───────────────────────────────────────────────────
        elif cmd == "/killswitch":
            console.print(
                Panel(
                    "[bold red]KILL SWITCH[/bold red]\n\n"
                    "This will [bold]permanently and irreversibly[/bold] destroy:\n"
                    "  • All stored experiences and conversations\n"
                    "  • All encryption keys (ciphertext becomes unreadable)\n"
                    "  • All model checkpoints\n"
                    "  • All audit logs\n"
                    "  • All consent and privacy settings\n\n"
                    f"To confirm, type exactly:\n"
                    f"  [bold]/killswitch {kill_switch.CONFIRM_PHRASE}[/bold]",
                    border_style="red", title="⚠  IRREVERSIBLE",
                )
            )
            audit.record("KILLSWITCH_PROMPTED", "User viewed kill switch prompt",
                         severity="HIGH")

        elif user_input.startswith("/killswitch "):
            phrase = user_input[12:].strip()
            kill_switch.execute(
                base_dir=BASE_DIR,
                confirm_phrase=phrase,
                stop_callback=lambda: _stop_all(c),
                audit=audit,
            )

        elif cmd == "/wipe-data":
            console.print(
                "[red]To wipe memory only (keep model), type:[/red]\n"
                "[bold]  /wipe-data DELETE DATA CONFIRM[/bold]"
            )

        elif user_input.startswith("/wipe-data "):
            phrase = user_input[11:].strip()
            kill_switch.wipe_data_only(
                base_dir=BASE_DIR,
                confirm_phrase=phrase,
                stop_callback=lambda: _stop_all(c),
                audit=audit,
            )

        # ── normal chat ───────────────────────────────────────────────────
        else:
            audit.record("CHAT_INPUT", f"len={len(user_input)}", severity="LOW",
                         data_type="conversation")
            response = chat.respond(user_input)
            feedback.set_last_response(user_input, response)
            console.print(f"\n[bold green]AI:[/bold green] {response}")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Companion")
    parser.add_argument("--train-now", action="store_true")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--security", action="store_true")
    args = parser.parse_args()

    c = load_system()

    if args.stats:
        c["data_mgr"].show_stats()
        return
    if args.audit:
        c["audit"].show(last_n=50)
        return
    if args.security:
        network_guard.status()
        c["audit"].show(last_n=10, min_severity="MEDIUM")
        c["ai_logger"].show(n=20)
        return
    if args.train_now:
        console.print("[cyan]Running learning session...[/cyan]")
        c["scheduler"].trigger_now()
        import time; time.sleep(5)
        return

    c["monitor"].start()
    c["scheduler"].start()
    c["suggestions"].start()

    console.print(
        f"[dim]Device: {DEVICE} | "
        f"Experiences: {c['buffer'].stats()['total']} | "
        f"Network: BLOCKED (no data leaves this machine) | "
        f"Encryption: AES-256 | Learning: LOCAL ONLY[/dim]"
    )

    try:
        run_chat(c)
    finally:
        _stop_all(c)
        c["audit"].record("SYSTEM_STOP", "Clean shutdown", severity="LOW")
        console.print("[dim]All systems stopped.[/dim]")


if __name__ == "__main__":
    main()
