"""
SQLite-Datenbankschicht für den Server-Log (aiosqlite).

Speichert die Kanäle, die per ``.unlog`` vom Nachrichten-Log ausgenommen sind.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS unlogged_channels (
    channel_id  INTEGER PRIMARY KEY,
    guild_id    INTEGER NOT NULL,
    added_by    INTEGER,
    added_at    TEXT    NOT NULL
);
"""


class ServerLogDatabase:
    """Asynchroner Zugriff auf die SQLite-Datenbank des Server-Logs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Datenbank ist nicht verbunden.")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def get_unlogged_channels(self, guild_id: int) -> set[int]:
        async with self.conn.execute(
            "SELECT channel_id FROM unlogged_channels WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            return {row[0] async for row in cursor}

    async def add_unlogged_channel(self, guild_id: int, channel_id: int, added_by: int | None) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO unlogged_channels (channel_id, guild_id, added_by, added_at) VALUES (?, ?, ?, ?)",
            (channel_id, guild_id, added_by, datetime.now(timezone.utc).isoformat()),
        )
        await self.conn.commit()

    async def remove_unlogged_channel(self, channel_id: int) -> None:
        await self.conn.execute("DELETE FROM unlogged_channels WHERE channel_id = ?", (channel_id,))
        await self.conn.commit()
