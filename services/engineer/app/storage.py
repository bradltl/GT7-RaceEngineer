from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import EngineerMessage


class HistoryStore:
    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS message_history (
                    id TEXT PRIMARY KEY,
                    timestamp_ms INTEGER NOT NULL,
                    priority TEXT NOT NULL,
                    category TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def add_message(self, message: EngineerMessage) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO message_history (id, timestamp_ms, priority, category, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.timestamp_ms,
                    message.priority.value,
                    message.category,
                    message.model_dump_json(),
                ),
            )
            conn.commit()

    def recent_messages(self, limit: int = 50) -> list[EngineerMessage]:
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT payload
                FROM message_history
                ORDER BY timestamp_ms DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [EngineerMessage.model_validate(json.loads(row[0])) for row in reversed(rows)]
