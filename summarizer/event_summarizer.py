import os
from datetime import datetime
from collections import defaultdict


class EventSummarizer:
    """
    Converts raw monitoring events into natural language training sentences.
    These sentences feed directly into the AI's experience buffer and become
    part of its continual learning data.
    """

    def __init__(self):
        self._pending = []      # events not yet summarized
        self._summaries = []    # finalized natural language texts

    def ingest(self, event):
        self._pending.append(event)

    def ingest_batch(self, events):
        self._pending.extend(events)

    def flush(self):
        """Convert all pending events to natural language and return them."""
        texts = []
        grouped = defaultdict(list)

        for ev in self._pending:
            grouped[ev.get("type", "unknown")].append(ev)

        for event_type, events in grouped.items():
            handler = self._handlers.get(event_type, self._generic)
            result = handler(self, events)
            if result:
                texts.extend(result if isinstance(result, list) else [result])

        self._summaries.extend(texts)
        self._pending.clear()
        return texts

    # ------------------------------------------------------------------ #
    # Event handlers — each returns one or more natural language strings  #
    # ------------------------------------------------------------------ #

    def _summarize_app_sessions(self, events):
        texts = []
        for ev in events:
            duration = ev.get("duration_sec", 0)
            if duration < 10:
                continue
            app = ev.get("app", "an application")
            title = ev.get("title", "")
            mins = round(duration / 60, 1)
            ts = self._fmt_time(ev.get("start", ""))
            text = f"At {ts}, the user spent {mins} minutes using {app}"
            if title and title.lower() != app.lower():
                text += f" on '{title}'"
            text += "."
            texts.append(text)
        return texts

    def _summarize_code_edits(self, events):
        by_lang = defaultdict(list)
        for ev in events:
            lang = ev.get("language", "unknown")
            by_lang[lang].append(ev)

        texts = []
        for lang, evs in by_lang.items():
            files = list({os.path.basename(e["file"]) for e in evs})
            ts = self._fmt_time(evs[0].get("timestamp", ""))
            if len(files) == 1:
                text = f"At {ts}, the user edited {files[0]} ({lang})."
            else:
                file_list = ", ".join(files[:3])
                extra = f" and {len(files)-3} more" if len(files) > 3 else ""
                text = f"At {ts}, the user edited {len(files)} {lang} files: {file_list}{extra}."
            texts.append(text)
        return texts

    def _summarize_code_created(self, events):
        texts = []
        for ev in events:
            fname = os.path.basename(ev.get("file", "a file"))
            lang = ev.get("language", "unknown")
            ts = self._fmt_time(ev.get("timestamp", ""))
            texts.append(f"At {ts}, the user created a new {lang} file: {fname}.")
        return texts

    def _summarize_document_edits(self, events):
        texts = []
        for ev in events:
            fname = ev.get("file", "a document")
            ts = self._fmt_time(ev.get("timestamp", ""))
            texts.append(f"At {ts}, the user edited document '{fname}'.")
        return texts

    def _summarize_idle_start(self, events):
        texts = []
        for ev in events:
            active = ev.get("active_duration_sec", 0)
            ts = self._fmt_time(ev.get("timestamp", ""))
            mins = round(active / 60, 1)
            texts.append(
                f"At {ts}, the user became idle after {mins} minutes of active work."
            )
        return texts

    def _summarize_idle_end(self, events):
        texts = []
        for ev in events:
            ts = self._fmt_time(ev.get("timestamp", ""))
            texts.append(f"At {ts}, the user returned from an idle period.")
        return texts

    def _summarize_input_stats(self, events):
        texts = []
        for ev in events:
            wpm = ev.get("wpm_estimate", 0)
            intensity = ev.get("intensity", "medium")
            ts = self._fmt_time(ev.get("timestamp", ""))
            texts.append(
                f"At {ts}, typing intensity was {intensity} (~{wpm} wpm)."
            )
        return texts

    def _generic(self, events):
        texts = []
        for ev in events:
            ts = self._fmt_time(ev.get("timestamp", ""))
            etype = ev.get("type", "event")
            texts.append(f"At {ts}, system event: {etype}.")
        return texts

    _handlers = {
        "app_session": _summarize_app_sessions,
        "code_edit": _summarize_code_edits,
        "code_created": _summarize_code_created,
        "document_edit": _summarize_document_edits,
        "document_created": _summarize_document_edits,
        "idle_start": _summarize_idle_start,
        "idle_end": _summarize_idle_end,
        "input_stats": _summarize_input_stats,
    }

    def build_daily_narrative(self, summaries=None):
        """Combine summaries into a single day narrative for training."""
        summaries = summaries or self._summaries
        if not summaries:
            return None
        date_str = datetime.now().strftime("%A, %B %d %Y")
        body = " ".join(summaries)
        return f"On {date_str}: {body}"

    @staticmethod
    def _fmt_time(iso_str):
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%I:%M %p")
        except Exception:
            return "an unknown time"
