"""SQLite-Datenbankschicht der Stats (aiosqlite), Standard: data/stats.sqlite3.

Daten liegen in Stunden-Buckets: hour = unix_ts // 3600 (UTC).
"""
from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from pathlib import Path

import aiosqlite

# kind -> (Tabelle, Wertspalte). Feste Namen, nie aus User-Input.
_KINDS = {
    "messages": ("message_stats", "count"),
    "voice": ("voice_stats", "seconds"),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS message_stats (
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    hour       INTEGER NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, channel_id, hour)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_msg_guild_hour ON message_stats (guild_id, hour);

CREATE TABLE IF NOT EXISTS voice_stats (
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    hour       INTEGER NOT NULL,
    seconds    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, channel_id, hour)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_voice_guild_hour ON voice_stats (guild_id, hour);
"""

Row = tuple[int, int, int, int, int]  # guild, user, channel, hour, value


def current_hour(ts: float | None = None) -> int:
    return int((time.time() if ts is None else ts) // 3600)


def window_start(days: int, now_hour: int) -> int:
    """Erster Bucket eines rollenden Fensters über `days` Tage (inkl. laufender Stunde)."""
    return now_hour - days * 24 + 1


class StatsDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------ setup
    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Stats-Datenbank ist nicht verbunden")
        return self._db

    # ----------------------------------------------------------------- writes
    async def _add(self, kind: str, rows: Iterable[Row]) -> None:
        table, col = _KINDS[kind]
        rows = list(rows)
        if not rows:
            return
        await self.db.executemany(
            f"INSERT INTO {table} (guild_id, user_id, channel_id, hour, {col}) VALUES (?, ?, ?, ?, ?) "
            f"ON CONFLICT (guild_id, user_id, channel_id, hour) DO UPDATE SET {col} = {col} + excluded.{col}",
            rows,
        )
        await self.db.commit()

    async def add_messages(self, rows: Iterable[Row]) -> None:
        await self._add("messages", rows)

    async def add_voice(self, rows: Iterable[Row]) -> None:
        await self._add("voice", rows)

    async def purge(self, older_than_days: int, now_hour: int | None = None) -> None:
        cutoff = (now_hour if now_hour is not None else current_hour()) - older_than_days * 24
        for table, _ in _KINDS.values():
            await self.db.execute(f"DELETE FROM {table} WHERE hour < ?", (cutoff,))
        await self.db.commit()

    # ------------------------------------------------------------------ reads
    async def _window_sums(
        self, kind: str, windows: Sequence[int], now_hour: int, where: str, params: tuple
    ) -> list[int]:
        table, col = _KINDS[kind]
        starts = [window_start(d, now_hour) for d in windows]
        cases = ", ".join(f"COALESCE(SUM(CASE WHEN hour >= ? THEN {col} END), 0)" for _ in starts)
        sql = f"SELECT {cases} FROM {table} WHERE {where} AND hour >= ?"
        async with self.db.execute(sql, (*starts, *params, min(starts))) as cur:
            row = await cur.fetchone()
        return [int(v) for v in row] if row else [0] * len(windows)

    async def user_totals(
        self, guild_id: int, user_id: int, kind: str, windows: Sequence[int], now_hour: int | None = None
    ) -> list[int]:
        now_hour = current_hour() if now_hour is None else now_hour
        return await self._window_sums(kind, windows, now_hour, "guild_id = ? AND user_id = ?", (guild_id, user_id))

    async def server_totals(
        self, guild_id: int, kind: str, windows: Sequence[int], now_hour: int | None = None
    ) -> list[int]:
        now_hour = current_hour() if now_hour is None else now_hour
        return await self._window_sums(kind, windows, now_hour, "guild_id = ?", (guild_id,))

    async def user_rank(
        self, guild_id: int, user_id: int, kind: str, days: int, now_hour: int | None = None
    ) -> int | None:
        """Platz des Users (1 = aktivster). None, wenn er im Zeitraum nichts hat."""
        table, col = _KINDS[kind]
        now_hour = current_hour() if now_hour is None else now_hour
        sql = f"""
            WITH totals AS (
                SELECT user_id, SUM({col}) AS total FROM {table}
                WHERE guild_id = ? AND hour >= ? GROUP BY user_id HAVING total > 0
            )
            SELECT r FROM (SELECT user_id, RANK() OVER (ORDER BY total DESC) AS r FROM totals)
            WHERE user_id = ?
        """
        async with self.db.execute(sql, (guild_id, window_start(days, now_hour), user_id)) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else None

    async def top_members(
        self, guild_id: int, kind: str, days: int, limit: int, now_hour: int | None = None
    ) -> list[tuple[int, int]]:
        table, col = _KINDS[kind]
        now_hour = current_hour() if now_hour is None else now_hour
        sql = f"""
            SELECT user_id, SUM({col}) AS total FROM {table}
            WHERE guild_id = ? AND hour >= ?
            GROUP BY user_id HAVING total > 0
            ORDER BY total DESC, user_id LIMIT ?
        """
        async with self.db.execute(sql, (guild_id, window_start(days, now_hour), limit)) as cur:
            return [(int(u), int(t)) for u, t in await cur.fetchall()]
