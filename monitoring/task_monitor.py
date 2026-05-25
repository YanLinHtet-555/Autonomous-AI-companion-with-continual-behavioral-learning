import os
import threading
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


DOCUMENT_EXTENSIONS = {
    ".docx", ".doc", ".pdf", ".xlsx", ".xls", ".pptx", ".ppt",
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml",
}


class _DocumentHandler(FileSystemEventHandler):
    def __init__(self, on_event):
        super().__init__()
        self.on_event = on_event

    def on_modified(self, event):
        if event.is_directory:
            return
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext in DOCUMENT_EXTENSIONS:
            self.on_event({
                "type": "document_edit",
                "file": os.path.basename(event.src_path),
                "path": event.src_path,
                "ext": ext,
                "timestamp": datetime.now().isoformat(),
            })

    def on_created(self, event):
        if event.is_directory:
            return
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext in DOCUMENT_EXTENSIONS:
            self.on_event({
                "type": "document_created",
                "file": os.path.basename(event.src_path),
                "path": event.src_path,
                "ext": ext,
                "timestamp": datetime.now().isoformat(),
            })


class TaskMonitor:
    """
    Watches document folders for file activity.
    Infers task type from file extensions and names.
    """

    def __init__(self, watch_dirs=None, on_event=None):
        self.watch_dirs = [d for d in (watch_dirs or []) if os.path.isdir(d)]
        self.on_event = on_event
        self._observer = None
        self.task_log = []

    def start(self):
        if not self.watch_dirs:
            return
        handler = _DocumentHandler(self._handle)
        self._observer = Observer()
        for d in self.watch_dirs:
            self._observer.schedule(handler, d, recursive=True)
        self._observer.start()

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def _handle(self, event):
        self.task_log.append(event)
        if self.on_event:
            self.on_event(event)

    def get_recent_tasks(self, limit=20):
        return self.task_log[-limit:]
