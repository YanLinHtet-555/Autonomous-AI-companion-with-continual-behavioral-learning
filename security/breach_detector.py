"""
BreachDetector — detects if any data file was modified outside this application.

On every startup:
  1. Computes SHA-256 hash of each sensitive file
  2. Compares against stored manifests from previous run
  3. Alerts immediately if any file was changed externally

Also monitors file access in real-time using watchdog —
if another process opens a sensitive file, the user is alerted.
"""

import os
import hashlib
import json
import threading
from datetime import datetime

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class BreachDetector:
    def __init__(self, watch_paths: list, manifest_path: str, audit_log=None):
        self.watch_paths = watch_paths          # files/dirs to protect
        self.manifest_path = manifest_path      # where hashes are stored
        self.audit = audit_log
        self._observer = None
        self._manifest = {}
        self._load_manifest()

    # ------------------------------------------------------------------ #
    # Startup integrity check                                              #
    # ------------------------------------------------------------------ #

    def startup_check(self) -> bool:
        """
        Called at startup. Returns True if all files are intact.
        Prints alerts and logs to audit for any modified files.
        """
        print("[BreachDetector] Running integrity check...")
        all_ok = True
        current_hashes = self._compute_all_hashes()

        for path, current_hash in current_hashes.items():
            previous = self._manifest.get(path)
            if previous is None:
                # First time seeing this file — register it
                self._manifest[path] = current_hash
            elif previous != current_hash:
                all_ok = False
                msg = (f"\n[SECURITY ALERT] File modified outside this application!\n"
                       f"  File: {path}\n"
                       f"  This may indicate unauthorized access or a data breach.\n"
                       f"  Expected hash: {previous[:16]}...\n"
                       f"  Current hash : {current_hash[:16]}...\n")
                print(msg)
                if self.audit:
                    self.audit.record(
                        "FILE_TAMPERED",
                        f"path={path}",
                        severity="CRITICAL",
                        data_type="breach_detection",
                    )

        # Update manifest with current state
        self._save_manifest(current_hashes)

        if all_ok:
            print(f"[BreachDetector] Integrity OK — {len(current_hashes)} files verified.")
        return all_ok

    # ------------------------------------------------------------------ #
    # Real-time file access monitoring                                     #
    # ------------------------------------------------------------------ #

    def start_realtime(self):
        if not WATCHDOG_AVAILABLE:
            print("[BreachDetector] watchdog not available — real-time monitoring disabled")
            return

        dirs_to_watch = set()
        for path in self.watch_paths:
            if os.path.isfile(path):
                dirs_to_watch.add(os.path.dirname(path))
            elif os.path.isdir(path):
                dirs_to_watch.add(path)

        handler = _FileAccessHandler(
            protected_files=set(self.watch_paths),
            on_alert=self._on_realtime_alert,
        )
        self._observer = Observer()
        for d in dirs_to_watch:
            if os.path.isdir(d):
                self._observer.schedule(handler, d, recursive=False)
        self._observer.start()

    def stop_realtime(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def _on_realtime_alert(self, path: str, event_type: str):
        msg = (f"\n[SECURITY ALERT] Suspicious file access detected!\n"
               f"  File      : {path}\n"
               f"  Event     : {event_type}\n"
               f"  Timestamp : {datetime.now().isoformat()}\n"
               f"  This data file was accessed. If you did not do this,\n"
               f"  stop the companion immediately and review your system.\n")
        print(msg)
        if self.audit:
            self.audit.record(
                "SUSPICIOUS_FILE_ACCESS",
                f"path={os.path.basename(path)} event={event_type}",
                severity="HIGH",
                data_type="breach_detection",
            )

    # ------------------------------------------------------------------ #
    # Hash management                                                      #
    # ------------------------------------------------------------------ #

    def _hash_file(self, path: str) -> str:
        sha = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha.update(chunk)
        except FileNotFoundError:
            return "NOT_FOUND"
        return sha.hexdigest()

    def _compute_all_hashes(self) -> dict:
        hashes = {}
        for path in self.watch_paths:
            if os.path.isfile(path):
                hashes[path] = self._hash_file(path)
        return hashes

    def update_manifest(self):
        """Call after intentional writes so next check doesn't false-alarm."""
        current = self._compute_all_hashes()
        self._save_manifest(current)

    def _load_manifest(self):
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path) as f:
                self._manifest = json.load(f)

    def _save_manifest(self, hashes: dict):
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        with open(self.manifest_path, "w") as f:
            json.dump(hashes, f, indent=2)
        self._manifest = hashes


class _FileAccessHandler(FileSystemEventHandler):
    def __init__(self, protected_files: set, on_alert):
        super().__init__()
        self.protected = protected_files
        self.on_alert = on_alert

    def on_modified(self, event):
        if not event.is_directory and event.src_path in self.protected:
            self.on_alert(event.src_path, "modified")

    def on_deleted(self, event):
        if not event.is_directory and event.src_path in self.protected:
            self.on_alert(event.src_path, "deleted")

    def on_moved(self, event):
        if not event.is_directory and event.src_path in self.protected:
            self.on_alert(event.src_path, "moved")
