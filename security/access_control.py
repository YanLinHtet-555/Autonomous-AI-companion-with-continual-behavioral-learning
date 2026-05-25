"""
AccessControl — gates all sensitive data operations behind explicit user commands.

Rules:
  - No data can be exported, shared, or read in bulk without a typed user command
  - Every operation is logged to the audit trail
  - No automated process can release data — only the user sitting at the keyboard
  - Export tokens expire after one use and within 60 seconds
"""

import hashlib
import os
import secrets
import threading
from datetime import datetime


class AccessControl:
    def __init__(self, audit_log=None):
        self.audit = audit_log
        self._lock = threading.Lock()
        # one-time tokens: token_id -> {operation, expiry, used}
        self._tokens: dict = {}
        # which operations require a confirmation token
        self._protected_ops = {
            "export_data",
            "delete_all",
            "bulk_read",
            "share_data",
            "disable_encryption",
            "disable_network_guard",
        }

    # ------------------------------------------------------------------ #
    # Token-based authorization                                           #
    # ------------------------------------------------------------------ #

    def request_token(self, operation: str, ttl_seconds: int = 60) -> str:
        """
        User requests permission to perform a sensitive operation.
        Returns a one-time token that must be passed back within TTL.
        """
        if operation not in self._protected_ops:
            return "not_required"

        token = secrets.token_hex(16)
        expiry = datetime.now().timestamp() + ttl_seconds
        with self._lock:
            self._tokens[token] = {
                "operation": operation,
                "expiry": expiry,
                "used": False,
                "issued_at": datetime.now().isoformat(),
            }

        self._log(f"TOKEN_ISSUED", f"op={operation} ttl={ttl_seconds}s", "MEDIUM")
        print(f"\n[AccessControl] Token issued for '{operation}'.")
        print(f"  Token : {token}")
        print(f"  Expires in {ttl_seconds} seconds.")
        print(f"  Pass this token back to confirm the operation.\n")
        return token

    def authorize(self, token: str, operation: str) -> bool:
        """
        Validate a one-time token for an operation.
        Tokens are single-use and time-limited.
        """
        with self._lock:
            entry = self._tokens.get(token)
            if not entry:
                self._log("AUTH_FAILED", f"op={operation} unknown token", "HIGH")
                print("[AccessControl] Authorization FAILED — unknown token.")
                return False
            if entry["used"]:
                self._log("AUTH_FAILED", f"op={operation} token already used", "HIGH")
                print("[AccessControl] Authorization FAILED — token already used.")
                return False
            if datetime.now().timestamp() > entry["expiry"]:
                self._log("AUTH_FAILED", f"op={operation} token expired", "HIGH")
                print("[AccessControl] Authorization FAILED — token expired.")
                del self._tokens[token]
                return False
            if entry["operation"] != operation:
                self._log("AUTH_FAILED",
                          f"op mismatch: expected {entry['operation']}, got {operation}",
                          "CRITICAL")
                print("[AccessControl] Authorization FAILED — operation mismatch.")
                return False

            entry["used"] = True

        self._log("AUTH_SUCCESS", f"op={operation}", "MEDIUM")
        print(f"[AccessControl] Authorization GRANTED for '{operation}'.")
        return True

    # ------------------------------------------------------------------ #
    # Direct guards — wrap sensitive operations                           #
    # ------------------------------------------------------------------ #

    def guard(self, operation: str):
        """
        Decorator / context guard for sensitive operations.
        Usage:
            with access_control.guard("export_data"):
                ... do the export ...
        """
        return _OperationGuard(self, operation)

    def check_permission(self, operation: str) -> bool:
        """
        Simple boolean check — does not require a token for low-risk ops.
        High-risk ops always return False here (use token flow instead).
        """
        if operation in self._protected_ops:
            self._log("PERMISSION_DENIED",
                      f"op={operation} requires token authorization", "HIGH")
            print(f"\n[AccessControl] '{operation}' requires explicit authorization.")
            print(f"  Run: /authorize {operation}")
            return False
        return True

    # ------------------------------------------------------------------ #
    # Convenience                                                          #
    # ------------------------------------------------------------------ #

    def _log(self, action: str, detail: str, severity: str = "LOW"):
        if self.audit:
            self.audit.record(action, detail, severity=severity,
                              data_type="access_control")

    def list_pending_tokens(self):
        now = datetime.now().timestamp()
        with self._lock:
            active = {
                t: e for t, e in self._tokens.items()
                if not e["used"] and e["expiry"] > now
            }
        if not active:
            print("[AccessControl] No active tokens.")
        for token, entry in active.items():
            remaining = round(entry["expiry"] - now)
            print(f"  {token[:8]}...  op={entry['operation']}  "
                  f"expires in {remaining}s")


class _OperationGuard:
    """Context manager that enforces access control around an operation."""

    def __init__(self, ac: AccessControl, operation: str):
        self.ac = ac
        self.operation = operation
        self._token = None

    def __enter__(self):
        if self.operation in self.ac._protected_ops:
            raise PermissionError(
                f"[AccessControl] '{self.operation}' is a protected operation. "
                f"Use /authorize {self.operation} to proceed."
            )
        self.ac._log("OP_START", f"op={self.operation}", "LOW")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "SUCCESS" if exc_type is None else f"FAILED:{exc_type.__name__}"
        self.ac._log("OP_END", f"op={self.operation} status={status}", "LOW")
        return False
