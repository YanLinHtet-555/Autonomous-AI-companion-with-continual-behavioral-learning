"""
AIActionLogger — every autonomous action the AI takes is logged and shown to you.

The AI must NEVER do anything silently in the background.
Every training run, data read, suggestion, error, or suspicious event
produces a visible notification. Nothing happens without your knowledge.

Suspicious event threshold: 3 events → CRITICAL alert + /killswitch prompt.
"""

import threading
from datetime import datetime


# Action type constants
class Action:
    TRAINING_START   = "TRAINING_START"
    TRAINING_END     = "TRAINING_END"
    TRAINING_FAIL    = "TRAINING_FAIL"
    DATA_READ        = "DATA_READ"
    DATA_WRITE       = "DATA_WRITE"
    CHECKPOINT_SAVE  = "CHECKPOINT_SAVE"
    CHECKPOINT_LOAD  = "CHECKPOINT_LOAD"
    SUGGESTION_MADE  = "SUGGESTION_MADE"
    MONITOR_EVENT    = "MONITOR_BATCH"
    ERROR            = "ERROR"
    SUSPICIOUS       = "SUSPICIOUS"
    SELF_UPGRADE     = "SELF_UPGRADE"


# Severity → display style
_STYLES = {
    "LOW":      ("[AI]",      ""),
    "MEDIUM":   ("[AI ℹ]",   ""),
    "HIGH":     ("[AI ⚠]",   "\n"),
    "CRITICAL": ("[AI !!!]",  "\n" + "="*60 + "\n"),
}

_SUSPICIOUS_THRESHOLD = 3


class AIActionLogger:
    """
    Central logger for all AI-initiated actions.
    Pass an instance to ContinualLearner, Scheduler, SuggestionEngine, etc.
    """

    def __init__(self, audit_log=None, print_callback=None):
        self.audit = audit_log
        self._print = print_callback or print
        self._log = []
        self._lock = threading.Lock()
        self._suspicious_count = 0

    # ------------------------------------------------------------------ #
    # Core log method                                                      #
    # ------------------------------------------------------------------ #

    def log(self, action_type: str, description: str,
            details: dict = None, severity: str = "LOW"):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "description": description,
            "details": details or {},
            "severity": severity,
        }
        with self._lock:
            self._log.append(entry)

        if self.audit:
            self.audit.record(
                f"AI_{action_type}", description,
                severity=severity, data_type="ai_action",
            )

        self._notify(entry)

        if action_type == Action.SUSPICIOUS:
            self._suspicious_count += 1
            if self._suspicious_count >= _SUSPICIOUS_THRESHOLD:
                self._critical_alert()

    # ------------------------------------------------------------------ #
    # Notification display                                                 #
    # ------------------------------------------------------------------ #

    def _notify(self, entry):
        sev = entry["severity"]
        prefix, border = _STYLES.get(sev, ("[AI]", ""))
        ts = entry["timestamp"][11:19]   # HH:MM:SS
        atype = entry["action_type"]
        desc = entry["description"]

        if sev in ("HIGH", "CRITICAL") or atype == Action.SUSPICIOUS:
            msg = (
                f"{border}"
                f"{prefix} [{ts}] {atype}\n"
                f"         {desc}\n"
            )
            if entry["details"]:
                for k, v in entry["details"].items():
                    msg += f"         {k}: {v}\n"
            if border:
                msg += border
        elif atype in (Action.TRAINING_START, Action.TRAINING_END,
                       Action.CHECKPOINT_SAVE, Action.SELF_UPGRADE):
            msg = f"{prefix} [{ts}] {atype}: {desc}"
        elif atype == Action.ERROR:
            msg = f"\n{prefix} [{ts}] ERROR: {desc}\n"
        else:
            return   # LOW severity non-training: silent (only goes to audit log)

        self._print(msg)

    def _critical_alert(self):
        msg = (
            f"\n{'='*60}\n"
            f"  CRITICAL SECURITY ALERT\n"
            f"  {self._suspicious_count} suspicious AI actions detected.\n"
            f"  If you did not expect this behaviour:\n"
            f"    Type /killswitch to wipe all data immediately\n"
            f"{'='*60}\n"
        )
        self._print(msg)
        if self.audit:
            self.audit.record(
                "SUSPICIOUS_THRESHOLD_REACHED",
                f"count={self._suspicious_count}",
                severity="CRITICAL",
                data_type="ai_action",
            )

    # ------------------------------------------------------------------ #
    # Convenience shortcuts                                                #
    # ------------------------------------------------------------------ #

    def training_start(self, n_samples: int, strategy: str = "EWC+Replay"):
        self.log(Action.TRAINING_START,
                 f"Starting self-training on {n_samples} samples",
                 details={"strategy": strategy, "samples": n_samples},
                 severity="MEDIUM")

    def training_end(self, avg_loss: float, duration_sec: float):
        self.log(Action.TRAINING_END,
                 f"Training complete — loss={avg_loss:.4f} in {duration_sec:.0f}s",
                 severity="MEDIUM")

    def training_fail(self, reason: str):
        self.log(Action.TRAINING_FAIL,
                 f"Training failed: {reason}",
                 severity="HIGH")

    def checkpoint_saved(self, tag: str):
        self.log(Action.CHECKPOINT_SAVE,
                 f"Model checkpoint saved: {tag}",
                 severity="LOW")

    def checkpoint_loaded(self, tag: str):
        self.log(Action.CHECKPOINT_LOAD,
                 f"Model checkpoint loaded: {tag}",
                 severity="LOW")

    def data_read(self, source: str, n_records: int, reason: str):
        self.log(Action.DATA_READ,
                 f"Read {n_records} records from {source} — reason: {reason}",
                 severity="LOW")

    def data_write(self, target: str, n_records: int):
        self.log(Action.DATA_WRITE,
                 f"Wrote {n_records} records to {target}",
                 severity="LOW")

    def suggestion_made(self, text: str):
        self.log(Action.SUGGESTION_MADE,
                 f"Proactive suggestion: {text[:80]}",
                 severity="LOW")

    def error(self, component: str, message: str):
        self.log(Action.ERROR,
                 f"[{component}] {message}",
                 severity="HIGH")

    def suspicious(self, description: str, details: dict = None):
        self.log(Action.SUSPICIOUS,
                 description,
                 details=details,
                 severity="CRITICAL")

    def self_upgrade(self, from_step: int, to_step: int):
        self.log(Action.SELF_UPGRADE,
                 f"Model upgraded: step {from_step} → {to_step}",
                 severity="MEDIUM")

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def show(self, n: int = 30, action_type: str = None):
        with self._lock:
            entries = list(self._log)
        if action_type:
            entries = [e for e in entries if e["action_type"] == action_type]
        recent = entries[-n:]
        print(f"\n--- AI Action Log (last {len(recent)}) ---")
        for e in recent:
            ts = e["timestamp"][11:19]
            print(f"  [{ts}] [{e['action_type']:<18}] [{e['severity']:<8}] {e['description']}")
        if self._suspicious_count:
            print(f"\n  ⚠  Suspicious events: {self._suspicious_count}")
        print("---\n")

    def get_suspicious_count(self):
        return self._suspicious_count

    def get_recent(self, n: int = 10):
        with self._lock:
            return list(self._log[-n:])
