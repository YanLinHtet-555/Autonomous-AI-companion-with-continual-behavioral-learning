"""
ProactiveEngine — Neon initiates conversation based on context.

Neon can send messages without being prompted:
  • Morning/evening greetings
  • Idle check-ins when the user hasn't said anything for a while
  • Coding observations when the monitor detects active code editing
  • Level-up announcements
  • Random thoughts when she feels like talking

All messages are queued and drained by the WebSocket handler.
"""

import asyncio
import random
from datetime import datetime
from typing import Callable, Optional

from companion.persona import get_proactive_message, level_up_message


class ProactiveEngine:
    def __init__(
        self,
        send_fn: Callable,          # async fn(content, emotion) — sends to websocket
        level_system=None,
        idle_threshold_sec: int = 600,   # 10 min idle before check-in
        check_interval_sec: int = 60,    # poll loop cadence
    ):
        self.send = send_fn
        self.level_system = level_system
        self.idle_threshold = idle_threshold_sec
        self.check_interval = check_interval_sec

        self._last_user_msg: datetime = datetime.now()
        self._last_greeting_date: Optional[str] = None
        self._last_idle_check: datetime = datetime.now()
        self._pending_level_up: Optional[str] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    # ------------------------------------------------------------------ #
    # External signals                                                      #
    # ------------------------------------------------------------------ #

    def on_user_message(self):
        """Call this whenever the user sends a message."""
        self._last_user_msg = datetime.now()
        self._last_idle_check = datetime.now()

    def on_level_up(self, new_level: str):
        """Call this right after a level-up — queues an announcement."""
        self._pending_level_up = new_level

    def on_coding_activity(self):
        """Call this when the monitor reports active code editing."""
        # Only fire occasionally — don't spam
        if random.random() < 0.15:
            asyncio.create_task(self._send_coding_observation())

    # ------------------------------------------------------------------ #
    # Internal loop                                                         #
    # ------------------------------------------------------------------ #

    async def _loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                now = datetime.now()

                # Level-up announcement takes priority
                if self._pending_level_up:
                    level = self._pending_level_up
                    self._pending_level_up = None
                    msg = level_up_message(level)
                    await self.send(msg, emotion="excited")
                    continue

                # Morning/evening greeting (once per day per period)
                await self._maybe_greet(now)

                # Idle check-in
                await self._maybe_idle_check(now)

                # Occasional random thought
                if random.random() < 0.03:  # ~3% chance each minute
                    msg = get_proactive_message("random_thoughts",
                                                self._current_level())
                    await self.send(msg, emotion="idle")

            except asyncio.CancelledError:
                break
            except Exception:
                pass  # never crash the loop

    async def _maybe_greet(self, now: datetime):
        hour = now.hour
        date_str = now.strftime("%Y-%m-%d")

        if hour < 6 or hour >= 22:
            return  # don't greet in dead hours

        period = "morning" if hour < 12 else "evening"
        key = f"{date_str}_{period}"

        if self._last_greeting_date == key:
            return  # already greeted this period today

        self._last_greeting_date = key
        msg = get_proactive_message(period, self._current_level())
        emotion = "happy" if period == "morning" else "idle"
        await self.send(msg, emotion=emotion)

    async def _maybe_idle_check(self, now: datetime):
        idle_sec = (now - self._last_user_msg).total_seconds()
        since_last_check = (now - self._last_idle_check).total_seconds()

        if idle_sec > self.idle_threshold and since_last_check > self.idle_threshold:
            self._last_idle_check = now
            msg = get_proactive_message("idle_check", self._current_level())
            await self.send(msg, emotion="idle")

    async def _send_coding_observation(self):
        msg = get_proactive_message("coding_observation", self._current_level())
        await self.send(msg, emotion="thinking")

    def _current_level(self) -> str:
        if self.level_system:
            return self.level_system.current_level
        return "adult"
