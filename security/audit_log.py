"""
AuditLog — tamper-evident hash-chained log of every data access.

Every read, write, export, deletion, or network attempt is recorded.
Each entry is linked to the previous via SHA-256 hash chaining —
if anyone modifies a past entry, the chain breaks and alerts the user.

The audit log itself is encrypted with a separate key.
"""

import os
import json
import hashlib
import threading
from datetime import datetime
from cryptography.fernet import Fernet


SEVERITY_LEVELS = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class AuditLog:
    def __init__(self, log_path: str, key_path: str):
        self.log_path = log_path
        self.key_path = key_path
        self._lock = threading.Lock()
        self._fernet = self._load_or_create_key()
        self._chain_hash = self._compute_chain_tip()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # ------------------------------------------------------------------ #
    # Key management                                                       #
    # ------------------------------------------------------------------ #

    def _load_or_create_key(self):
        os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, "wb") as f:
                f.write(key)
        return Fernet(key)

    # ------------------------------------------------------------------ #
    # Hash chain                                                           #
    # ------------------------------------------------------------------ #

    def _compute_chain_tip(self):
        """Read the last entry's hash to continue the chain."""
        if not os.path.exists(self.log_path):
            return "GENESIS"
        try:
            entries = self._read_raw()
            if entries:
                return entries[-1].get("entry_hash", "GENESIS")
        except Exception:
            pass
        return "GENESIS"

    def _hash_entry(self, entry: dict, prev_hash: str) -> str:
        payload = json.dumps(entry, sort_keys=True) + prev_hash
        return hashlib.sha256(payload.encode()).hexdigest()

    # ------------------------------------------------------------------ #
    # Writing                                                              #
    # ------------------------------------------------------------------ #

    def record(self, action: str, detail: str, severity: str = "LOW",
               data_type: str = "general"):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "detail": detail,
            "severity": severity,
            "data_type": data_type,
            "prev_hash": self._chain_hash,
        }
        entry["entry_hash"] = self._hash_entry(entry, self._chain_hash)

        encrypted = self._fernet.encrypt(
            json.dumps(entry).encode()
        ).decode()

        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(encrypted + "\n")
            self._chain_hash = entry["entry_hash"]

        # Print alerts for high-severity events
        if SEVERITY_LEVELS.get(severity, 0) >= SEVERITY_LEVELS["HIGH"]:
            print(f"\n[AUDIT ALERT] {severity}: {action} — {detail}")

    # ------------------------------------------------------------------ #
    # Reading & verification                                               #
    # ------------------------------------------------------------------ #

    def _read_raw(self):
        if not os.path.exists(self.log_path):
            return []
        entries = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    decrypted = self._fernet.decrypt(line.encode()).decode()
                    entries.append(json.loads(decrypted))
                except Exception:
                    entries.append({"CORRUPT": True, "raw": line[:40]})
        return entries

    def verify_chain(self):
        """
        Verify the hash chain is intact.
        Returns (intact: bool, first_broken_index: int or None)
        """
        entries = self._read_raw()
        if not entries:
            return True, None

        prev_hash = "GENESIS"
        for i, entry in enumerate(entries):
            if entry.get("CORRUPT"):
                return False, i
            stored_hash = entry.get("entry_hash", "")
            entry_copy = {k: v for k, v in entry.items() if k != "entry_hash"}
            expected = self._hash_entry(entry_copy, prev_hash)
            if stored_hash != expected:
                print(f"\n[AUDIT] CHAIN BROKEN at entry {i} — possible tampering detected!")
                return False, i
            prev_hash = stored_hash
        return True, None

    def show(self, last_n: int = 20, min_severity: str = "LOW"):
        entries = self._read_raw()
        min_level = SEVERITY_LEVELS.get(min_severity, 0)
        filtered = [
            e for e in entries
            if SEVERITY_LEVELS.get(e.get("severity", "LOW"), 0) >= min_level
            and not e.get("CORRUPT")
        ]
        recent = filtered[-last_n:]

        print(f"\n--- Audit Log (last {len(recent)} entries, severity >= {min_severity}) ---")
        for e in recent:
            ts = e["timestamp"][:19]
            sev = e.get("severity", "LOW")
            action = e.get("action", "?")
            detail = e.get("detail", "")
            print(f"  [{ts}] [{sev:<8}] {action}: {detail}")
        print("---\n")

        intact, broken_at = self.verify_chain()
        if not intact:
            print(f"[AUDIT WARNING] Hash chain broken at entry {broken_at}. "
                  f"Data may have been tampered with!")
        else:
            print(f"[AUDIT] Chain integrity: OK ({len(entries)} entries verified)")

    def get_stats(self):
        entries = self._read_raw()
        counts = {}
        for e in entries:
            sev = e.get("severity", "LOW")
            counts[sev] = counts.get(sev, 0) + 1
        return {"total_entries": len(entries), "by_severity": counts}

    def callback(self, action: str, detail: str, severity: str = "LOW"):
        """Convenience method for use as a callback."""
        self.record(action, detail, severity=severity)
