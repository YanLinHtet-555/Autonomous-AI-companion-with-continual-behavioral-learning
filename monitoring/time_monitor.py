import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict


class TimeMonitor:
    """
    Tracks productive hours, idle periods, and daily routines.
    Builds a picture of when the user works and how long sessions last.
    """

    def __init__(self, idle_threshold=120, poll_interval=10, on_event=None):
        self.idle_threshold = idle_threshold  # seconds before "idle"
        self.poll_interval = poll_interval
        self.on_event = on_event
        self._running = False
        self._thread = None
        self._last_active = datetime.now()
        self._is_idle = False
        self._session_start = datetime.now()
        self._daily_log = defaultdict(list)  # date -> [{"start", "end", "type"}]

        try:
            from pynput import mouse, keyboard
            self._input_available = True
            self._mouse = mouse.Listener(on_move=self._on_input,
                                         on_click=self._on_input)
            self._keyboard = keyboard.Listener(on_press=self._on_input)
        except Exception:
            self._input_available = False

    def start(self):
        self._running = True
        if self._input_available:
            self._mouse.start()
            self._keyboard.start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._input_available:
            self._mouse.stop()
            self._keyboard.stop()

    def _on_input(self, *args):
        self._last_active = datetime.now()
        if self._is_idle:
            self._is_idle = False
            self._emit("idle_end", {"idle_end": datetime.now().isoformat()})

    def _loop(self):
        while self._running:
            now = datetime.now()
            idle_secs = (now - self._last_active).total_seconds()

            if not self._is_idle and idle_secs > self.idle_threshold:
                self._is_idle = True
                self._emit("idle_start", {
                    "idle_start": now.isoformat(),
                    "active_duration_sec": round(
                        (now - self._session_start).total_seconds()
                    ),
                })

            time.sleep(self.poll_interval)

    def _emit(self, event_type, data):
        event = {"type": event_type, "timestamp": datetime.now().isoformat()}
        event.update(data)
        date_key = datetime.now().strftime("%Y-%m-%d")
        self._daily_log[date_key].append(event)
        if self.on_event:
            self.on_event(event)

    def get_productive_hours_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        events = self._daily_log.get(today, [])
        idle_secs = sum(
            e.get("active_duration_sec", 0)
            for e in events if e["type"] == "idle_start"
        )
        session_secs = (datetime.now() - self._session_start).total_seconds()
        productive = max(0, session_secs - idle_secs)
        return round(productive / 3600, 2)  # hours

    def get_current_hour(self):
        return datetime.now().hour

    def get_day_summary(self, date_str=None):
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        return self._daily_log.get(date_str, [])
