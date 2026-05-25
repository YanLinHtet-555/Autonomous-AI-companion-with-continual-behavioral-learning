import queue
from datetime import datetime

from .app_monitor import AppMonitor
from .code_monitor import CodeMonitor
from .task_monitor import TaskMonitor
from .time_monitor import TimeMonitor
from .input_monitor import InputMonitor
from .learning_detector import LearningDetector


class MonitorManager:
    """
    Orchestrates all monitors. Aggregates events into a single queue
    that the experience buffer and summarizer consume.
    Includes the LearningDetector so the AI learns alongside the user.
    """

    def __init__(self, config, privacy_config, on_event=None, co_learner=None):
        self.config = config
        self.privacy = privacy_config
        self.on_event = on_event
        self.co_learner = co_learner   # CoLearner notified on learning sessions
        self.event_queue = queue.Queue()
        self._monitors = []

        if privacy_config.get("monitor_apps", True):
            self.app_monitor = AppMonitor(
                poll_interval=config.get("poll_interval", 5),
                idle_threshold=config.get("idle_threshold", 120),
                on_event=self._push,
            )
            self._monitors.append(self.app_monitor)
        else:
            self.app_monitor = None

        if privacy_config.get("monitor_code", True):
            self.code_monitor = CodeMonitor(
                watch_dirs=config.get("watched_dirs", []),
                on_event=self._push,
            )
            self._monitors.append(self.code_monitor)
        else:
            self.code_monitor = None

        if privacy_config.get("monitor_tasks", True):
            self.task_monitor = TaskMonitor(
                watch_dirs=config.get("watched_dirs", []),
                on_event=self._push,
            )
            self._monitors.append(self.task_monitor)
        else:
            self.task_monitor = None

        if privacy_config.get("monitor_time", True):
            self.time_monitor = TimeMonitor(
                idle_threshold=config.get("idle_threshold", 120),
                on_event=self._push,
            )
            self._monitors.append(self.time_monitor)
        else:
            self.time_monitor = None

        if privacy_config.get("monitor_input", False):
            self.input_monitor = InputMonitor(on_event=self._push)
            self._monitors.append(self.input_monitor)
        else:
            self.input_monitor = None

        # Learning detector — always active alongside other monitors
        self.learning_detector = LearningDetector(
            on_event=self._on_learning_event,
            poll_interval=10,
        )
        self._monitors.append(self.learning_detector)

    def start(self):
        # Attach sub-monitors to the learning detector so it can inspect them
        self.learning_detector.attach_monitors(
            app_monitor=self.app_monitor,
            code_monitor=self.code_monitor,
        )
        for m in self._monitors:
            m.start()
        print(f"[MonitorManager] Started {len(self._monitors)} monitors "
              f"(including LearningDetector)")

    def stop(self):
        for m in self._monitors:
            m.stop()
        print("[MonitorManager] All monitors stopped")

    def _push(self, event):
        excluded = self.privacy.get("excluded_apps", [])
        app = event.get("app", "").lower()
        if any(ex.lower() in app for ex in excluded):
            return
        self.event_queue.put(event)
        if self.on_event:
            self.on_event(event)

    def _on_learning_event(self, event):
        """Route learning events to CoLearner and also push to the general queue."""
        self._push(event)
        if self.co_learner and event.get("type") in (
            "learning_session", "study_session_started"
        ):
            self.co_learner.on_learning_session(event)

    def drain_events(self):
        events = []
        while not self.event_queue.empty():
            try:
                events.append(self.event_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def get_status(self):
        return {
            "active_monitors": [type(m).__name__ for m in self._monitors],
            "queued_events": self.event_queue.qsize(),
            "productive_hours": (
                self.time_monitor.get_productive_hours_today()
                if self.time_monitor else None
            ),
            "top_apps": (
                self.app_monitor.get_session_summary()[:5]
                if self.app_monitor else []
            ),
            "language_stats": (
                self.code_monitor.get_language_stats()
                if self.code_monitor else {}
            ),
            "current_study_topic": (
                self.learning_detector.get_current_topic()
            ),
            "study_time_today_min": (
                self.learning_detector.total_study_time_today()
            ),
        }
