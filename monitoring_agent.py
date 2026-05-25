"""
Monitoring Agent — runs NATIVELY on your Windows host machine.

This script is the only part that stays outside Docker because it
needs direct access to your Windows desktop, active windows, and files.

It collects activity events and sends them to the AI backend
running in Docker at http://localhost:8000/events every 30 seconds.

Usage:
    python monitoring_agent.py              # default: connects to localhost:8000
    python monitoring_agent.py --port 8000  # custom port
    python monitoring_agent.py --dry-run    # print events, don't send
"""

import os
import sys
import time
import json
import argparse
import threading
import queue

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Only import host-side monitoring — no Docker-only deps needed
from config import MONITORING, PRIVACY
from monitoring.app_monitor import AppMonitor
from monitoring.code_monitor import CodeMonitor
from monitoring.task_monitor import TaskMonitor
from monitoring.time_monitor import TimeMonitor
from monitoring.learning_detector import LearningDetector
from summarizer.event_summarizer import EventSummarizer
from privacy.consent_manager import ConsentManager

try:
    import urllib.request
    HTTP_AVAILABLE = True
except ImportError:
    HTTP_AVAILABLE = False

FLUSH_INTERVAL = 30     # send batch to Docker every 30 seconds
MAX_BATCH_SIZE = 100    # max events per batch


class MonitoringAgent:
    def __init__(self, api_url: str = "http://localhost:8000", dry_run: bool = False):
        self.api_url = api_url.rstrip("/")
        self.dry_run = dry_run
        self._event_queue = queue.Queue()
        self._running = False
        self._monitors = []

        consent = ConsentManager(PRIVACY["consent_path"])
        privacy_cfg = consent.as_dict() if consent.has_consented() else PRIVACY

        # App monitor
        self.app_monitor = AppMonitor(
            poll_interval=MONITORING.get("poll_interval", 5),
            idle_threshold=MONITORING.get("idle_threshold", 120),
            on_event=self._push,
        )
        self._monitors.append(self.app_monitor)

        # Code monitor
        watch_dirs = [d for d in MONITORING.get("watched_dirs", [])
                      if os.path.isdir(d)]
        self.code_monitor = CodeMonitor(
            watch_dirs=watch_dirs,
            on_event=self._push,
        )
        self._monitors.append(self.code_monitor)

        # Task monitor
        self.task_monitor = TaskMonitor(
            watch_dirs=watch_dirs,
            on_event=self._push,
        )
        self._monitors.append(self.task_monitor)

        # Time monitor
        self.time_monitor = TimeMonitor(
            idle_threshold=MONITORING.get("idle_threshold", 120),
            on_event=self._push,
        )
        self._monitors.append(self.time_monitor)

        # Learning detector
        self.learning_detector = LearningDetector(
            on_event=self._push,
            poll_interval=10,
        )
        self.learning_detector.attach_monitors(
            app_monitor=self.app_monitor,
            code_monitor=self.code_monitor,
        )
        self._monitors.append(self.learning_detector)

    def _push(self, event: dict):
        excluded = PRIVACY.get("excluded_apps", [])
        app = event.get("app", "").lower()
        if any(ex.lower() in app for ex in excluded):
            return
        self._event_queue.put(event)

    def start(self):
        self._running = True
        for m in self._monitors:
            try:
                m.start()
            except Exception as e:
                print(f"[Agent] Warning starting {type(m).__name__}: {e}")

        flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        flush_thread.start()

        print(f"[Agent] Monitoring started — sending to {self.api_url}")
        print(f"[Agent] Press Ctrl+C to stop\n")

    def stop(self):
        self._running = False
        for m in self._monitors:
            try:
                m.stop()
            except Exception:
                pass

    def _flush_loop(self):
        while self._running:
            time.sleep(FLUSH_INTERVAL)
            self._flush()

    def _flush(self):
        events = []
        while not self._event_queue.empty() and len(events) < MAX_BATCH_SIZE:
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break

        if not events:
            return

        if self.dry_run:
            print(f"[Agent][DRY RUN] Would send {len(events)} events:")
            for e in events[:5]:
                print(f"  {e.get('type','?')}: {str(e)[:80]}")
            return

        self._send_events(events)

    def _send_events(self, events: list):
        url = f"{self.api_url}/events"
        payload = json.dumps({"events": events}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                print(f"[Agent] Sent {len(events)} events → "
                      f"ingested: {result.get('ingested', '?')}")
        except Exception as e:
            print(f"[Agent] Failed to send events: {e}")
            print(f"[Agent] Is Docker running? Check: docker ps")

    def start_study(self, topic: str):
        """Tell Docker about a manual study session."""
        self.learning_detector.start_study_session(topic)
        url = f"{self.api_url}/study"
        payload = json.dumps({"topic": topic, "action": "start"}).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"[Agent] Could not notify Docker: {e}")

    def run_forever(self):
        self.start()
        try:
            while True:
                status = self._get_status()
                print(f"[Agent] {status}")
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[Agent] Stopping...")
            self.stop()

    def _get_status(self):
        topic = self.learning_detector.get_current_topic()
        study_time = self.learning_detector.total_study_time_today()
        queued = self._event_queue.qsize()
        return (
            f"queued={queued} | "
            f"study={study_time:.0f}min today"
            + (f" | learning: {topic}" if topic else "")
        )


def main():
    parser = argparse.ArgumentParser(description="AI Companion Monitoring Agent")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print events instead of sending to Docker")
    args = parser.parse_args()

    api_url = f"http://{args.host}:{args.port}"
    agent = MonitoringAgent(api_url=api_url, dry_run=args.dry_run)
    agent.run_forever()


if __name__ == "__main__":
    main()
