"""Persistent store for each user's currently-active Kilo session.

Even though the bot allows a single Telegram user, the store is keyed by user id
so it can be extended to many owners later without changing the interface. Data
is kept in an ``aiosqlite`` database so the active session survives bot
restarts.
"""

from __future__ import annotations

import logging
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS active_sessions (
    user_id   INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    title     TEXT
)
"""

_PINS_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_pins (
    user_id   INTEGER PRIMARY KEY,
    chat_id   INTEGER NOT NULL,
    message_id INTEGER NOT NULL
)
"""


class SessionStore:
    """Keyed access to active-session records backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open the database connection and create the schema if needed."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(_SCHEMA)
        await self._db.execute(_PINS_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _check(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SessionStore is not open")
        return self._db

    async def get_active(self, user_id: int) -> str | None:
        """Return the active session id for ``user_id`` or ``None``."""
        db = self._check()
        cursor = await db.execute(
            "SELECT session_id FROM active_sessions WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row["session_id"] if row else None

    async def set_active(self, user_id: int, session_id: str, title: str | None = None) -> None:
        """Record ``session_id`` as the active session for ``user_id``."""
        db = self._check()
        await db.execute(
            """
            INSERT INTO active_sessions (user_id, session_id, title)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET session_id = excluded.session_id,
                                               title = excluded.title
            """,
            (user_id, session_id, title),
        )
        await db.commit()

    async def clear(self, user_id: int) -> None:
        """Remove the active-session record for ``user_id``."""
        db = self._check()
        await db.execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
        await db.commit()

    async def get_pin(self, user_id: int) -> tuple[int, int] | None:
        """Return the ``(chat_id, message_id)`` pin for ``user_id`` or ``None``."""
        db = self._check()
        cursor = await db.execute(
            "SELECT chat_id, message_id FROM session_pins WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return (row["chat_id"], row["message_id"]) if row else None

    async def set_pin(self, user_id: int, chat_id: int, message_id: int) -> None:
        """Record the pinned-message location used to shows the active session."""
        db = self._check()
        await db.execute(
            """
            INSERT INTO session_pins (user_id, chat_id, message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET chat_id = excluded.chat_id,
                                               message_id = excluded.message_id
            """,
            (user_id, chat_id, message_id),
        )
        await db.commit()

    async def clear_pin(self, user_id: int) -> None:
        """Remove the pinned-message record for ``user_id``."""
        db = self._check()
        await db.execute("DELETE FROM session_pins WHERE user_id = ?", (user_id,))
        await db.commit()

    async def _rows(self) -> list[dict[str, Any]]:
        db = self._check()
        cursor = await db.execute("SELECT user_id, session_id, title FROM active_sessions")
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(row) for row in rows]
