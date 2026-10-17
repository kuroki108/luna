from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

import config as cfg
from .formatting import reply
from .leaderboard_card import LeaderboardData, LeaderboardEntry, render_leaderboard
from .levelup_card import LevelupCardData, render_levelup_card
from .leveling_math import level_from_total_xp, xp_for_next_level
from .rankcard import RankCardData, render_rank_card

if TYPE_CHECKING:
    from .database import LevelingDatabase

log = logging.getLogger(cfg.LEVEL_LOGGER_NAME)

EMBED_COLOR = discord.Color(cfg.LEVEL_EMBED_COLOR)
LEVEL_ROLES: list[tuple[int, int]] = sorted(cfg.LEVEL_ROLES.items())  # [(level, role_id), ...] aufsteigend

# Kanäle, für die schon gewarnt wurde, dass Levelup-Karten dort nicht gesendet werden können
_warned_levelup_channels: set[int] = set()


def _card_cooldown():
    """Cooldown pro Nutzer für `.rank` und `.leaderboard` (CARD_COOLDOWN_SECONDS in config.py, 0 = aus)."""
    if cfg.CARD_COOLDOWN_SECONDS > 0:
        return commands.cooldown(1, cfg.CARD_COOLDOWN_SECONDS, commands.BucketType.user)
    return lambda func: func


async def fetch_avatar(user: discord.abc.User | None, size: int) -> bytes | None:
    """Lädt den Avatar als PNG. Bei Fehlern (oder ohne Nutzer) -> None (weißer Platzhalter)."""
    if user is None:
        return None
    try:
        return await user.display_avatar.replace(size=size, format="png").read()
    except (discord.HTTPException, ValueError):
        return None


# ======================================================================
# Befehle & Levelup-Karte (Teil des Leveling-Cogs)
# ======================================================================

class DisplayMixin:
    bot: commands.Bot
    db: LevelingDatabase

    # ------------------------------------------------------------------
    # Bilder bauen
    # ------------------------------------------------------------------

    async def _rank_file(self, member: discord.Member) -> discord.File:
        """Rangkarte eines Mitglieds als discord.File."""
        total = await self.db.get_total_xp(member.id)
        rank = await self.db.get_rank(member.id)
        level, xp_in_level = level_from_total_xp(total)
        data = RankCardData(
            username=member.display_name,
            level=level,
            rank=rank,
            xp_current=xp_in_level,
            xp_needed=xp_for_next_level(level),
            xp_total=total,
            avatar_bytes=await fetch_avatar(member, 512),
        )
        # Pillow blockiert -> in einen Thread auslagern, damit der Bot reaktionsfähig bleibt
        buffer = await asyncio.to_thread(render_rank_card, data)
        return discord.File(buffer, filename="rank.png")

    async def _leaderboard_file(self, guild: discord.Guild) -> discord.File:
        """Leaderboard (Top LEADERBOARD_SIZE) als discord.File."""
        rows = await self.db.get_leaderboard(cfg.LEADERBOARD_SIZE)

        # Ausgetretene Mitglieder: Name/Avatar aus dem User-Cache, sonst Platzhalter
        users = [guild.get_member(user_id) or self.bot.get_user(user_id) for user_id, _ in rows]
        avatars = await asyncio.gather(*(
            fetch_avatar(user, 256 if i < 3 else 128) for i, user in enumerate(users)
        ))

        entries = []
        for place, ((_, total), user, avatar) in enumerate(zip(rows, users, avatars), start=1):
            level, xp_in_level = level_from_total_xp(total)
            entries.append(LeaderboardEntry(
                place=place,
                name=user.display_name if user else "Unbekannt",
                level=level,
                xp_current=xp_in_level,
                xp_needed=xp_for_next_level(level),
                xp_total=total,
                avatar_bytes=avatar,
            ))

        data = LeaderboardData(server_name=guild.name, entries=entries)
        buffer = await asyncio.to_thread(render_leaderboard, data)
        return discord.File(buffer, filename="leaderboard.png")

    async def _levelup_file(self, member: discord.Member, role: discord.Role) -> discord.File:
        """Levelup-Bild für eine neu erreichte Level-Rolle als discord.File."""
        data = LevelupCardData(
            username=member.display_name,
            role_name=role.name,
            avatar_bytes=await fetch_avatar(member, 512),
        )
        buffer = await asyncio.to_thread(render_levelup_card, data)
        return discord.File(buffer, filename="levelup.png")

    # ------------------------------------------------------------------
    # Levelup: neue Level-Rolle -> Levelup-Bild + Ping (nur die Erwähnung, kein Text),
    # sonst Rangkarte (ohne Text, ohne Ping)
    # ------------------------------------------------------------------

    async def _announce_levelup(
        self,
        member: discord.Member,
        old_level: int,
        level: int,
        fallback_channel: discord.abc.Messageable | None,
    ) -> None:
        guild = member.guild

        channel = fallback_channel
        if cfg.LEVELUP_CHANNEL_ID:
            configured = guild.get_channel(cfg.LEVELUP_CHANNEL_ID)
            if isinstance(configured, discord.abc.Messageable):
                channel = configured
        if channel is None:
            return

        if isinstance(channel, (discord.abc.GuildChannel, discord.Thread)):
            perms = channel.permissions_for(guild.me)
            can_send = perms.send_messages_in_threads if isinstance(channel, discord.Thread) else perms.send_messages
            if not (can_send and perms.attach_files):
                if channel.id not in _warned_levelup_channels:
                    _warned_levelup_channels.add(channel.id)
                    log.warning(
                        "Levelup-Karten in #%s (Guild %s) nicht möglich – Bot braucht "
                        "'Nachrichten senden' und 'Dateien anhängen'", channel, guild.id,
                    )
                return

        # Höchste Level-Rolle, die mit diesem Levelup neu erreicht wurde (None = keine)
        new_roles = [guild.get_role(role_id) for lv, role_id in LEVEL_ROLES if old_level < lv <= level]
        role = next((r for r in reversed(new_roles) if r is not None), None)

        try:
            file = await (self._levelup_file(member, role) if role else self._rank_file(member))
        except Exception:
            log.exception("Levelup-Karte für %s (Level %s) konnte nicht erstellt werden", member.id, level)
            return
        try:
            await channel.send(file=file, allowed_mentions=discord.AllowedMentions.none())
            if role:
                await channel.send(member.mention, allowed_mentions=discord.AllowedMentions(users=[member]))
        except discord.HTTPException as exc:
            log.warning("Levelup-Karte in Guild %s nicht gesendet: %s", guild.id, exc)

    # ------------------------------------------------------------------
    # .rank
    # ------------------------------------------------------------------

    @commands.command(name=cfg.COMMAND_RANK, usage="[mitglied]")
    @_card_cooldown()
    async def rank(self, ctx: commands.Context, mitglied: discord.Member | None = None) -> None:
        """Zeigt die Rangkarte eines Mitglieds (ohne Angabe: deine eigene)."""
        target = mitglied or ctx.author
        assert isinstance(target, discord.Member)
        if target.bot:
            await reply(ctx, "Bots sammeln keine XP.")
            return
        async with ctx.typing():
            file = await self._rank_file(target)
        await reply(ctx, file=file)

    # ------------------------------------------------------------------
    # .leaderboard
    # ------------------------------------------------------------------

    @commands.command(name=cfg.COMMAND_LEADERBOARD)
    @_card_cooldown()
    async def leaderboard(self, ctx: commands.Context) -> None:
        """Zeigt die XP-Bestenliste des Servers als Bild."""
        assert ctx.guild is not None
        async with ctx.typing():
            file = await self._leaderboard_file(ctx.guild)
        await reply(ctx, file=file)
