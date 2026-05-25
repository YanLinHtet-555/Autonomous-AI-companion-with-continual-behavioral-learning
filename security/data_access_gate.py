"""
DataAccessGate — protects against data leaving your machine.

POLICY (matches user intent exactly):
─────────────────────────────────────────────────────────────────
  ALWAYS ALLOWED (local, never leaves your machine):
    • AI training on your daily activity logs
    • AI reading experiences to improve responses
    • Nightly self-training and model upgrades
    • Monitoring your apps, code, tasks, screen
    • Continual learning replay buffer reads
    • Saving model checkpoints locally
    • Writing new experiences to local database

  ALWAYS BLOCKED (requires explicit /permit command):
    • Exporting data to any external file or service
    • Sharing data with anyone
    • Any outbound network call (enforced by NetworkGuard)
    • Disabling encryption or the network guard
    • Bulk plaintext dumps to unencrypted locations
─────────────────────────────────────────────────────────────────

The AI can freely learn from everything you do locally.
What it CANNOT do is take that data outside your machine.
"""

import threading
from datetime import datetime


# Operations that are ALWAYS blocked without explicit user permission.
# These are the only things this gate cares about.
PROTECTED_EXTERNAL_OPS = {
    "export_data",
    "export_to_file",
    "share_data",
    "send_to_cloud",
    "bulk_plaintext_dump",
    "disable_encryption",
    "disable_network_guard",
    "remote_backup",
}


class DataAccessGate:
    """
    Only blocks operations that move data outside this machine.
    Local learning, monitoring, and AI self-improvement are never gated.
    """

    def __init__(self, audit_log=None, ai_logger=None):
        self.audit = audit_log
        self.ai_logger = ai_logger
        self._lock = threading.Lock()
        self._pending: dict = {}           # op -> {"event", "granted"}
        self._session_permits: set = set()
        self._deny_count = 0
        self._allow_count = 0

    # ------------------------------------------------------------------ #
    # Export / share gate — the ONLY thing this blocks                    #
    # ------------------------------------------------------------------ #

    def request_export(self, reason: str, timeout_sec: int = 60) -> bool:
        """
        Call this before any operation that writes data to an external
        location (file export, cloud backup, etc.).

        Returns True only if the user explicitly types /permit export_data.
        """
        return self._gate("export_data", reason, timeout_sec)

    def request_share(self, destination: str, timeout_sec: int = 60) -> bool:
        """Call before sharing data with any external party."""
        return self._gate("share_data", f"share to: {destination}", timeout_sec)

    def request_sensitive_op(self, operation: str, reason: str,
                              timeout_sec: int = 60) -> bool:
        """Gate for any other operation in PROTECTED_EXTERNAL_OPS."""
        if operation not in PROTECTED_EXTERNAL_OPS:
            # Not a protected operation — always allow locally
            return True
        return self._gate(operation, reason, timeout_sec)

    def _gate(self, operation: str, reason: str, timeout_sec: int) -> bool:
        # Check session permit
        with self._lock:
            if operation in self._session_permits:
                self._log_allowed(operation, "session_permit")
                return True

        # Show the request to the user and wait
        print(
            f"\n{'─'*58}\n"
            f"  DATA RELEASE REQUEST — requires your permission\n"
            f"  Operation : {operation}\n"
            f"  Reason    : {reason}\n"
            f"\n"
            f"  → /permit {operation:<30} allow once\n"
            f"  → /permit-session {operation:<24} allow for this session\n"
            f"  → /deny {operation:<34} block it\n"
            f"\n"
            f"  Auto-denied in {timeout_sec}s if no response.\n"
            f"{'─'*58}\n"
        )

        event = threading.Event()
        with self._lock:
            self._pending[operation] = {"event": event, "granted": False}

        responded = event.wait(timeout=timeout_sec)

        with self._lock:
            result = self._pending.pop(operation, {}).get("granted", False)

        if result:
            self._log_allowed(operation, "user_permit")
            return True
        else:
            cause = "user_deny" if responded else "timeout"
            self._log_denied(operation, reason, cause)
            return False

    # ------------------------------------------------------------------ #
    # User commands                                                        #
    # ------------------------------------------------------------------ #

    def permit(self, operation: str, session_wide: bool = False):
        with self._lock:
            if operation in self._pending:
                self._pending[operation]["granted"] = True
                self._pending[operation]["event"].set()
        if session_wide:
            with self._lock:
                self._session_permits.add(operation)
            print(f"[DataAccessGate] '{operation}' permitted for this session.")
        else:
            print(f"[DataAccessGate] '{operation}' permitted once.")

    def deny(self, operation: str):
        with self._lock:
            if operation in self._pending:
                self._pending[operation]["granted"] = False
                self._pending[operation]["event"].set()
        print(f"[DataAccessGate] '{operation}' denied.")

    def revoke_session(self, operation: str):
        with self._lock:
            self._session_permits.discard(operation)
        print(f"[DataAccessGate] Session permit for '{operation}' revoked.")

    # ------------------------------------------------------------------ #
    # Logging                                                              #
    # ------------------------------------------------------------------ #

    def _log_allowed(self, operation: str, method: str):
        self._allow_count += 1
        if self.audit:
            self.audit.record("DATA_RELEASE_ALLOWED",
                              f"op={operation} via={method}",
                              severity="MEDIUM", data_type="data_gate")

    def _log_denied(self, operation: str, reason: str, cause: str):
        self._deny_count += 1
        msg = f"Data release blocked: {operation} (cause={cause})"
        print(f"[DataAccessGate] BLOCKED: {operation} — {cause}")
        if self.ai_logger:
            self.ai_logger.log("DATA_RELEASE_BLOCKED", msg, severity="HIGH")
        if self.audit:
            self.audit.record("DATA_RELEASE_DENIED",
                              f"op={operation} cause={cause} reason={reason}",
                              severity="HIGH", data_type="data_gate")

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    def show_status(self):
        with self._lock:
            pending = list(self._pending.keys())
            permits = list(self._session_permits)
        print(f"\n--- DataAccessGate ---")
        print(f"  Policy           : local learning ALWAYS ALLOWED")
        print(f"  Protected ops    : export, share, disable-security")
        print(f"  Releases allowed : {self._allow_count}")
        print(f"  Releases blocked : {self._deny_count}")
        print(f"  Session permits  : {permits or 'none'}")
        print(f"  Pending requests : {pending or 'none'}")
        print(f"----------------------\n")

    def get_mode(self):
        return "local-permitted / external-blocked"
