from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY CHECK (typeof(user_id) = 'integer'),
    total_xp        INTEGER NOT NULL DEFAULT 0 CHECK (total_xp >= 0),
    last_message_ts INTEGER NOT NULL DEFAULT 0,   -- Unix-Zeit, für Text-Cooldown
    voice_day       TEXT,                         -- ISO-Datum (UTC) des Voice-Zählers
    voice_minutes   INTEGER NOT NULL DEFAULT 0    -- Voice-Minuten mit XP an voice_day
);
CREATE INDEX IF NOT EXISTS idx_users_totalxp ON users (total_xp DESC);
CREATE TABLE IF NOT EXISTS boosts (
    kind     TEXT PRIMARY KEY CHECK (kind IN ('text', 'voice')),
    percent  INTEGER NOT NULL CHECK (percent > 0),
    ends_at  INTEGER NOT NULL                     -- Unix-Zeit
);
"""


class LevelingDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Verbindung & Schema
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        try:
            await self._conn.execute("PRAGMA busy_timeout=5000")
            await self._check_old_schema()
            await self._conn.executescript(SCHEMA)
            await self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            await self._conn.commit()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("LevelingDatabase ist nicht verbunden – connect() fehlt.")
        return self._conn

    async def _check_old_schema(self) -> None:
        """Bricht mit klarer Meldung ab, wenn noch eine alte DB-Datei (Schema v1/v2) verwendet wird."""
        async with self.conn.execute("PRAGMA table_info(users)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
        if columns and ("voice_day" not in columns or "guild_id" in columns):
            raise RuntimeError(
                f"{self.path} nutzt noch das alte Leveling-Schema. "
                "Ersetze die Datei durch die neue leere Datenbank oder lösche sie "
                "(sie wird dann automatisch neu angelegt)."
            )

    # ------------------------------------------------------------------
    # XP (alle Schreibzugriffe atomar)
    # ------------------------------------------------------------------

    async def add_text_xp(
        self, user_id: int, amount: int, now: int, cooldown: int
    ) -> int | None:
        """Vergibt Text-XP, wenn der Cooldown abgelaufen ist.

        Returns: neue Gesamt-XP oder None, wenn der Cooldown noch aktiv war.
        """
        async with self.conn.execute(
            """
            INSERT INTO users (user_id, total_xp, last_message_ts)
            VALUES (?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
                total_xp        = users.total_xp + excluded.total_xp,
                last_message_ts = excluded.last_message_ts
            WHERE users.last_message_ts <= excluded.last_message_ts - ?
            RETURNING total_xp
            """,
            (user_id, amount, now, cooldown),
        ) as cur:
            row = await cur.fetchone()
        await self.conn.commit()
        return row[0] if row else None

    async def add_voice_xp(
        self, user_id: int, amount: int, day: str, cap_minutes: int
    ) -> int | None:
        """Vergibt Voice-XP für eine Minute, solange das Tageslimit nicht erreicht ist.

        `day` ist das aktuelle Datum (ISO). Wechselt der Tag, startet der Zähler neu.
        `cap_minutes = 0` bedeutet kein Limit.

        Returns: neue Gesamt-XP oder None, wenn das Tageslimit erreicht ist.
        """
        async with self.conn.execute(
            """
            INSERT INTO users (user_id, total_xp, voice_day, voice_minutes)
            VALUES (?, ?, ?, 1)
            ON CONFLICT (user_id) DO UPDATE SET
                total_xp      = users.total_xp + excluded.total_xp,
                voice_minutes = CASE WHEN users.voice_day IS excluded.voice_day
                                    THEN users.voice_minutes + 1 ELSE 1 END,
                voice_day     = excluded.voice_day
            WHERE users.voice_day IS NOT excluded.voice_day
                OR ? = 0
                OR users.voice_minutes < ?
            RETURNING total_xp
            """,
            (user_id, amount, day, cap_minutes, cap_minutes),
        ) as cur:
            row = await cur.fetchone()
        await self.conn.commit()
        return row[0] if row else None

    async def change_xp(self, user_id: int, delta: int) -> int:
        """Addiert (oder subtrahiert) XP, nie unter 0. Returns: neue Gesamt-XP."""
        async with self.conn.execute(
            """
            INSERT INTO users (user_id, total_xp) VALUES (?, MAX(0, ?))
            ON CONFLICT (user_id) DO UPDATE SET
                total_xp = MAX(0, users.total_xp + ?)
            RETURNING total_xp
            """,
            (user_id, delta, delta),
        ) as cur:
            row = await cur.fetchone()
        await self.conn.commit()
        return row[0]

    async def get_total_xp(self, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT total_xp FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def get_rank(self, user_id: int) -> int:
        """Platz im Server-Ranking (1 = bester). Gleichstand teilt sich den Platz."""
        total = await self.get_total_xp(user_id)
        async with self.conn.execute(
            "SELECT COUNT(*) FROM users WHERE total_xp > ?", (total,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] + 1

    async def get_leaderboard(self, limit: int) -> list[tuple[int, int]]:
        async with self.conn.execute(
            """
            SELECT user_id, total_xp FROM users
            WHERE total_xp > 0
            ORDER BY total_xp DESC, user_id ASC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            return [(r[0], r[1]) for r in await cur.fetchall()]

    # ------------------------------------------------------------------
    # XP-Boosts (.xprise)
    # ------------------------------------------------------------------

    async def set_boost(self, kind: str, percent: int, ends_at: int) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO boosts (kind, percent, ends_at) VALUES (?, ?, ?)", (kind, percent, ends_at)
        )
        await self.conn.commit()

    async def clear_boost(self, kind: str) -> None:
        await self.conn.execute("DELETE FROM boosts WHERE kind = ?", (kind,))
        await self.conn.commit()

    async def get_boosts(self) -> dict[str, tuple[int, int]]:
        """Returns: {kind: (prozent, ends_at)} – auch abgelaufene."""
        async with self.conn.execute("SELECT kind, percent, ends_at FROM boosts") as cur:
            return {r[0]: (r[1], r[2]) for r in await cur.fetchall()}

    async def get_all_users(self) -> list[tuple[int, int]]:
        async with self.conn.execute("SELECT user_id, total_xp FROM users") as cur:
            return [(r[0], r[1]) for r in await cur.fetchall()]
