"""Discord-Anbindung: Befehle, Listener und Hintergrund-Loops. Läuft nur auf GUILD_ID."""
from __future__ import annotations

import asyncio
import io
import logging
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands, tasks

import config as cfg

from . import design
from .database import StatsDatabase, current_hour
from .render import ServerCardData, UserCardData, render_server_card, render_user_card
from .tracker import MessageBuffer, eligible_voice_members, should_count_message, text_channel_id

log = logging.getLogger(__name__)
L = design.LABELS


class WrongGuild(commands.CheckFailure):
    """Command auf einem anderen Server als GUILD_ID."""


def _validate_config() -> None:
    """Prüft die STATS-Werte aus config.py, damit Fehler beim Laden auffallen und nicht erst beim ersten Befehl."""
    problems = []
    longest = 0
    for name in ("STATS_USER_LOOKBACK", "STATS_SERVER_LOOKBACK"):
        value = getattr(cfg, name)
        if not (isinstance(value, tuple) and len(value) == 3 and all(isinstance(d, int) and d >= 1 for d in value)):
            problems.append(f"{name} muss genau 3 Tageswerte ≥ 1 enthalten, z. B. (1, 7, 14)")
        else:
            longest = max(longest, *value)
    for name in ("STATS_RANK_DAYS", "STATS_HIGHLIGHT_DAYS"):
        if getattr(cfg, name) < 1:
            problems.append(f"{name} muss ≥ 1 sein")
        longest = max(longest, getattr(cfg, name))
    if cfg.STATS_RETENTION_DAYS < longest:
        problems.append(f"STATS_RETENTION_DAYS muss ≥ {longest} sein (längster angezeigter Zeitraum)")
    if not 1 <= cfg.STATS_TOP_N <= 10:
        problems.append("STATS_TOP_N muss zwischen 1 und 10 liegen")
    if cfg.STATS_COOLDOWN_SECONDS < 0:
        problems.append("STATS_COOLDOWN_SECONDS muss ≥ 0 sein")
    if cfg.STATS_VOICE_MIN_MEMBERS < 1:
        problems.append("STATS_VOICE_MIN_MEMBERS muss ≥ 1 sein")
    if cfg.STATS_VOICE_TICK_SECONDS < 1 or cfg.STATS_MESSAGE_FLUSH_SECONDS < 1:
        problems.append("STATS_VOICE_TICK_SECONDS und STATS_MESSAGE_FLUSH_SECONDS müssen ≥ 1 sein")
    if cfg.STATS_VOICE_MAX_DELTA < cfg.STATS_VOICE_TICK_SECONDS:
        problems.append("STATS_VOICE_MAX_DELTA muss ≥ STATS_VOICE_TICK_SECONDS sein")
    for name in ("STATS_IGNORED_TEXT_CHANNEL_IDS", "STATS_IGNORED_VOICE_CHANNEL_IDS"):
        if not all(isinstance(i, int) for i in getattr(cfg, name)):
            problems.append(f"{name} darf nur Kanal-IDs als Zahlen enthalten (ohne Anführungszeichen)")
    if cfg.STATS_DECIMAL_SEP not in (".", ","):
        problems.append('STATS_DECIMAL_SEP muss "." oder "," sein')
    try:
        ZoneInfo(cfg.STATS_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        problems.append(
            f"STATS_TIMEZONE '{cfg.STATS_TIMEZONE}' ist unbekannt "
            "(auf Windows muss das Paket tzdata installiert sein, siehe requirements.txt)"
        )
    if problems:
        raise ValueError("Ungültige Werte in config.py: " + "; ".join(problems))


class ServerKeyword(commands.Converter[str]):
    """Akzeptiert "all" ohne Rücksicht auf Groß-/Kleinschreibung (all, ALL, All)."""

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        if argument.strip().lower() == "all":
            return "all"
        raise commands.BadArgument(f'"{argument}" ist nicht "all"')


async def _read_asset(asset: discord.Asset | None) -> bytes | None:
    if asset is None:
        return None
    try:
        return await asset.replace(size=256, format="png").read()
    except (discord.HTTPException, discord.NotFound, ValueError):
        return None


class StatsCog(commands.Cog, name="Stats"):
    """Nachrichten- und Voice-Statistiken als Bildkarte."""

    def __init__(self, bot: commands.Bot, db: StatsDatabase) -> None:
        self.bot = bot
        self.db = db
        self.buffer = MessageBuffer()
        self._last_voice_tick: float | None = None
        self._flush_lock = asyncio.Lock()

    # ------------------------------------------------------------- lifecycle
    async def cog_load(self) -> None:
        await self.db.connect()
        # Fonts und Hintergrund vorab laden, damit der erste Befehl nicht wartet
        await asyncio.to_thread(_warm_up)
        self.flush_messages.start()
        self.voice_tick.start()
        self.purge_old.start()

    async def cog_unload(self) -> None:
        for loop in (self.flush_messages, self.voice_tick, self.purge_old):
            loop.cancel()
        await self._flush()
        await self.db.close()

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        if ctx.guild.id != cfg.GUILD_ID:
            raise WrongGuild()
        return True

    # ------------------------------------------------------------- tracking
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.guild.id != cfg.GUILD_ID:
            return
        if should_count_message(message):
            self.buffer.add(message.guild.id, message.author.id, text_channel_id(message.channel), current_hour())

    async def _flush(self) -> None:
        async with self._flush_lock:
            rows = self.buffer.drain()
            if not rows:
                return
            try:
                await self.db.add_messages(rows)
            except Exception:
                self.buffer.restore(rows)
                log.exception("Nachrichten konnten nicht gespeichert werden – neuer Versuch beim nächsten Flush")

    @tasks.loop(seconds=cfg.STATS_MESSAGE_FLUSH_SECONDS)
    async def flush_messages(self) -> None:
        await self._flush()

    @tasks.loop(seconds=cfg.STATS_VOICE_TICK_SECONDS)
    async def voice_tick(self) -> None:
        now = time.monotonic()
        last, self._last_voice_tick = self._last_voice_tick, now
        if last is None:
            return  # erster Tick nach dem Start: nur Zeitstempel setzen
        delta = int(min(now - last, cfg.STATS_VOICE_MAX_DELTA))
        if delta <= 0:
            return
        guild = self.bot.get_guild(cfg.GUILD_ID)
        if guild is None:
            return
        hour = current_hour()
        rows = []
        for channel in (*guild.voice_channels, *guild.stage_channels):
            for member in eligible_voice_members(channel):
                rows.append((guild.id, member.id, channel.id, hour, delta))
        if rows:
            # Fehler hier abfangen: eine Exception würde die Loop sonst dauerhaft beenden
            try:
                await self.db.add_voice(rows)
            except Exception:
                log.exception("Voice-Zeit konnte nicht gespeichert werden – dieser Tick geht verloren")

    @tasks.loop(hours=24)
    async def purge_old(self) -> None:
        try:
            await self.db.purge(cfg.STATS_RETENTION_DAYS)
        except Exception:
            log.exception("Alte Stats konnten nicht gelöscht werden – neuer Versuch in 24 h")

    @flush_messages.before_loop
    @voice_tick.before_loop
    @purge_old.before_loop
    async def _before_loops(self) -> None:
        await self.bot.wait_until_ready()

    @voice_tick.error
    @flush_messages.error
    @purge_old.error
    async def _loop_error(self, error: BaseException) -> None:  # pragma: no cover - Logging
        log.exception("Fehler in Stats-Loop", exc_info=error)

    # ------------------------------------------------------------- commands
    @commands.command(name=cfg.COMMAND_STATS)
    @commands.cooldown(1, cfg.STATS_COOLDOWN_SECONDS, commands.BucketType.user)
    async def stats(self, ctx: commands.Context, *, target: ServerKeyword | discord.Member = None) -> None:  # type: ignore[assignment]
        """Zeigt die Stats-Karte: .stats | .stats @Mitglied | .stats all"""
        # Bewusst ohne "| None" im Typ: sonst liefert discord.py bei unbekanntem User still None
        # (= eigene Karte) statt BadUnionArgument (= Fehlermeldung).
        async with ctx.typing():
            await self._flush()  # frische Nachrichten mitzählen
            if target == "all":
                buf = await self._server_card(ctx.guild)
            else:
                buf = await self._user_card(ctx.guild, target or ctx.author)
        await ctx.reply(file=discord.File(buf, "stats.png"), mention_author=False)

    async def _user_card(self, guild: discord.Guild, member: discord.Member) -> io.BytesIO:
        now = current_hour()
        windows = cfg.STATS_USER_LOOKBACK
        msgs, voice, m_rank, v_rank, avatar = await asyncio.gather(
            self.db.user_totals(guild.id, member.id, "messages", windows, now),
            self.db.user_totals(guild.id, member.id, "voice", windows, now),
            self.db.user_rank(guild.id, member.id, "messages", cfg.STATS_RANK_DAYS, now),
            self.db.user_rank(guild.id, member.id, "voice", cfg.STATS_RANK_DAYS, now),
            _read_asset(member.display_avatar),
        )
        data = UserCardData(
            display_name=member.display_name, username=member.name, server_name=guild.name,
            avatar=avatar, created_at=member.created_at, joined_at=member.joined_at,
            message_rank=m_rank, voice_rank=v_rank, message_values=msgs, voice_seconds=voice,
            windows=windows, lookback_days=cfg.STATS_RANK_DAYS,
        )
        return await asyncio.to_thread(render_user_card, data)

    async def _server_card(self, guild: discord.Guild) -> io.BytesIO:
        now = current_hour()
        windows = cfg.STATS_SERVER_LOOKBACK
        hd = cfg.STATS_HIGHLIGHT_DAYS
        msgs, voice, hl_m, hl_v, top_m, top_v, icon = await asyncio.gather(
            self.db.server_totals(guild.id, "messages", windows, now),
            self.db.server_totals(guild.id, "voice", windows, now),
            self.db.server_totals(guild.id, "messages", (hd,), now),
            self.db.server_totals(guild.id, "voice", (hd,), now),
            self.db.top_members(guild.id, "messages", hd, cfg.STATS_TOP_N, now),
            self.db.top_members(guild.id, "voice", hd, cfg.STATS_TOP_N, now),
            _read_asset(guild.icon),
        )
        data = ServerCardData(
            server_name=guild.name, icon=icon, member_count=guild.member_count or len(guild.members),
            created_at=guild.created_at, highlight_days=hd,
            highlight_messages=hl_m[0], highlight_voice_seconds=hl_v[0],
            message_values=msgs, voice_seconds=voice,
            top_messages=[(await self._name(guild, uid), v) for uid, v in top_m],
            top_voice=[(await self._name(guild, uid), v) for uid, v in top_v],
            windows=windows,
        )
        return await asyncio.to_thread(render_server_card, data)

    async def _name(self, guild: discord.Guild, user_id: int) -> str:
        """Username; auch für User, die den Server verlassen haben."""
        member = guild.get_member(user_id)
        if member is not None:
            return member.name
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                return L["unknown_user"]
        return user.name

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        # on_command_error in bot.py überspringt Cogs mit eigenem Error-Handler.
        delete_after = None
        if isinstance(error, commands.CommandOnCooldown):
            text, delete_after = L["err_cooldown"].format(sec=error.retry_after), 5
        elif isinstance(error, (commands.BadUnionArgument, commands.MemberNotFound)):
            text = L["err_member"]
        elif isinstance(error, commands.NoPrivateMessage):
            text = L["err_dm"]
        elif isinstance(error, WrongGuild):
            text = L["err_guild"]
        elif isinstance(error, commands.CheckFailure):
            return
        else:
            log.error("Fehler in .%s", ctx.command.qualified_name if ctx.command else "?", exc_info=error)
            text = L["err_generic"]
        try:
            await ctx.reply(text, mention_author=False, delete_after=delete_after)
        except discord.HTTPException:
            pass


def _warm_up() -> None:
    from .render import _source_background
    from .text import chain

    _source_background()
    for role in ("serif", "sans", "sans_medium", "sans_semibold", "sans_bold"):
        chain(role)


async def setup(bot: commands.Bot) -> None:
    _validate_config()
    await bot.add_cog(StatsCog(bot, StatsDatabase(cfg.STATS_DB_PATH)))
