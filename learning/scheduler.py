import threading
import time
from datetime import datetime


class LearningScheduler:
    """
    Triggers nightly continual learning runs automatically.
    Collects untrained experiences from the buffer and passes them
    to the ContinualLearner at a scheduled time each day.
    """

    def __init__(self, continual_learner, experience_buffer,
                 event_summarizer, monitor_manager,
                 train_hour=2, min_samples=10,
                 ai_logger=None, data_gate=None):
        self.learner = continual_learner
        self.buffer = experience_buffer
        self.summarizer = event_summarizer
        self.monitor = monitor_manager
        self.train_hour = train_hour
        self.min_samples = min_samples
        self.ai_logger = ai_logger
        self.data_gate = data_gate
        self._running = False
        self._thread = None
        self._last_run = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[Scheduler] Nightly learning scheduled at {self.train_hour:02d}:00")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            now = datetime.now()
            if (now.hour == self.train_hour and
                    (self._last_run is None or
                     self._last_run.date() < now.date())):
                self._run_learning_session()
                self._last_run = now
            time.sleep(60)

    def _run_learning_session(self):
        print(f"\n[Scheduler] Starting nightly learning — {datetime.now():%Y-%m-%d %H:%M}")

        # Local learning is always permitted — no gate check needed.
        # Data never leaves this machine (NetworkGuard blocks all outbound connections).
        # The ai_logger records everything so you can inspect it with /ai-log.

        # 1. Flush monitoring events → natural language
        if self.monitor:
            events = self.monitor.drain_events()
            self.summarizer.ingest_batch(events)
            if self.ai_logger and events:
                self.ai_logger.data_read(
                    "monitor_events", len(events),
                    "converting daily observations to training data"
                )

        new_texts = self.summarizer.flush()
        daily_narrative = self.summarizer.build_daily_narrative(new_texts)
        if daily_narrative:
            self.buffer.add_observation(daily_narrative)
            new_texts.append(daily_narrative)

        # 2. Pull untrained experiences from buffer
        untrained = self.buffer.get_untrained(limit=500)
        if self.ai_logger:
            self.ai_logger.data_read(
                "experience_buffer", len(untrained),
                "nightly training corpus"
            )

        all_texts = new_texts + [e["content"] for e in untrained]

        if len(all_texts) < self.min_samples:
            print(f"[Scheduler] Only {len(all_texts)} samples — skipping (need {self.min_samples})")
            return

        # 3. Run continual learning
        result = self.learner.learn(all_texts, epochs=3, verbose=True)

        # 4. Mark trained
        trained_ids = [e["id"] for e in untrained]
        if trained_ids:
            self.buffer.mark_trained(trained_ids)
            if self.ai_logger:
                self.ai_logger.data_write("experience_buffer", len(trained_ids))

        if result:
            print(f"[Scheduler] Learning complete: {result}")

    def trigger_now(self):
        t = threading.Thread(target=self._run_learning_session, daemon=True)
        t.start()
