"""
KillSwitch — irreversible emergency wipe of ALL companion data.

Use when:
  - The AI did something suspicious you did not authorise
  - You want to completely remove all traces from your machine
  - You suspect a data breach

What it destroys (in order):
  1. Stops all background processes
  2. Overwrites every data file with random bytes (3 passes — DoD-style)
  3. Deletes encryption keys → existing ciphertext becomes permanently unreadable
  4. Deletes model checkpoints
  5. Deletes vector index
  6. Deletes SQLite experience database
  7. Deletes audit logs
  8. Deletes consent and privacy files
  9. Exits the process

CONFIRM PHRASE required: type it exactly to proceed.
There is no undo.
"""

import os
import sys
import secrets
import shutil
from datetime import datetime

CONFIRM_PHRASE = "DELETE EVERYTHING CONFIRM"
WIPE_PASSES = 3   # number of random-overwrite passes before deletion


# ------------------------------------------------------------------ #
# Secure file deletion                                                 #
# ------------------------------------------------------------------ #

def _secure_delete_file(path: str, passes: int = WIPE_PASSES):
    """Overwrite with random bytes N times, then delete."""
    if not os.path.isfile(path):
        return
    size = os.path.getsize(path)
    if size > 0:
        for _ in range(passes):
            with open(path, "r+b") as f:
                f.write(secrets.token_bytes(size))
                f.flush()
                os.fsync(f.fileno())
    os.remove(path)
    print(f"  [WIPED] {os.path.basename(path)}")


def _secure_delete_dir(path: str, passes: int = WIPE_PASSES):
    """Recursively wipe all files in a directory, then remove it."""
    if not os.path.isdir(path):
        return
    for root, dirs, files in os.walk(path, topdown=False):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                _secure_delete_file(fpath, passes)
            except Exception as e:
                print(f"  [WARN] Could not wipe {fname}: {e}")
        for dname in dirs:
            try:
                os.rmdir(os.path.join(root, dname))
            except Exception:
                pass
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


# ------------------------------------------------------------------ #
# Main execute function                                                #
# ------------------------------------------------------------------ #

def execute(base_dir: str,
            confirm_phrase: str,
            stop_callback=None,
            audit=None):
    """
    Execute the kill switch.

    :param base_dir:       Root directory of the companion
    :param confirm_phrase: Must match CONFIRM_PHRASE exactly
    :param stop_callback:  Called first to stop all background threads
    :param audit:          AuditLog — written to BEFORE files are deleted
    :returns: False if wrong phrase (does nothing). Otherwise exits the process.
    """
    if confirm_phrase.strip() != CONFIRM_PHRASE:
        print(
            f"\n[KillSwitch] Wrong confirmation phrase.\n"
            f"  Required: {CONFIRM_PHRASE}\n"
            f"  Try again with: /killswitch {CONFIRM_PHRASE}\n"
        )
        return False

    # Final warning
    print(
        f"\n{'='*60}\n"
        f"  KILL SWITCH ACTIVATED — {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"  Securely wiping all data ({WIPE_PASSES}-pass overwrite).\n"
        f"  This is IRREVERSIBLE.\n"
        f"{'='*60}\n"
    )

    # Write final audit entry before logs are destroyed
    if audit:
        try:
            audit.record(
                "KILLSWITCH_EXECUTED",
                f"User initiated full data wipe at {datetime.now().isoformat()}",
                severity="CRITICAL",
            )
        except Exception:
            pass

    # Stop all background threads first
    if stop_callback:
        try:
            print("[KillSwitch] Stopping background processes...")
            stop_callback()
        except Exception as e:
            print(f"[KillSwitch] Warning during shutdown: {e}")

    # ── Wipe targets ──────────────────────────────────────────────────
    targets = [
        # Encryption keys — wiped first so remaining ciphertext is unreadable
        os.path.join(base_dir, "memory", "data", ".key"),
        os.path.join(base_dir, "memory", "data", ".audit_key"),

        # Databases and indexes
        os.path.join(base_dir, "memory", "data", "experiences.db"),
        os.path.join(base_dir, "memory", "data", "faiss.index"),
        os.path.join(base_dir, "memory", "data", "faiss.index.meta.json"),
        os.path.join(base_dir, "memory", "data", "audit.log"),
        os.path.join(base_dir, "memory", "data", "integrity.json"),
        os.path.join(base_dir, "memory", "data", "activity.log"),

        # Model checkpoints
        os.path.join(base_dir, "model", "checkpoints"),

        # Privacy / consent
        os.path.join(base_dir, "privacy", "consent.json"),

        # Tokenizer (contains nothing sensitive but wipe anyway)
        os.path.join(base_dir, "model", "tokenizer.json"),
    ]

    print("[KillSwitch] Wiping files...\n")
    for target in targets:
        if os.path.isdir(target):
            print(f"  Wiping directory: {os.path.basename(target)}/")
            _secure_delete_dir(target, passes=WIPE_PASSES)
        elif os.path.isfile(target):
            try:
                _secure_delete_file(target, passes=WIPE_PASSES)
            except Exception as e:
                print(f"  [WARN] {target}: {e}")

    # ── Final message ─────────────────────────────────────────────────
    print(
        f"\n{'='*60}\n"
        f"  WIPE COMPLETE\n\n"
        f"  All experiences, model weights, encryption keys,\n"
        f"  audit logs, and consent data have been destroyed.\n\n"
        f"  Encryption keys were wiped first — any remaining\n"
        f"  ciphertext fragments are permanently unreadable.\n\n"
        f"  The AI companion has been fully reset.\n"
        f"{'='*60}\n"
    )

    sys.exit(0)


# ------------------------------------------------------------------ #
# Partial wipe — data only, keep model                                #
# ------------------------------------------------------------------ #

def wipe_data_only(base_dir: str, confirm_phrase: str,
                   stop_callback=None, audit=None):
    """
    Wipes only experience data and keys — keeps model weights.
    Use when you want to reset memory but keep the trained model.
    Confirm phrase: 'DELETE DATA CONFIRM'
    """
    if confirm_phrase.strip() != "DELETE DATA CONFIRM":
        print("[KillSwitch] Wrong phrase. Required: DELETE DATA CONFIRM")
        return False

    if audit:
        try:
            audit.record("PARTIAL_WIPE_EXECUTED", "Data-only wipe",
                         severity="HIGH")
        except Exception:
            pass

    if stop_callback:
        try:
            stop_callback()
        except Exception:
            pass

    data_targets = [
        os.path.join(base_dir, "memory", "data", ".key"),
        os.path.join(base_dir, "memory", "data", ".audit_key"),
        os.path.join(base_dir, "memory", "data", "experiences.db"),
        os.path.join(base_dir, "memory", "data", "faiss.index"),
        os.path.join(base_dir, "memory", "data", "faiss.index.meta.json"),
        os.path.join(base_dir, "memory", "data", "audit.log"),
        os.path.join(base_dir, "memory", "data", "activity.log"),
    ]

    print("[KillSwitch] Wiping experience data only...")
    for target in data_targets:
        if os.path.isfile(target):
            try:
                _secure_delete_file(target)
            except Exception as e:
                print(f"  [WARN] {target}: {e}")

    print("[KillSwitch] Memory wiped. Model weights preserved.")
    sys.exit(0)
