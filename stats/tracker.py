"""Erfassungslogik ohne Discord-I/O, damit sie sich leicht testen lässt."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from discord import MessageType

import config as cfg

from .database import Row

# Nur echte Nachrichten zählen – keine System-Meldungen (Join, Boost, Pin, ...),
# deren Autor der betroffene User ist und nicht ein Bot.
_COUNTED_TYPES = {MessageType.default, MessageType.reply}

IGNORED_TEXT_CHANNELS = frozenset(cfg.STATS_IGNORED_TEXT_CHANNEL_IDS)
IGNORED_VOICE_CHANNELS = frozenset(cfg.STATS_IGNORED_VOICE_CHANNEL_IDS)


class MessageBuffer:
    """Zählt Nachrichten im Speicher und gibt sie gebündelt an die DB weiter."""

    def __init__(self) -> None:
        self._counts: defaultdict[tuple[int, int, int, int], int] = defaultdict(int)

    def add(self, guild_id: int, user_id: int, channel_id: int, hour: int, n: int = 1) -> None:
        self._counts[(guild_id, user_id, channel_id, hour)] += n

    def drain(self) -> list[Row]:
        rows = [(*key, n) for key, n in self._counts.items()]
        self._counts.clear()
        return rows

    def restore(self, rows: list[Row]) -> None:
        """Zurücklegen, falls das Schreiben fehlgeschlagen ist."""
        for g, u, c, h, n in rows:
            self._counts[(g, u, c, h)] += n

    def __len__(self) -> int:
        return len(self._counts)


def text_channel_id(channel: Any) -> int:
    """Bei Threads zählt der Parent-Channel (für Ignorier-Liste und Speicherung)."""
    parent_id = getattr(channel, "parent_id", None)
    return parent_id or channel.id


def should_count_message(message: Any, ignored: frozenset[int] | set[int] | None = None) -> bool:
    ignored = IGNORED_TEXT_CHANNELS if ignored is None else ignored
    if message.guild is None or message.author.bot or message.webhook_id is not None:
        return False
    if message.type not in _COUNTED_TYPES:
        return False
    return text_channel_id(message.channel) not in ignored and message.channel.id not in ignored


def eligible_voice_members(
    channel: Any,
    ignored: frozenset[int] | set[int] | None = None,
    min_members: int | None = None,
) -> list[Any]:
    """Mitglieder eines Voice-Channels, denen gerade Zeit gutgeschrieben wird.

    Taube oder stummgeschaltete Mitglieder (selbst oder vom Server) sammeln nie Zeit
    und zählen auch nicht zur Mindestanzahl – sonst ließe sich mit einem tauben
    oder stummen Zweitaccount allein Zeit sammeln.
    """
    ignored = IGNORED_VOICE_CHANNELS if ignored is None else ignored
    min_members = cfg.STATS_VOICE_MIN_MEMBERS if min_members is None else min_members

    afk = getattr(channel.guild, "afk_channel", None)
    if channel.id in ignored or (afk is not None and afk.id == channel.id):
        return []

    eligible = []
    for m in channel.members:
        if m.bot:
            continue
        vs = m.voice
        if vs is None or vs.self_deaf or vs.deaf or vs.self_mute or vs.mute:
            continue
        eligible.append(m)
    return eligible if len(eligible) >= min_members else []
