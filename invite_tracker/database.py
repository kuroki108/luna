"""
SQLite-Datenbankschicht für den Invite-Tracker (aiosqlite).

Speichert pro Server die Einladungslinks (``invites``) sowie die Beitritte
inklusive Inviter (``joins``). Das Modul ist unabhängig vom Cog und kennt
keine discord.py-Objekte – es arbeitet nur mit einfachen Werten.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    guild_id    INTEGER NOT NULL,
    code        TEXT    NOT NULL,
    inviter_id  INTEGER,
    channel_id  INTEGER,
    uses        INTEGER NOT NULL DEFAULT 0,
    max_uses    INTEGER NOT NULL DEFAULT 0,
    is_vanity   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT,
    deleted_at  TEXT,
    PRIMARY KEY (guild_id, code)
);

CREATE TABLE IF NOT EXISTS joins (
    guild_id     INTEGER NOT NULL,
    member_id    INTEGER NOT NULL,
    inviter_id   INTEGER,
    invite_code  TEXT,
    join_type    TEXT    NOT NULL,
    joined_at    TEXT    NOT NULL,
    left_at      TEXT,
    join_count   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_joins_inviter ON joins (guild_id, inviter_id);
"""

# Zählt nur eindeutig zugeordnete Einladungen, Selbsteinladungen ausgenommen.
_STATS_SELECT = """
SELECT inviter_id,
       COALESCE(SUM(left_at IS NULL), 0)     AS active,
       COALESCE(SUM(left_at IS NOT NULL), 0) AS left_count,
       COUNT(*)                              AS total
FROM joins
WHERE guild_id = ?
  AND join_type = 'invite'
  AND inviter_id IS NOT NULL
  AND inviter_id != member_id
"""


class InviteRecord(Protocol):
    """Alles, was als Invite gespeichert werden kann (z. B. ``CachedInvite``)."""

    code: str
    inviter_id: int | None
    channel_id: int | None
    uses: int
    max_uses: int
    created_at: datetime | None
    is_vanity: bool


@dataclass(slots=True, frozen=True)
class InviterStats:
    inviter_id: int
    active: int  # noch auf dem Server
    left: int    # wieder gegangen
    total: int


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _now() -> str:
    return datetime.now(UTC).isoformat()


class InviteDatabase:
    """Asynchroner Zugriff auf die SQLite-Datenbank (eine Verbindung pro Bot)."""

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
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ---- Invites ---------------------------------------------------------- #

    async def _upsert_invites(self, guild_id: int, invites: Iterable[InviteRecord]) -> None:
        await self.conn.executemany(
            """
            INSERT INTO invites (guild_id, code, inviter_id, channel_id, uses,
                                 max_uses, is_vanity, created_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT (guild_id, code) DO UPDATE SET
                inviter_id = COALESCE(excluded.inviter_id, invites.inviter_id),
                channel_id = excluded.channel_id,
                uses       = excluded.uses,
                max_uses   = excluded.max_uses,
                is_vanity  = excluded.is_vanity,
                deleted_at = NULL
            """,
            [
                (guild_id, inv.code, inv.inviter_id, inv.channel_id, inv.uses,
                 inv.max_uses, int(inv.is_vanity), _iso(inv.created_at))
                for inv in invites
            ],
        )

    async def save_invite(self, guild_id: int, invite: InviteRecord) -> None:
        await self._upsert_invites(guild_id, [invite])
        await self.conn.commit()

    async def save_snapshot(self, guild_id: int, invites: Iterable[InviteRecord]) -> None:
        """Speichert den vollständigen Invite-Stand und markiert fehlende als gelöscht."""
        invites = list(invites)
        await self._upsert_invites(guild_id, invites)

        codes = [inv.code for inv in invites]
        placeholders = ",".join("?" * len(codes))
        code_filter = f"AND code NOT IN ({placeholders})" if codes else ""
        await self.conn.execute(
            f"UPDATE invites SET deleted_at = ? "
            f"WHERE guild_id = ? AND deleted_at IS NULL {code_filter}",
            (_now(), guild_id, *codes),
        )
        await self.conn.commit()

    async def mark_invite_deleted(self, guild_id: int, code: str) -> None:
        await self.conn.execute(
            "UPDATE invites SET deleted_at = ? WHERE guild_id = ? AND code = ?",
            (_now(), guild_id, code),
        )
        await self.conn.commit()

    # ---- Beitritte -------------------------------------------------------- #

    async def record_join(
        self,
        guild_id: int,
        member_id: int,
        *,
        join_type: str,
        inviter_id: int | None,
        invite_code: str | None,
        joined_at: datetime,
    ) -> None:
        # Bei erneutem Beitritt zählt die aktuellste Zuordnung.
        await self.conn.execute(
            """
            INSERT INTO joins (guild_id, member_id, inviter_id, invite_code,
                               join_type, joined_at, left_at, join_count)
            VALUES (?, ?, ?, ?, ?, ?, NULL, 1)
            ON CONFLICT (guild_id, member_id) DO UPDATE SET
                inviter_id  = excluded.inviter_id,
                invite_code = excluded.invite_code,
                join_type   = excluded.join_type,
                joined_at   = excluded.joined_at,
                left_at     = NULL,
                join_count  = joins.join_count + 1
            """,
            (guild_id, member_id, inviter_id, invite_code, join_type, _iso(joined_at)),
        )
        await self.conn.commit()

    async def mark_left(self, guild_id: int, member_id: int) -> None:
        await self.conn.execute(
            "UPDATE joins SET left_at = ? WHERE guild_id = ? AND member_id = ?",
            (_now(), guild_id, member_id),
        )
        await self.conn.commit()

    async def get_join(self, guild_id: int, member_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute(
            "SELECT * FROM joins WHERE guild_id = ? AND member_id = ?",
            (guild_id, member_id),
        ) as cursor:
            return await cursor.fetchone()

    # ---- Statistiken ------------------------------------------------------ #

    async def get_inviter_stats(self, guild_id: int, inviter_id: int) -> InviterStats:
        async with self.conn.execute(
            _STATS_SELECT + " AND inviter_id = ? GROUP BY inviter_id",
            (guild_id, inviter_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return InviterStats(inviter_id, 0, 0, 0)
        return InviterStats(row["inviter_id"], row["active"], row["left_count"], row["total"])

    async def get_leaderboard(self, guild_id: int, limit: int) -> list[InviterStats]:
        async with self.conn.execute(
            _STATS_SELECT
            + " GROUP BY inviter_id HAVING active > 0"
            + " ORDER BY active DESC, total DESC LIMIT ?",
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            InviterStats(r["inviter_id"], r["active"], r["left_count"], r["total"])
            for r in rows
        ]

    async def count_unknown_joins(self, guild_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM joins WHERE guild_id = ? AND join_type = 'unknown'",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0
