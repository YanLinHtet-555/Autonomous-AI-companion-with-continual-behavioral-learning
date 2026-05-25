"""
CoLearner — the AI learns alongside you in real time.

When you study something, the AI:
  1. Detects the topic from your activity (browser, notes, code)
  2. Learns it by adding it to the experience buffer as training data
  3. Becomes a study partner — explains, quizzes, reinforces
  4. Tracks your learning progress per topic over time
  5. Connects new knowledge to what it already knows about your work

The more you study, the more the AI understands about your domain.
Next time you encounter the same concept in your code, it already knows it.
"""

import re
from datetime import datetime
from collections import defaultdict


class CoLearner:
    """
    Bridges the LearningDetector and the ExperienceBuffer.

    Converts detected learning sessions into structured training data
    and provides study-partner features: explain, quiz, summarise.
    """

    def __init__(self, experience_buffer, ai_logger=None):
        self.buffer = experience_buffer
        self.ai_logger = ai_logger

        # topic -> list of session dicts
        self._knowledge_map: dict = defaultdict(list)

        # topic -> list of key concepts extracted
        self._concepts: dict = defaultdict(list)

        # shared notes: topic -> list of strings user shared with AI
        self._shared_notes: dict = defaultdict(list)

        # total learning time per topic (minutes)
        self._study_time: dict = defaultdict(float)

    # ------------------------------------------------------------------ #
    # Called by LearningDetector on each session                          #
    # ------------------------------------------------------------------ #

    def on_learning_session(self, session: dict):
        """
        Called every time a learning session is closed (user stopped reading).
        Converts the session into training data and stores it.
        """
        topic = session.get("topic", "unknown")
        duration_sec = session.get("duration_sec", 0)
        duration_min = round(duration_sec / 60, 1)
        timestamp = session.get("timestamp", datetime.now().isoformat())
        start = session.get("start", "")
        manual = session.get("manual", False)

        self._knowledge_map[topic].append(session)
        self._study_time[topic] += duration_min

        # Build a natural language training sentence that the model learns from
        date_str = datetime.now().strftime("%A %B %d")
        training_text = (
            f"On {date_str}, the user studied: {topic}. "
            f"They spent {duration_min} minutes on this topic. "
            f"The AI learned this topic together with the user. "
            f"Total study time on this topic: "
            f"{self._study_time[topic]:.1f} minutes across "
            f"{len(self._knowledge_map[topic])} sessions."
        )

        self.buffer.add(training_text, exp_type="co_learning",
                        metadata={"topic": topic, "duration_min": duration_min})

        if self.ai_logger:
            self.ai_logger.log(
                "CO_LEARNING",
                f"Learned alongside user: {topic} ({duration_min} min)",
                details={"topic": topic, "sessions": len(self._knowledge_map[topic])},
                severity="LOW",
            )

        print(
            f"\n[CoLearner] Learned with you: '{topic}' "
            f"({duration_min} min) — stored as training data."
        )

    # ------------------------------------------------------------------ #
    # User shares notes / content with AI                                 #
    # ------------------------------------------------------------------ #

    def share_content(self, topic: str, content: str):
        """
        User pastes notes, a code snippet, or text for the AI to learn.
        Both user and AI now know this content.
        """
        self._shared_notes[topic].append(content)

        training_text = (
            f"The user shared the following content about '{topic}' "
            f"for the AI to learn:\n{content}"
        )
        self.buffer.add(training_text, exp_type="co_learning",
                        metadata={"topic": topic, "shared": True})

        # Extract and store key concepts
        concepts = self._extract_concepts(content)
        if concepts:
            self._concepts[topic].extend(concepts)
            concept_text = (
                f"Key concepts in '{topic}': {', '.join(concepts)}."
            )
            self.buffer.add(concept_text, exp_type="co_learning",
                            metadata={"topic": topic, "type": "concepts"})

        if self.ai_logger:
            self.ai_logger.log(
                "CO_LEARNING",
                f"User shared content on '{topic}' ({len(content)} chars)",
                severity="LOW",
            )

        return concepts

    # ------------------------------------------------------------------ #
    # Study partner features                                               #
    # ------------------------------------------------------------------ #

    def get_study_summary(self, topic: str = None) -> str:
        """
        Returns a summary of what was studied — used by the AI when answering
        questions to provide context-aware responses.
        """
        if topic:
            sessions = self._knowledge_map.get(topic, [])
            total_min = self._study_time.get(topic, 0)
            concepts = self._concepts.get(topic, [])
            notes_count = len(self._shared_notes.get(topic, []))

            if not sessions:
                return f"No recorded study sessions on '{topic}' yet."

            lines = [
                f"Study summary for '{topic}':",
                f"  Sessions    : {len(sessions)}",
                f"  Total time  : {total_min:.1f} minutes",
                f"  Last studied: {sessions[-1]['timestamp'][:10]}",
            ]
            if concepts:
                lines.append(f"  Concepts    : {', '.join(concepts[:10])}")
            if notes_count:
                lines.append(f"  Shared notes: {notes_count}")
            return "\n".join(lines)

        else:
            # All topics
            if not self._knowledge_map:
                return "No study sessions recorded yet."
            lines = ["All studied topics:"]
            for t, sessions in sorted(
                self._study_time.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(
                    f"  {t[:50]:<52} "
                    f"{self._study_time[t]:.0f}min  "
                    f"({len(sessions)} sessions)"
                )
            return "\n".join(lines)

    def build_quiz_prompt(self, topic: str) -> str:
        """
        Builds a prompt for the AI model to generate a quiz question
        about a studied topic.
        """
        concepts = self._concepts.get(topic, [])
        notes = self._shared_notes.get(topic, [])
        sessions = self._knowledge_map.get(topic, [])

        prompt = f"<user> Quiz me on: {topic}"
        if concepts:
            prompt += f". Key concepts we studied: {', '.join(concepts[:5])}"
        if notes:
            prompt += f". My notes: {notes[-1][:200]}"
        prompt += " <ai>"
        return prompt

    def build_explain_prompt(self, concept: str, topic_context: str = "") -> str:
        """Builds a prompt for the AI to explain a concept based on shared context."""
        prompt = f"<user> Explain: {concept}"
        if topic_context:
            prompt += f" (in the context of {topic_context})"

        # Find if we have notes on this concept
        for topic, notes in self._shared_notes.items():
            for note in notes:
                if concept.lower() in note.lower():
                    prompt += f". Here is relevant context from my notes: {note[:300]}"
                    break

        prompt += " <ai>"
        return prompt

    def build_review_prompt(self, topic: str) -> str:
        """Builds a prompt for the AI to review what was learned together."""
        total_min = self._study_time.get(topic, 0)
        concepts = self._concepts.get(topic, [])
        prompt = (
            f"<user> We studied '{topic}' together for {total_min:.0f} minutes. "
            f"Summarise what we learned"
        )
        if concepts:
            prompt += f", covering: {', '.join(concepts[:8])}"
        prompt += ". <ai>"
        return prompt

    # ------------------------------------------------------------------ #
    # Concept extraction (lightweight, no ML required)                    #
    # ------------------------------------------------------------------ #

    def _extract_concepts(self, text: str) -> list:
        """
        Simple keyword extraction: capitalized terms, code identifiers,
        and domain terms from the text.
        """
        concepts = set()

        # Capitalized multi-word terms (e.g. "Gradient Descent", "Neural Network")
        caps = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
        concepts.update(caps[:10])

        # Technical terms in backticks or quotes
        backtick_terms = re.findall(r'`([^`]{2,40})`', text)
        concepts.update(backtick_terms[:10])

        # Acronyms (2-6 uppercase letters)
        acronyms = re.findall(r'\b[A-Z]{2,6}\b', text)
        concepts.update(a for a in acronyms if len(a) >= 2)

        # def/class names in code
        code_names = re.findall(r'\b(?:def|class|function)\s+(\w+)', text)
        concepts.update(code_names[:5])

        return sorted(concepts)[:20]

    # ------------------------------------------------------------------ #
    # Persistence helpers                                                  #
    # ------------------------------------------------------------------ #

    def get_context_for_topic(self, topic: str) -> str:
        """
        Returns a compact context string for injection into chat prompts —
        so the AI can give better answers about topics you've studied together.
        """
        parts = []
        total = self._study_time.get(topic, 0)
        if total:
            parts.append(f"We studied '{topic}' together for {total:.0f} min.")
        concepts = self._concepts.get(topic, [])
        if concepts:
            parts.append(f"Concepts covered: {', '.join(concepts[:6])}.")
        notes = self._shared_notes.get(topic, [])
        if notes:
            parts.append(f"Your notes: {notes[-1][:200]}")
        return " ".join(parts)

    def get_all_topics(self) -> list:
        return list(self._knowledge_map.keys())

    def get_total_study_minutes(self) -> float:
        return sum(self._study_time.values())
