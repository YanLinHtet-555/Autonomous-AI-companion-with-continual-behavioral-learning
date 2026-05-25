import threading
import time
from datetime import datetime


class InputMonitor:
    """
    Tracks typing speed and activity intensity.
    OPT-IN ONLY — disabled by default, user must explicitly enable.
    Stores only aggregate statistics, never actual keystrokes.
    """

    def __init__(self, on_event=None):
        self.on_event = on_event
        self._running = False
        self._keystroke_count = 0
        self._window_start = datetime.now()
        self._window_sec = 60  # report stats every 60s
        self._thread = None
        self._listener = None
        self._available = False

        try:
            from pynput import keyboard
            self._keyboard_mod = keyboard
            self._available = True
        except ImportError:
            pass

    def start(self):
        if not self._available:
            print("[InputMonitor] pynput not available — input monitoring disabled")
            return
        self._running = True
        self._listener = self._keyboard_mod.Listener(on_press=self._on_key)
        self._listener.start()
        self._thread = threading.Thread(target=self._report_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._listener:
            self._listener.stop()

    def _on_key(self, key):
        self._keystroke_count += 1

    def _report_loop(self):
        while self._running:
            time.sleep(self._window_sec)
            now = datetime.now()
            elapsed = (now - self._window_start).total_seconds()
            if elapsed > 0:
                wpm_estimate = (self._keystroke_count / 5) / (elapsed / 60)
                event = {
                    "type": "input_stats",
                    "keystrokes": self._keystroke_count,
                    "wpm_estimate": round(wpm_estimate, 1),
                    "window_sec": round(elapsed),
                    "intensity": self._classify_intensity(wpm_estimate),
                    "timestamp": now.isoformat(),
                }
                if self.on_event:
                    self.on_event(event)
            self._keystroke_count = 0
            self._window_start = now

    def _classify_intensity(self, wpm):
        if wpm < 10:
            return "low"
        elif wpm < 40:
            return "medium"
        else:
            return "high"
