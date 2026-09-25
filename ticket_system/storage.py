from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import aiosqlite

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATABASE_PATH = DATA_DIR / "tickets.sqlite3"


@dataclass
class TicketData:
    channel_id: int
    type: str  # "support" | "support_report" | "support_admin" | "application_supporter"
    opener_id: int
    created_at: float = field(default_factory=time.time)
    closed: bool = False
    added_users: list[int] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _from_row(row: tuple) -> "TicketData":
        channel_id, type_, opener_id, created_at, closed, added_users_json, answers_json = row
        return TicketData(
            channel_id=channel_id,
            type=type_,
            opener_id=opener_id,
            created_at=created_at,
            closed=bool(closed),
            added_users=json.loads(added_users_json),
            answers=json.loads(answers_json),
        )


class TicketStore:

    def __init__(self) -> None:
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    def bind(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def connect(self, path: Path = DATABASE_PATH) -> None:
        if self._conn is not None:
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(path)
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                type TEXT NOT NULL,
                opener_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                closed INTEGER NOT NULL DEFAULT 0,
                added_users TEXT NOT NULL DEFAULT '[]',
                answers TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_counters (
                counter_key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError()
        return self._conn

    async def get_ticket(self, channel_id: int) -> Optional[TicketData]:
        conn = self._require_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT channel_id, type, opener_id, created_at, closed, added_users, answers "
                "FROM tickets WHERE channel_id = ?",
                (channel_id,),
            )
            row = await cur.fetchone()
            return TicketData._from_row(row) if row else None

    async def save_ticket(self, ticket: TicketData) -> None:
        conn = self._require_conn()
        async with self._lock:
            await conn.execute(
                """
                INSERT INTO tickets (channel_id, type, opener_id, created_at, closed, added_users, answers)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (channel_id) DO UPDATE SET
                    type = excluded.type, opener_id = excluded.opener_id, created_at = excluded.created_at,
                    closed = excluded.closed,
                    added_users = excluded.added_users, answers = excluded.answers
                """,
                (
                    ticket.channel_id,
                    ticket.type,
                    ticket.opener_id,
                    ticket.created_at,
                    int(ticket.closed),
                    json.dumps(ticket.added_users),
                    json.dumps(ticket.answers),
                ),
            )
            await conn.commit()

    async def delete_ticket(self, channel_id: int) -> None:
        conn = self._require_conn()
        async with self._lock:
            await conn.execute("DELETE FROM tickets WHERE channel_id = ?", (channel_id,))
            await conn.commit()

    async def open_tickets_by_user(self, user_id: int, type_prefix: str) -> list[TicketData]:
        """Alle offenen Tickets eines Nutzers, deren type mit type_prefix beginnt."""
        conn = self._require_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT channel_id, type, opener_id, created_at, closed, added_users, answers "
                "FROM tickets WHERE opener_id = ? AND type LIKE ? AND closed = 0",
                (user_id, f"{type_prefix}%"),
            )
            rows = await cur.fetchall()
            return [TicketData._from_row(row) for row in rows]

    async def reserve_ticket_slot(
        self, user_id: int, type_prefix: str, max_allowed: int, counter_key: str
    ) -> Optional[int]:
        """Prueft das Ticket-Limit und zieht bei freiem Slot atomar einen neuen Zaehlerwert.

        Haelt den Lock ueber Pruefung + Inkrement, damit zwei gleichzeitige
        Ticket-Erstellungen desselben Nutzers das Limit nicht umgehen koennen.
        Gibt None zurueck, wenn das Limit bereits erreicht ist.
        """
        conn = self._require_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE opener_id = ? AND type LIKE ? AND closed = 0",
                (user_id, f"{type_prefix}%"),
            )
            (open_count,) = await cur.fetchone()
            if open_count >= max_allowed:
                return None

            await conn.execute(
                """
                INSERT INTO ticket_counters (counter_key, value) VALUES (?, 1)
                ON CONFLICT (counter_key) DO UPDATE SET value = value + 1
                """,
                (counter_key,),
            )
            cur = await conn.execute(
                "SELECT value FROM ticket_counters WHERE counter_key = ?", (counter_key,)
            )
            (value,) = await cur.fetchone()
            await conn.commit()
            return value

    async def next_counter(self, key: str) -> int:
        conn = self._require_conn()
        async with self._lock:
            await conn.execute(
                """
                INSERT INTO ticket_counters (counter_key, value) VALUES (?, 1)
                ON CONFLICT (counter_key) DO UPDATE SET value = value + 1
                """,
                (key,),
            )
            cur = await conn.execute(
                "SELECT value FROM ticket_counters WHERE counter_key = ?", (key,)
            )
            (value,) = await cur.fetchone()
            await conn.commit()
            return value

    async def all_tickets(self) -> list[TicketData]:
        conn = self._require_conn()
        async with self._lock:
            cur = await conn.execute(
                "SELECT channel_id, type, opener_id, created_at, closed, added_users, answers "
                "FROM tickets"
            )
            rows = await cur.fetchall()
            return [TicketData._from_row(row) for row in rows]


store = TicketStore()
