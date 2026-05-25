from datetime import datetime


class FeedbackCollector:
    """
    Turns user corrections and ratings into training data.
    Every correction teaches the AI to do better next time.

    Correction example:
      User: "No, I meant X not Y"
      → stored as high-priority training pair
    """

    def __init__(self, experience_buffer):
        self.buffer = experience_buffer
        self._pending_response = None   # last AI response, waiting for feedback
        self._stats = {"corrections": 0, "approvals": 0, "rejections": 0}

    def set_last_response(self, user_input: str, ai_response: str):
        self._pending_response = (user_input, ai_response)

    def submit_correction(self, corrected_response: str):
        """User provides what the AI SHOULD have said."""
        if not self._pending_response:
            return
        user_input, _ = self._pending_response
        self.buffer.add_correction(user_input, corrected_response)
        self._stats["corrections"] += 1
        self._pending_response = None
        print("[Feedback] Correction saved — will improve in next training session")

    def submit_approval(self):
        """User signals the last response was good — reinforce it."""
        if not self._pending_response:
            return
        user_input, ai_response = self._pending_response
        self.buffer.add_conversation(user_input, ai_response)
        self._stats["approvals"] += 1
        self._pending_response = None

    def submit_rejection(self):
        """User signals response was bad but doesn't provide correction."""
        self._stats["rejections"] += 1
        self._pending_response = None

    def get_stats(self):
        total = sum(self._stats.values())
        approval_rate = (
            self._stats["approvals"] / total * 100 if total > 0 else 0
        )
        return {**self._stats, "total": total,
                "approval_rate": f"{approval_rate:.1f}%"}
