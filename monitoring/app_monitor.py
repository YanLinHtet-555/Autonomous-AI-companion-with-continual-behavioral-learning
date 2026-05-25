import time
import threading
import psutil
from datetime import datetime

try:
    import win32gui
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class AppMonitor:
    """
    Tracks active window and application usage every N seconds.
    Detects app switches and accumulates time-per-app.
    """

    def __init__(self, poll_interval=5, idle_threshold=120, on_event=None):
        self.poll_interval = poll_interval
        self.idle_threshold = idle_threshold
        self.on_event = on_event  # callback(event_dict)
        self._running = False
        self._thread = None
        self._current_app = None
        self._app_start = None
        self._session_log = []   # list of {app, title, start, end, duration}

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _get_active_window(self):
        if not WIN32_AVAILABLE:
            return "unknown", "unknown"
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            return proc.name().replace(".exe", ""), title
        except Exception:
            return "unknown", "unknown"

    def _loop(self):
        while self._running:
            app_name, window_title = self._get_active_window()
            now = datetime.now()

            if app_name != self._current_app:
                # app switched — log previous session
                if self._current_app and self._app_start:
                    duration = (now - self._app_start).total_seconds()
                    if duration >= 5:  # ignore sub-5s flickers
                        entry = {
                            "type": "app_session",
                            "app": self._current_app,
                            "title": window_title,
                            "start": self._app_start.isoformat(),
                            "end": now.isoformat(),
                            "duration_sec": round(duration),
                        }
                        self._session_log.append(entry)
                        if self.on_event:
                            self.on_event(entry)

                self._current_app = app_name
                self._app_start = now

            time.sleep(self.poll_interval)

    def get_session_summary(self):
        totals = {}
        for entry in self._session_log:
            app = entry["app"]
            totals[app] = totals.get(app, 0) + entry["duration_sec"]
        return sorted(totals.items(), key=lambda x: x[1], reverse=True)
