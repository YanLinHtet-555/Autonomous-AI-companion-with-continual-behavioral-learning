import sqlite3
import json
import os
import random
from datetime import datetime


class ExperienceBuffer:
    """
    Persistent SQLite store for all experiences:
    - user conversations
    - AI responses
    - monitoring observations (as natural language)
    - user corrections / feedback

    This is the AI's long-term episodic memory and continual training corpus.
    """

    def __init__(self, db_path, encryption=None,
                 data_gate=None, ai_logger=None):
        self.db_path = db_path
        self.encryption = encryption
        self.data_gate = data_gate    # DataAccessGate — gates bulk background reads
        self.ai_logger = ai_logger
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    timestamp TEXT NOT NULL,
                    used_in_training INTEGER DEFAULT 0,
                    feedback_score INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_type ON experiences(type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON experiences(timestamp)
            """)

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def add(self, content: str, exp_type: str = "general", metadata: dict = None):
        if self.encryption:
            content = self.encryption.encrypt(content)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO experiences (type, content, metadata, timestamp) VALUES (?,?,?,?)",
                (exp_type, content, json.dumps(metadata or {}),
                 datetime.now().isoformat()),
            )

    def add_conversation(self, user_text: str, ai_response: str):
        text = f"<user> {user_text} <ai> {ai_response}"
        self.add(text, exp_type="conversation")

    def add_observation(self, text: str):
        self.add(text, exp_type="observation")

    def add_correction(self, original: str, corrected: str):
        text = f"<user> {original} <ai> {corrected}"
        self.add(text, exp_type="correction", metadata={"is_correction": True})

    def get_for_training(self, limit=500, types=None):
        """
        Local training read — always permitted.
        Data stays on this machine. AI uses this to learn from your activity.
        Logged to audit trail so you can always see what was read.
        Export to external destinations is blocked separately by NetworkGuard.
        """
        if self.ai_logger:
            self.ai_logger.data_read("experience_buffer", limit, "local training")

        types = types or ["conversation", "observation", "correction"]
        placeholders = ",".join("?" * len(types))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT id, content, type FROM experiences "
                f"WHERE type IN ({placeholders}) "
                f"ORDER BY timestamp DESC LIMIT ?",
                (*types, limit),
            ).fetchall()
        results = []
        for row_id, content, exp_type in rows:
            if self.encryption:
                try:
                    content = self.encryption.decrypt(content)
                except Exception:
                    if self.ai_logger:
                        self.ai_logger.suspicious(
                            "Decryption failure — possible data corruption",
                            details={"exp_id": row_id},
                        )
                    continue
            results.append({"id": row_id, "content": content, "type": exp_type})
        return results

    def get_replay_sample(self, n=50):
        """
        Random sample for continual learning replay buffer — always permitted locally.
        Prevents the AI from forgetting old knowledge when learning new things.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT content FROM experiences ORDER BY RANDOM() LIMIT ?", (n,)
            ).fetchall()
        results = []
        for (content,) in rows:
            if self.encryption:
                try:
                    content = self.encryption.decrypt(content)
                except Exception:
                    continue
            results.append(content)
        return results

    def export_to_file(self, output_path: str, data_gate=None):
        """
        Export experiences to a plaintext file.
        THIS is the operation that requires explicit user permission —
        because it creates an unencrypted copy outside the secure store.
        """
        if data_gate:
            allowed = data_gate.request_export(
                reason=f"Exporting all experiences to {output_path}",
            )
            if not allowed:
                print("[ExperienceBuffer] Export blocked — user did not permit.")
                return False

        rows = self.get_for_training(limit=99999)
        with open(output_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(f"[{row['type']}] {row['content']}\n\n")
        print(f"[ExperienceBuffer] Exported {len(rows)} experiences to {output_path}")
        return True

    def mark_trained(self, ids):
        with self._conn() as conn:
            conn.executemany(
                "UPDATE experiences SET used_in_training=1 WHERE id=?",
                [(i,) for i in ids],
            )

    def get_untrained(self, limit=200):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, content FROM experiences "
                "WHERE used_in_training=0 ORDER BY timestamp ASC LIMIT ?",
                (limit,),
            ).fetchall()
        results = []
        for row_id, content in rows:
            if self.encryption:
                try:
                    content = self.encryption.decrypt(content)
                except Exception:
                    continue
            results.append({"id": row_id, "content": content})
        return results

    def stats(self):
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]
            by_type = conn.execute(
                "SELECT type, COUNT(*) FROM experiences GROUP BY type"
            ).fetchall()
            trained = conn.execute(
                "SELECT COUNT(*) FROM experiences WHERE used_in_training=1"
            ).fetchone()[0]
        return {
            "total": total,
            "trained": trained,
            "untrained": total - trained,
            "by_type": dict(by_type),
        }

    def delete(self, exp_id):
        with self._conn() as conn:
            conn.execute("DELETE FROM experiences WHERE id=?", (exp_id,))

    def delete_all(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM experiences")
