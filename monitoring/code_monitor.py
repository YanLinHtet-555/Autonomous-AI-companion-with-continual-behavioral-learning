import os
import threading
from datetime import datetime
from collections import defaultdict

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cpp", ".c",
    ".cs", ".go", ".rs", ".php", ".rb", ".html", ".css", ".sql",
    ".vue", ".svelte", ".kt", ".swift",
}

LANGUAGE_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript/React", ".jsx": "JavaScript/React",
    ".java": "Java", ".cpp": "C++", ".c": "C", ".cs": "C#",
    ".go": "Go", ".rs": "Rust", ".php": "PHP", ".rb": "Ruby",
    ".html": "HTML", ".css": "CSS", ".sql": "SQL",
    ".vue": "Vue", ".svelte": "Svelte", ".kt": "Kotlin", ".swift": "Swift",
}


class _CodeEventHandler(FileSystemEventHandler):
    def __init__(self, on_event):
        super().__init__()
        self.on_event = on_event
        self._debounce = {}     # path -> last event time
        self._debounce_sec = 3  # group rapid saves

    def on_modified(self, event):
        if event.is_directory:
            return
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext not in CODE_EXTENSIONS:
            return
        now = datetime.now()
        last = self._debounce.get(event.src_path)
        if last and (now - last).total_seconds() < self._debounce_sec:
            return
        self._debounce[event.src_path] = now
        self.on_event({
            "type": "code_edit",
            "file": event.src_path,
            "language": LANGUAGE_MAP.get(ext, ext),
            "timestamp": now.isoformat(),
        })

    def on_created(self, event):
        if event.is_directory:
            return
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext not in CODE_EXTENSIONS:
            return
        self.on_event({
            "type": "code_created",
            "file": event.src_path,
            "language": LANGUAGE_MAP.get(ext, ext),
            "timestamp": datetime.now().isoformat(),
        })


class CodeMonitor:
    """
    Watches directories for code file changes.
    Tracks which files and languages the user is working on.
    Also monitors git commits when gitpython is available.
    """

    def __init__(self, watch_dirs=None, on_event=None):
        self.watch_dirs = [d for d in (watch_dirs or []) if os.path.isdir(d)]
        self.on_event = on_event
        self._observer = None
        self._running = False
        self._git_thread = None
        self.edit_log = []  # {file, language, timestamp}
        self._lang_counts = defaultdict(int)

    def start(self):
        if not self.watch_dirs:
            return
        self._running = True
        handler = _CodeEventHandler(self._handle_event)
        self._observer = Observer()
        for d in self.watch_dirs:
            self._observer.schedule(handler, d, recursive=True)
        self._observer.start()

    def stop(self):
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def _handle_event(self, event):
        self.edit_log.append(event)
        lang = event.get("language", "unknown")
        self._lang_counts[lang] += 1
        if self.on_event:
            self.on_event(event)

    def get_language_stats(self):
        return dict(sorted(self._lang_counts.items(), key=lambda x: x[1], reverse=True))

    def get_active_files(self, last_n_minutes=60):
        cutoff = datetime.now().timestamp() - last_n_minutes * 60
        seen = set()
        result = []
        for entry in reversed(self.edit_log):
            ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
            if ts < cutoff:
                break
            f = entry["file"]
            if f not in seen:
                seen.add(f)
                result.append(f)
        return result
