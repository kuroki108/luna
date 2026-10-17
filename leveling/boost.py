"""XP-Boost: `.xprise <prozent> <dauer> [text|voice]` erhöht Text- und/oder Voice-XP für eine Zeit."""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

from discord.ext import commands

import config as cfg
from .formatting import reply

if TYPE_CHECKING:
    from .database import LevelingDatabase

log = logging.getLogger(cfg.LEVEL_LOGGER_NAME)

KINDS = ("text", "voice")
KIND_NAMES = {"text": "Text-XP", "voice": "Voice-XP"}
MAX_PERCENT = 1000
MAX_DURATION_SECONDS = 30 * 24 * 3600  # 30 Tage

_DURATION_RE = re.compile(r"(\d+)([dhm])")
_DURATION_UNITS = {"d": 86400, "h": 3600, "m": 60}


class Duration(commands.Converter[int]):
    """'3h', '30m', '1d', '1h30m' -> Sekunden."""

    async def convert(self, ctx: commands.Context, argument: str) -> int:
        text = argument.lower()
        parts = _DURATION_RE.findall(text)
        if not parts or "".join(n + u for n, u in parts) != text:
            raise commands.BadArgument(f"`{argument}` ist keine Dauer – z. B. `30m`, `3h`, `1d` oder `1h30m`")
        seconds = sum(int(n) * _DURATION_UNITS[u] for n, u in parts)
        if not 60 <= seconds <= MAX_DURATION_SECONDS:
            raise commands.BadArgument("Die Dauer muss zwischen 1 Minute und 30 Tagen liegen")
        return seconds


class BoostKind(commands.Converter[tuple[str, ...]]):
    """'text', 'voice'/'vc' oder 'alle' -> betroffene Arten."""

    async def convert(self, ctx: commands.Context, argument: str) -> tuple[str, ...]:
        value = argument.lower()
        if value == "text":
            return ("text",)
        if value in ("voice", "vc"):
            return ("voice",)
        if value in ("alle", "all", "beide"):
            return KINDS
        raise commands.BadArgument(f"`{argument}` – erlaubt sind `text`, `voice` oder `alle`")


def _until(ends_at: int) -> str:
    return f"bis <t:{ends_at}:f> (<t:{ends_at}:R>)"


# ======================================================================
# Befehle & Boost-Berechnung (Teil des Leveling-Cogs)
# ======================================================================

class BoostMixin:
    db: LevelingDatabase
    _boosts: dict[str, tuple[int, int]]  # {kind: (prozent, ends_at)}

    async def _load_boosts(self) -> None:
        self._boosts = await self.db.get_boosts()

    def _active_boost(self, kind: str) -> int:
        """Aktueller Boost in Prozent (0 = keiner)."""
        boost = self._boosts.get(kind)
        if boost is None or boost[1] <= time.time():
            return 0
        return boost[0]

    def _boosted(self, kind: str, amount: int) -> int:
        percent = self._active_boost(kind)
        return round(amount * (100 + percent) / 100) if percent else amount

    def _boost_lines(self) -> list[str]:
        return [
            f"{KIND_NAMES[kind]}: **+{self._active_boost(kind)} %** {_until(self._boosts[kind][1])}"
            for kind in KINDS if self._active_boost(kind)
        ]

    # ------------------------------------------------------------------
    # .xprise
    # ------------------------------------------------------------------

    @commands.group(
        name=cfg.COMMAND_XP_BOOST, invoke_without_command=True, usage="<prozent> <dauer> [text|voice]"
    )
    @commands.has_guild_permissions(manage_guild=True)
    async def xp_boost(
        self,
        ctx: commands.Context,
        prozent: commands.Range[int, 1, MAX_PERCENT],
        dauer: Duration,
        art: BoostKind = KINDS,
    ) -> None:
        """Erhöht Text- und/oder Voice-XP für eine Zeit, z. B. `20 3h` oder `50 1h30m voice` (Admin)."""
        ends_at = int(time.time()) + dauer
        for kind in art:
            await self.db.set_boost(kind, prozent, ends_at)
            self._boosts[kind] = (prozent, ends_at)
        names = " und ".join(KIND_NAMES[k] for k in art)
        log.info("XP-Boost +%d %% für %s bis %s (von %s)", prozent, names, ends_at, ctx.author)
        await reply(ctx, f"{names} **+{prozent} %** {_until(ends_at)}.")

    # invoke_without_command=True: die Prüfung der Gruppe läuft nicht für Unterbefehle -> hier nochmal
    @xp_boost.command(name="status")
    @commands.has_guild_permissions(manage_guild=True)
    async def xp_boost_status(self, ctx: commands.Context) -> None:
        """Zeigt die aktiven XP-Boosts."""
        await reply(ctx, "\n".join(self._boost_lines()) or "Kein XP-Boost aktiv.")

    @xp_boost.command(name="stop", usage="[text|voice]")
    @commands.has_guild_permissions(manage_guild=True)
    async def xp_boost_stop(self, ctx: commands.Context, art: BoostKind = KINDS) -> None:
        """Beendet XP-Boosts (ohne Angabe: alle)."""
        for kind in art:
            await self.db.clear_boost(kind)
            self._boosts.pop(kind, None)
        await reply(ctx, f"XP-Boost für {' und '.join(KIND_NAMES[k] for k in art)} beendet.")
