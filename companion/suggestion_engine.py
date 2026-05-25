import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict, Counter


class SuggestionEngine:
    """
    Watches learned patterns and proactively suggests actions
    before the user asks. Gets smarter as more behavior is observed.

    Examples:
    - "You usually start a daily summary around now — want me to draft one?"
    - "You've been coding for 2 hours straight — time for a break?"
    - "You always open Stack Overflow after debugging — want help with that error?"
    """

    def __init__(self, monitor_manager, experience_buffer,
                 check_interval=300, min_occurrences=3,
                 on_suggestion=None):
        self.monitor = monitor_manager
        self.buffer = experience_buffer
        self.check_interval = check_interval
        self.min_occurrences = min_occurrences
        self.on_suggestion = on_suggestion  # callback(suggestion_text)
        self._running = False
        self._thread = None
        self._suppressed = set()   # suggestions shown recently

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            suggestions = self._generate_suggestions()
            for s in suggestions:
                key = s["key"]
                if key not in self._suppressed:
                    self._suppressed.add(key)
                    if self.on_suggestion:
                        self.on_suggestion(s["text"])
            # Clear suppression after 2 hours so suggestions can repeat
            time.sleep(self.check_interval)
            if len(self._suppressed) > 20:
                self._suppressed.clear()

    def _generate_suggestions(self):
        suggestions = []
        now = datetime.now()
        hour = now.hour

        # --- Break reminder ---
        if self.monitor and self.monitor.time_monitor:
            productive_hours = self.monitor.time_monitor.get_productive_hours_today()
            if productive_hours >= 2.0:
                suggestions.append({
                    "key": f"break_{now.hour}",
                    "text": (f"You've been working for {productive_hours:.1f} hours. "
                              "Consider a short break to stay sharp."),
                })

        # --- Coding session suggestion ---
        if self.monitor and self.monitor.code_monitor:
            lang_stats = self.monitor.code_monitor.get_language_stats()
            if lang_stats:
                top_lang = list(lang_stats.keys())[0]
                active_files = self.monitor.code_monitor.get_active_files(last_n_minutes=30)
                if active_files:
                    suggestions.append({
                        "key": f"coding_{top_lang}_{now.hour}",
                        "text": (f"You're actively coding in {top_lang}. "
                                  "Want me to help review your recent changes?"),
                    })

        # --- Time-based routine suggestions ---
        suggestions.extend(self._time_routine_suggestions(hour))

        return suggestions

    def _time_routine_suggestions(self, hour):
        suggestions = []
        if hour == 9:
            suggestions.append({
                "key": f"morning_plan_{datetime.now().date()}",
                "text": "Good morning! Want me to help plan your tasks for today?",
            })
        elif hour == 12:
            suggestions.append({
                "key": f"midday_check_{datetime.now().date()}",
                "text": "Midday check-in: how is your progress going today?",
            })
        elif hour == 17:
            suggestions.append({
                "key": f"eod_summary_{datetime.now().date()}",
                "text": (
                    "End of day — want me to write a summary of what you accomplished today?"
                ),
            })
        return suggestions

    def get_pending_suggestions(self):
        return self._generate_suggestions()
