from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Sequence


SCHEMA = """
CREATE TABLE IF NOT EXISTS dialogue_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dialogue_messages_user ON dialogue_messages(user_id, id);
"""


class DialogueStorage:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_history(self, user_id: int, limit: int) -> List[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM dialogue_messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        result = []
        for row in reversed(rows):
            content = row["content"]
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                pass
            result.append({"role": row["role"], "content": content})
        return result

    def append(self, user_id: int, role: str, content: str | list | dict) -> None:
        with self._connect() as conn:
            content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            conn.execute(
                "INSERT INTO dialogue_messages (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content_str),
            )

    def replace_history(self, user_id: int, messages: Sequence[dict]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM dialogue_messages WHERE user_id = ?", (user_id,))
            rows = []
            for msg in messages:
                content = msg["content"]
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                rows.append((user_id, msg["role"], content))
            conn.executemany(
                "INSERT INTO dialogue_messages (user_id, role, content) VALUES (?, ?, ?)",
                rows,
            )

    def reset_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM dialogue_messages WHERE user_id = ?", (user_id,))

