"""
LearningDetector — watches for signals that the user is studying something.

Detects learning mode from:
  • Browser window titles containing doc/tutorial/course/learn keywords
  • PDF reader open with study material
  • Jupyter notebook active
  • Note-taking apps and markdown files being edited
  • User typing slowly in a browser (reading, not coding)
  • Explicit /study command from the user

When learning is detected, fires a learning_session event so the
CoLearner can capture the topic and study alongside the user.
"""

import re
import time
import threading
from datetime import datetime
from collections import defaultdict


# Keywords in window titles that suggest learning activity
LEARNING_TITLE_KEYWORDS = [
    "documentation", "docs", "tutorial", "learn", "course", "guide",
    "how to", "howto", "getting started", "reference", "manual",
    "lecture", "lesson", "study", "notes", "cheatsheet", "cheat sheet",
    "w3schools", "mdn", "stackoverflow", "geeksforgeeks", "medium",
    "towards data science", "realpython", "python.org", "pytorch.org",
    "tensorflow", "huggingface", "arxiv", "paper", "research",
    "readme", "wiki", "wikipedia", "github.com",
]

# Apps that strongly indicate learning mode
LEARNING_APPS = {
    "jupyter",
    "jupyter-notebook",
    "jupyter-lab",
    "jupyterlab",
    "jupyter notebook",
    "acrobat",           # PDF reader
    "foxit",             # PDF reader
    "sumatrapdf",        # PDF reader
    "okular",
    "evince",
    "calibre",           # ebook reader
    "obsidian",          # note-taking
    "notion",
    "onenote",
    "zotero",            # research tool
    "anki",              # flashcard learning
    "vlc",               # could be tutorial video
}

# Browser apps — check window title for learning keywords
BROWSER_APPS = {
    "chrome", "firefox", "msedge", "edge", "brave", "opera",
    "vivaldi", "chromium",
}

# Note file extensions — user is writing study notes
NOTE_EXTENSIONS = {".md", ".txt", ".rst", ".ipynb", ".tex"}

# Minimum time on a learning page before we register the session (seconds)
MIN_LEARNING_DURATION = 30


def _title_suggests_learning(title: str) -> tuple:
    """Returns (is_learning: bool, topic: str)."""
    title_lower = title.lower()
    for kw in LEARNING_TITLE_KEYWORDS:
        if kw in title_lower:
            # Try to extract topic from title
            topic = _extract_topic(title)
            return True, topic
    return False, ""


def _extract_topic(title: str) -> str:
    """Best-effort topic extraction from a window title."""
    # Remove common suffixes like "- Stack Overflow", "| MDN", etc.
    cleaned = re.sub(
        r"\s*[\|\-–—]\s*(stack overflow|mdn|mozilla|python\.org|github|"
        r"medium|towards data science|w3schools|geeksforgeeks|youtube|"
        r"google|bing|wikipedia).*",
        "", title, flags=re.IGNORECASE
    ).strip()
    # Truncate
    return cleaned[:80] if cleaned else title[:80]


class LearningDetector:
    """
    Monitors app and window activity to detect when the user is learning.
    Fires on_learning_event(event_dict) when a learning session is detected.
    """

    def __init__(self, on_event=None, poll_interval=10):
        self.on_event = on_event
        self.poll_interval = poll_interval
        self._running = False
        self._thread = None

        # State tracking
        self._current_topic = None
        self._topic_start = None
        self._session_log = []         # list of completed learning sessions
        self._active_sessions = {}     # topic -> start_time

        # Injected by MonitorManager after construction
        self._app_monitor = None
        self._code_monitor = None

    def attach_monitors(self, app_monitor=None, code_monitor=None):
        self._app_monitor = app_monitor
        self._code_monitor = code_monitor

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ #
    # Detection loop                                                       #
    # ------------------------------------------------------------------ #

    def _loop(self):
        while self._running:
            self._check_learning_state()
            time.sleep(self.poll_interval)

    def _check_learning_state(self):
        if not self._app_monitor:
            return

        app_name, window_title = self._app_monitor._get_active_window()
        app_lower = app_name.lower()
        now = datetime.now()

        is_learning = False
        topic = ""

        # 1. Direct learning app
        for learning_app in LEARNING_APPS:
            if learning_app in app_lower:
                is_learning = True
                topic = f"{app_name} session"
                break

        # 2. Browser with a learning page
        if not is_learning:
            for browser in BROWSER_APPS:
                if browser in app_lower:
                    detected, extracted_topic = _title_suggests_learning(window_title)
                    if detected:
                        is_learning = True
                        topic = extracted_topic
                    break

        # 3. Note-taking (code monitor sees .md, .txt edits)
        if not is_learning and self._code_monitor:
            active_files = self._code_monitor.get_active_files(last_n_minutes=5)
            for fpath in active_files:
                if any(fpath.lower().endswith(ext) for ext in NOTE_EXTENSIONS):
                    is_learning = True
                    topic = f"notes: {fpath.split('\\')[-1].split('/')[-1]}"
                    break

        if is_learning and topic:
            self._on_learning_active(topic, now)
        else:
            self._on_learning_inactive(now)

    def _on_learning_active(self, topic: str, now: datetime):
        if self._current_topic != topic:
            # New topic detected
            if self._current_topic:
                self._close_session(self._current_topic, now)
            self._current_topic = topic
            self._topic_start = now
        # else: continuing same topic, no action needed

    def _on_learning_inactive(self, now: datetime):
        if self._current_topic:
            self._close_session(self._current_topic, now)
            self._current_topic = None
            self._topic_start = None

    def _close_session(self, topic: str, end_time: datetime):
        if not self._topic_start:
            return
        duration = (end_time - self._topic_start).total_seconds()
        if duration < MIN_LEARNING_DURATION:
            return   # too brief, ignore

        session = {
            "type": "learning_session",
            "topic": topic,
            "start": self._topic_start.isoformat(),
            "end": end_time.isoformat(),
            "duration_sec": round(duration),
            "timestamp": end_time.isoformat(),
        }
        self._session_log.append(session)
        if self.on_event:
            self.on_event(session)

    # ------------------------------------------------------------------ #
    # Explicit topic injection (from /study command)                      #
    # ------------------------------------------------------------------ #

    def start_study_session(self, topic: str):
        """Called when user types /study <topic>."""
        now = datetime.now()
        if self._current_topic:
            self._close_session(self._current_topic, now)
        self._current_topic = topic
        self._topic_start = now
        event = {
            "type": "study_session_started",
            "topic": topic,
            "timestamp": now.isoformat(),
            "manual": True,
        }
        if self.on_event:
            self.on_event(event)
        print(f"[LearningDetector] Study session started: {topic}")

    def end_study_session(self):
        """Called when user types /study end."""
        if self._current_topic:
            self._close_session(self._current_topic, datetime.now())
            topic = self._current_topic
            self._current_topic = None
            self._topic_start = None
            print(f"[LearningDetector] Study session ended: {topic}")

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def get_current_topic(self):
        return self._current_topic

    def get_session_log(self, limit=20):
        return self._session_log[-limit:]

    def get_topics_studied(self):
        from collections import Counter
        counts = Counter(s["topic"] for s in self._session_log)
        return counts.most_common()

    def total_study_time_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        total = sum(
            s["duration_sec"] for s in self._session_log
            if s["timestamp"].startswith(today)
        )
        return round(total / 60, 1)   # minutes
