"""
AI Level System — the AI grows from baby to professional as it learns.

Levels (lowest → highest):
  Baby         — freshly initialised, knows almost nothing
  Kid          — starting to grasp patterns
  Adult        — capable and context-aware
  Scholar      — deep domain knowledge
  Professional — fully adapted to your workflow and style

Level is determined by three combined metrics:
  • experiences       — entries in the experience buffer
  • training_sessions — completed nightly self-training cycles
  • study_minutes     — co-learning time (user studied alongside the AI)

All three criteria must be met simultaneously to advance.
Level is persisted to data/level.json and never goes backwards.
"""

import json
import os
from datetime import datetime
from typing import Optional


LEVELS = ["baby", "kid", "adult", "scholar", "professional"]

# All three criteria must be satisfied to reach a given level
THRESHOLDS = {
    "baby":         {"experiences": 0,    "training_sessions": 0,  "study_minutes": 0},
    "kid":          {"experiences": 50,   "training_sessions": 2,  "study_minutes": 10},
    "adult":        {"experiences": 200,  "training_sessions": 7,  "study_minutes": 60},
    "scholar":      {"experiences": 500,  "training_sessions": 20, "study_minutes": 300},
    "professional": {"experiences": 1000, "training_sessions": 50, "study_minutes": 1000},
}

# Per-level behaviour traits applied during chat generation
TRAITS = {
    "baby": {
        "label":             "Baby",
        "icon":              "[B]",
        "description":       "Just awakened. Still learning to form thoughts.",
        "temperature_delta": +0.15,    # more random — the AI is exploring
        "max_tokens_cap":    80,
        "response_prefix":   "I'm still learning, but here is my best attempt: ",
    },
    "kid": {
        "label":             "Kid",
        "icon":              "[K]",
        "description":       "Curious and growing. Picks up patterns quickly.",
        "temperature_delta": +0.07,
        "max_tokens_cap":    150,
        "response_prefix":   "",
    },
    "adult": {
        "label":             "Adult",
        "icon":              "[A]",
        "description":       "Capable and context-aware. Handles most tasks well.",
        "temperature_delta": 0.0,
        "max_tokens_cap":    250,
        "response_prefix":   "",
    },
    "scholar": {
        "label":             "Scholar",
        "icon":              "[S]",
        "description":       "Deep analytical thinking. Strong domain knowledge.",
        "temperature_delta": -0.05,    # more focused — the AI knows more
        "max_tokens_cap":    350,
        "response_prefix":   "",
    },
    "professional": {
        "label":             "Professional",
        "icon":              "[P]",
        "description":       "Expert-level. Fully adapted to your workflow and style.",
        "temperature_delta": -0.10,
        "max_tokens_cap":    512,
        "response_prefix":   "",
    },
}


class LevelSystem:
    def __init__(self, state_path: str, ai_logger=None):
        self.state_path = state_path
        self.ai_logger = ai_logger
        self._current_level = "baby"
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def _load(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path) as f:
                    data = json.load(f)
                    lvl = data.get("level", "baby")
                    if lvl in LEVELS:
                        self._current_level = lvl
            except Exception:
                self._current_level = "baby"

    def _save(self):
        parent = os.path.dirname(self.state_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump(
                {"level": self._current_level,
                 "updated": datetime.now().isoformat()},
                f, indent=2,
            )

    # ------------------------------------------------------------------ #
    # Core evaluation                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def compute_level(experiences: int, training_sessions: int,
                      study_minutes: float) -> str:
        """Pure function — derive level from stats with no side effects."""
        result = "baby"
        for level in LEVELS:
            t = THRESHOLDS[level]
            if (experiences >= t["experiences"]
                    and training_sessions >= t["training_sessions"]
                    and study_minutes >= t["study_minutes"]):
                result = level
        return result

    def update(self, experiences: int, training_sessions: int,
               study_minutes: float) -> Optional[str]:
        """
        Re-evaluate level from current stats.
        Returns the new level name if a level-up just occurred, else None.
        """
        new_level = self.compute_level(experiences, training_sessions, study_minutes)
        old_idx = LEVELS.index(self._current_level)
        new_idx = LEVELS.index(new_level)

        if new_idx > old_idx:
            old_level = self._current_level
            self._current_level = new_level
            self._save()
            self._notify_level_up(old_level, new_level,
                                  experiences, training_sessions, study_minutes)
            return new_level

        return None

    def _notify_level_up(self, old: str, new: str, experiences: int,
                         training_sessions: int, study_minutes: float):
        traits = TRAITS[new]
        print(
            f"\n{'='*60}\n"
            f"  LEVEL UP!  {old.upper()} → {new.upper()}  {traits['icon']}\n"
            f"  {traits['description']}\n"
            f"{'='*60}\n"
        )
        if self.ai_logger:
            self.ai_logger.log(
                "LEVEL_UP",
                f"AI leveled up: {old} → {new}",
                details={
                    "from": old, "to": new,
                    "experiences": experiences,
                    "training_sessions": training_sessions,
                    "study_minutes": round(study_minutes, 1),
                },
                severity="LOW",
            )

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def current_level(self) -> str:
        return self._current_level

    def get_traits(self) -> dict:
        return TRAITS[self._current_level]

    def get_progress(self, experiences: int, training_sessions: int,
                     study_minutes: float) -> dict:
        """Returns progress toward the next level, or at_max if already Professional."""
        idx = LEVELS.index(self._current_level)
        base = {
            "level":       self._current_level,
            "label":       TRAITS[self._current_level]["label"],
            "icon":        TRAITS[self._current_level]["icon"],
            "description": TRAITS[self._current_level]["description"],
        }
        if idx == len(LEVELS) - 1:
            return {**base, "at_max": True}

        next_level = LEVELS[idx + 1]
        t = THRESHOLDS[next_level]
        return {
            **base,
            "at_max": False,
            "next_level": next_level,
            "needs": {
                "experiences":       max(0, t["experiences"] - experiences),
                "training_sessions": max(0, t["training_sessions"] - training_sessions),
                "study_minutes":     max(0.0, t["study_minutes"] - study_minutes),
            },
            "has": {
                "experiences":       experiences,
                "training_sessions": training_sessions,
                "study_minutes":     round(study_minutes, 1),
            },
        }

    def format_status(self) -> str:
        t = TRAITS[self._current_level]
        return f"{t['icon']} {t['label'].upper()} — {t['description']}"

    def all_levels_info(self) -> list:
        return [
            {
                "level": lvl,
                "label": TRAITS[lvl]["label"],
                "icon": TRAITS[lvl]["icon"],
                "description": TRAITS[lvl]["description"],
                "thresholds": THRESHOLDS[lvl],
                "current": lvl == self._current_level,
            }
            for lvl in LEVELS
        ]
