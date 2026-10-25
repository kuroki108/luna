import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

import aiosqlite
import discord
from discord.ext import commands

import config as cfg
from .database import InviteDatabase, InviterStats

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Konfiguration (einstellbare Werte stehen in config.py)
# --------------------------------------------------------------------------- #

# Discord aktualisiert Nutzungszahlen gelegentlich minimal verzögert. Wird beim
# ersten Abruf keine Veränderung gefunden, wird nach dieser Pause erneut geprüft.
RETRY_DELAY_SECONDS = 1.5
MAX_FETCH_ATTEMPTS = 2

# Wie lange ein gelöschter Invite noch als "evtl. gerade aufgebraucht" gilt.
DELETED_INVITE_TTL = timedelta(seconds=30)

MAX_LISTED_LINKS = 10
EMBED_COLOR = cfg.EMBED_COLOR
NO_PINGS = discord.AllowedMentions.none()


class WrongGuild(commands.CheckFailure):
    """Command auf einem anderen Server als GUILD_ID."""


def _validate_config() -> None:
    problems = []
    if not 1 <= cfg.INVITE_LEADERBOARD_SIZE <= 25:
        problems.append("INVITE_LEADERBOARD_SIZE muss zwischen 1 und 25 liegen")
    if not isinstance(cfg.INVITE_LOG_CHANNEL_ID, int):
        problems.append("INVITE_LOG_CHANNEL_ID muss eine Kanal-ID als Zahl sein (0 = aus)")
    if problems:
        raise ValueError("Ungültige Werte in config.py: " + "; ".join(problems))


async def _reply(ctx: commands.Context, content: str | None = None, **kwargs) -> discord.Message:
    """Antwortet ohne jemanden zu pingen (auch nicht den Autor)."""
    kwargs.setdefault("allowed_mentions", NO_PINGS)
    return await ctx.reply(content, mention_author=False, **kwargs)


# --------------------------------------------------------------------------- #
# Datenmodelle
# --------------------------------------------------------------------------- #


class JoinType(StrEnum):
    INVITE = "invite"    # eindeutig einem Invite zugeordnet
    VANITY = "vanity"    # über die Vanity-URL des Servers
    UNKNOWN = "unknown"  # nicht eindeutig ermittelbar
    BOT = "bot"          # Bot über OAuth2 hinzugefügt


@dataclass(slots=True, frozen=True)
class CachedInvite:
    """Schlanke, unveränderliche Kopie der relevanten Invite-Daten."""

    code: str
    inviter_id: int | None
    channel_id: int | None
    uses: int
    max_uses: int  # 0 = unbegrenzt
    created_at: datetime | None
    expires_at: datetime | None
    is_vanity: bool = False

    @classmethod
    def from_invite(cls, invite: discord.Invite, *, is_vanity: bool = False) -> Self:
        expires_at = invite.expires_at
        if expires_at is None and invite.max_age and invite.created_at:
            expires_at = invite.created_at + timedelta(seconds=invite.max_age)

        return cls(
            code=invite.code,
            inviter_id=invite.inviter.id if invite.inviter else None,
            channel_id=invite.channel.id if invite.channel else None,
            uses=invite.uses or 0,
            max_uses=invite.max_uses or 0,
            created_at=invite.created_at,
            expires_at=expires_at,
            is_vanity=is_vanity,
        )

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and self.expires_at <= now

    def would_be_used_up_by_one_more_use(self) -> bool:
        return self.max_uses > 0 and self.uses + 1 >= self.max_uses


@dataclass(slots=True)
class JoinResult:
    join_type: JoinType
    invite: CachedInvite | None = None
    reason: str | None = None
    # Aktueller Invite-Stand, der anschließend in der DB gespeichert wird.
    snapshot: dict[str, CachedInvite] | None = None

    @classmethod
    def unknown(cls, reason: str, snapshot: dict[str, CachedInvite] | None = None) -> Self:
        return cls(JoinType.UNKNOWN, reason=reason, snapshot=snapshot)

    @property
    def inviter_id(self) -> int | None:
        if self.join_type is JoinType.INVITE and self.invite:
            return self.invite.inviter_id
        return None

    @property
    def invite_code(self) -> str | None:
        return self.invite.code if self.invite else None


# --------------------------------------------------------------------------- #
# Invite-Cache (reine Logik, ohne Discord-API-Aufrufe)
# --------------------------------------------------------------------------- #


class InviteCache:
    """Hält pro Server den zuletzt bekannten Invite-Stand und ermittelt Kandidaten."""

    def __init__(self) -> None:
        self._invites: dict[int, dict[str, CachedInvite]] = {}
        # Kürzlich gelöschte Invites, die durch eine letzte Nutzung aufgebraucht
        # worden sein könnten: guild_id -> code -> (invite, gelöscht_um)
        self._deleted: dict[int, dict[str, tuple[CachedInvite, datetime]]] = {}

    def has_guild(self, guild_id: int) -> bool:
        return guild_id in self._invites

    def get_invites(self, guild_id: int) -> list[CachedInvite]:
        return list(self._invites.get(guild_id, {}).values())

    def set_guild(self, guild_id: int, invites: dict[str, CachedInvite]) -> None:
        self._invites[guild_id] = dict(invites)
        self._deleted.pop(guild_id, None)

    def drop_guild(self, guild_id: int) -> None:
        self._invites.pop(guild_id, None)
        self._deleted.pop(guild_id, None)

    def add(self, guild_id: int, invite: CachedInvite) -> None:
        if guild_id in self._invites:
            self._invites[guild_id][invite.code] = invite

    def remove(self, guild_id: int, code: str, now: datetime) -> None:
        guild_invites = self._invites.get(guild_id)
        if guild_invites is None:
            return
        invite = guild_invites.pop(code, None)
        # Nur merken, wenn die Löschung durch Aufbrauchen entstanden sein kann
        # (nicht bei manuell gelöschten unbegrenzten oder abgelaufenen Invites).
        if invite and invite.would_be_used_up_by_one_more_use() and not invite.is_expired(now):
            self._deleted.setdefault(guild_id, {})[code] = (invite, now)

    def _prune_deleted(self, guild_id: int, now: datetime) -> None:
        deleted = self._deleted.get(guild_id)
        if not deleted:
            return
        for code, (_, deleted_at) in list(deleted.items()):
            if now - deleted_at > DELETED_INVITE_TTL:
                del deleted[code]

    def find_candidates(
        self, guild_id: int, current: dict[str, CachedInvite], now: datetime
    ) -> list[CachedInvite]:
        """Liefert alle Invites, die für den aktuellen Beitritt in Frage kommen."""
        cached = self._invites.get(guild_id, {})
        self._prune_deleted(guild_id, now)
        candidates: dict[str, CachedInvite] = {}

        # 1. Invites mit gestiegener Nutzungszahl
        for code, invite in current.items():
            previous = cached.get(code)
            if previous is None and invite.is_vanity:
                continue  # Vanity-URL neu im Cache -> nur Ausgangswert, kein Treffer
            previous_uses = previous.uses if previous else 0
            if invite.uses > previous_uses:
                candidates[code] = invite

        # 2. Verschwundene Invites, die durch genau diese Nutzung aufgebraucht wurden
        vanished = [inv for code, inv in cached.items() if code not in current]
        vanished += [inv for inv, _ in self._deleted.get(guild_id, {}).values()]
        for invite in vanished:
            if (
                invite.code not in current
                and invite.would_be_used_up_by_one_more_use()
                and not invite.is_expired(now)
            ):
                candidates.setdefault(invite.code, invite)

        return list(candidates.values())

    def apply_snapshot(
        self,
        guild_id: int,
        current: dict[str, CachedInvite],
        *,
        consumed: CachedInvite | None = None,
    ) -> None:
        """Übernimmt den aktuellen Stand in den Cache.

        Bei eindeutigem Treffer wird nur *eine* Nutzung des verwendeten Invites
        verbucht. Ist dessen Zähler um mehr als 1 gestiegen (mehrere Beitritte
        gleichzeitig über denselben Link), bleibt der Rest für die noch
        ausstehenden ``on_member_join``-Events erhalten.
        """
        previous = self._invites.get(guild_id, {})
        snapshot = dict(current)

        if consumed is None:
            # Mehrdeutig oder ohne Treffer: alles als verrechnet betrachten.
            self._deleted.pop(guild_id, None)
        else:
            if consumed.code in snapshot:
                before = previous.get(consumed.code)
                counted_uses = (before.uses if before else 0) + 1
                live = snapshot[consumed.code]
                snapshot[consumed.code] = replace(live, uses=min(counted_uses, live.uses))
            self._deleted.get(guild_id, {}).pop(consumed.code, None)

        self._invites[guild_id] = snapshot


# --------------------------------------------------------------------------- #
# Cog
# --------------------------------------------------------------------------- #


def _format_invite_source(join_type: str, inviter_id: int | None, invite_code: str | None) -> str:
    match join_type:
        case JoinType.INVITE:
            inviter = f"<@{inviter_id}>" if inviter_id else "*unbekannter Ersteller*"
            return f"{inviter} über den Link `{invite_code}`"
        case JoinType.VANITY:
            return f"über die Vanity-URL `discord.gg/{invite_code}`"
        case JoinType.BOT:
            return "Bot – per OAuth2 hinzugefügt"
        case _:
            return "❔ Unbekannt – die Einladung konnte nicht eindeutig ermittelt werden"


def _join_log_embed(
    member: discord.Member, result: JoinResult, stats: InviterStats | None
) -> discord.Embed:
    source = _format_invite_source(result.join_type, result.inviter_id, result.invite_code)
    embed = discord.Embed(
        title="Neues Mitglied",
        description=f"{member.mention} ist beigetreten.\n**Eingeladen von:** {source}",
        color=EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if stats is not None:
        embed.add_field(
            name="Invites des Inviters",
            value=f"**{stats.active}** aktiv ({stats.left} verlassen, {stats.total} gesamt)",
        )
    embed.set_footer(text=f"ID: {member.id}")
    return embed


def _is_tracked(guild: discord.abc.Snowflake | None) -> bool:
    return guild is not None and guild.id == cfg.GUILD_ID


class InviteTracker(commands.Cog):
    """Verfolgt, wer wen auf den Server eingeladen hat."""

    def __init__(self, bot: commands.Bot, db: InviteDatabase) -> None:
        self.bot = bot
        self.db = db
        self.cache = InviteCache()
        # Ein Lock pro Server serialisiert Sync und Beitrittsauswertung.
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Server, auf denen die Berechtigung "Server verwalten" fehlt.
        self._untracked: set[int] = set()
        self._startup_task: asyncio.Task[None] | None = None
        self._warned_log_channel = False

    # ---- Lebenszyklus ----------------------------------------------------- #

    async def cog_load(self) -> None:
        await self.db.connect()
        # Wird der Cog erst nach dem Start geladen, feuert on_ready nicht erneut.
        if self.bot.is_ready():
            self._startup_task = asyncio.create_task(self._sync_tracked_guild())

    async def cog_unload(self) -> None:
        if self._startup_task:
            self._startup_task.cancel()
        await self.db.close()

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        if ctx.guild.id != cfg.GUILD_ID:
            raise WrongGuild()
        return True

    # ---- Invite-Abruf & Synchronisierung ---------------------------------- #

    @staticmethod
    def _can_track(guild: discord.Guild) -> bool:
        return guild.me is not None and guild.me.guild_permissions.manage_guild

    async def _fetch_invites(self, guild: discord.Guild) -> dict[str, CachedInvite] | None:
        """Ruft alle aktiven Invites ab (inkl. Vanity-URL).

        Gibt ``None`` zurück, wenn die nötige Berechtigung fehlt.
        Andere API-Fehler (``discord.HTTPException``) werden weitergereicht.
        """
        if not self._can_track(guild):
            return None
        try:
            invites = await guild.invites()
        except discord.Forbidden:
            return None

        snapshot = {inv.code: CachedInvite.from_invite(inv) for inv in invites}

        if "VANITY_URL" in guild.features:
            try:
                vanity = await guild.vanity_invite()
            except discord.HTTPException as exc:
                log.debug("Vanity-URL von %s nicht abrufbar: %s", guild.id, exc)
            else:
                if vanity is not None:
                    snapshot[vanity.code] = CachedInvite.from_invite(vanity, is_vanity=True)

        return snapshot

    def _mark_untracked(self, guild: discord.Guild) -> None:
        self.cache.drop_guild(guild.id)
        if guild.id not in self._untracked:
            self._untracked.add(guild.id)
            log.warning(
                "Invite-Tracking auf '%s' (%s) nicht möglich: "
                "Berechtigung 'Server verwalten' fehlt.",
                guild.name, guild.id,
            )

    async def _refresh_unlocked(self, guild: discord.Guild) -> dict[str, CachedInvite] | None:
        """Lädt den Invite-Stand neu. Aufrufer muss den Server-Lock halten."""
        try:
            snapshot = await self._fetch_invites(guild)
        except discord.HTTPException as exc:
            log.warning("Invites von %s konnten nicht geladen werden: %s", guild.id, exc)
            return None
        if snapshot is None:
            self._mark_untracked(guild)
            return None
        self.cache.set_guild(guild.id, snapshot)
        self._untracked.discard(guild.id)
        return snapshot

    async def _sync_guild(self, guild: discord.Guild) -> None:
        async with self._locks[guild.id]:
            snapshot = await self._refresh_unlocked(guild)
        if snapshot is not None:
            await self._persist_snapshot(guild.id, snapshot)

    async def _sync_tracked_guild(self) -> None:
        guild = self.bot.get_guild(cfg.GUILD_ID)
        if guild is None:
            log.warning("Bot ist nicht auf dem Server %s (GUILD_ID in config.py) – kein Invite-Tracking", cfg.GUILD_ID)
            return
        await self._sync_guild(guild)
        if self.cache.has_guild(guild.id):
            log.info("Invite-Cache initialisiert: %d Invites", len(self.cache.get_invites(guild.id)))

    async def _persist_snapshot(self, guild_id: int, snapshot: dict[str, CachedInvite]) -> None:
        try:
            await self.db.save_snapshot(guild_id, snapshot.values())
        except aiosqlite.Error:
            log.exception("Invite-Stand von %s konnte nicht gespeichert werden", guild_id)

    # ---- Beitrittsauswertung ---------------------------------------------- #

    async def _resolve_join(self, member: discord.Member) -> JoinResult:
        if member.bot:
            return JoinResult(JoinType.BOT)

        guild = member.guild
        async with self._locks[guild.id]:
            if not self.cache.has_guild(guild.id):
                # Ohne Ausgangsstand kein Vergleich möglich -> Basis für künftige Beitritte.
                snapshot = await self._refresh_unlocked(guild)
                return JoinResult.unknown("kein Invite-Cache vorhanden", snapshot)

            current: dict[str, CachedInvite] = {}
            for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
                try:
                    fetched = await self._fetch_invites(guild)
                except discord.HTTPException as exc:
                    return JoinResult.unknown(f"API-Fehler ({exc.status})")
                if fetched is None:
                    self._mark_untracked(guild)
                    return JoinResult.unknown("fehlende Berechtigung")
                current = fetched

                candidates = self.cache.find_candidates(guild.id, current, discord.utils.utcnow())

                if len(candidates) == 1:
                    used = candidates[0]
                    self.cache.apply_snapshot(guild.id, current, consumed=used)
                    join_type = JoinType.VANITY if used.is_vanity else JoinType.INVITE
                    return JoinResult(join_type, used, snapshot=current)

                if len(candidates) > 1:
                    # Mehrere Beitritte über verschiedene Links -> lieber unbekannt als falsch.
                    self.cache.apply_snapshot(guild.id, current)
                    codes = ", ".join(c.code for c in candidates)
                    return JoinResult.unknown(f"mehrdeutig ({codes})", current)

                if attempt < MAX_FETCH_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

            self.cache.apply_snapshot(guild.id, current)
            return JoinResult.unknown("keine Veränderung erkennbar", current)

    async def _send_join_log(self, member: discord.Member, result: JoinResult) -> None:
        if not cfg.INVITE_LOG_CHANNEL_ID:
            return
        channel = member.guild.get_channel(cfg.INVITE_LOG_CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            if not self._warned_log_channel:
                self._warned_log_channel = True
                log.warning("Invite-Log-Kanal %s (INVITE_LOG_CHANNEL_ID) nicht gefunden", cfg.INVITE_LOG_CHANNEL_ID)
            return

        stats = None
        if result.inviter_id and result.inviter_id != member.id:
            try:
                stats = await self.db.get_inviter_stats(member.guild.id, result.inviter_id)
            except aiosqlite.Error:
                log.exception("Invite-Statistik von %s konnte nicht geladen werden", result.inviter_id)
        try:
            await channel.send(embed=_join_log_embed(member, result, stats), allowed_mentions=NO_PINGS)
        except discord.HTTPException as exc:
            log.warning("Beitritts-Nachricht für %s nicht gesendet: %s", member.id, exc)

    # ---- Events ----------------------------------------------------------- #

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # Feuert auch nach Reconnects -> verpasste Änderungen werden nachgeholt.
        await self._sync_tracked_guild()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        if _is_tracked(guild):
            await self._sync_guild(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        self.cache.drop_guild(guild.id)
        self._untracked.discard(guild.id)
        self._locks.pop(guild.id, None)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        # Bot hat neue Rollen erhalten -> evtl. jetzt ausreichende Berechtigungen.
        if (
            self.bot.user
            and after.id == self.bot.user.id
            and after.guild.id in self._untracked
            and before.roles != after.roles
        ):
            await self._sync_guild(after.guild)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if after.guild.id in self._untracked and before.permissions != after.permissions:
            await self._sync_guild(after.guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if not _is_tracked(invite.guild):
            return
        cached = CachedInvite.from_invite(invite)
        self.cache.add(invite.guild.id, cached)
        try:
            await self.db.save_invite(invite.guild.id, cached)
        except aiosqlite.Error:
            log.exception("Invite %s konnte nicht gespeichert werden", invite.code)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if not _is_tracked(invite.guild):
            return
        self.cache.remove(invite.guild.id, invite.code, discord.utils.utcnow())
        try:
            await self.db.mark_invite_deleted(invite.guild.id, invite.code)
        except aiosqlite.Error:
            log.exception("Löschung von Invite %s konnte nicht gespeichert werden", invite.code)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not _is_tracked(member.guild):
            return
        result = await self._resolve_join(member)
        joined_at = member.joined_at or discord.utils.utcnow()

        try:
            await self.db.record_join(
                member.guild.id,
                member.id,
                join_type=result.join_type.value,
                inviter_id=result.inviter_id,
                invite_code=result.invite_code,
                joined_at=joined_at,
            )
        except aiosqlite.Error:
            log.exception("Beitritt von %s konnte nicht gespeichert werden", member.id)
        if result.snapshot is not None:
            await self._persist_snapshot(member.guild.id, result.snapshot)

        if result.join_type is JoinType.UNKNOWN:
            log.info("%s ist %s beigetreten – Invite unbekannt (%s)",
                     member, member.guild.id, result.reason)
        else:
            log.info("%s ist %s beigetreten – %s, Code=%s, Inviter=%s",
                     member, member.guild.id, result.join_type, result.invite_code,
                     result.inviter_id)

        await self._send_join_log(member, result)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not _is_tracked(member.guild):
            return
        try:
            await self.db.mark_left(member.guild.id, member.id)
        except aiosqlite.Error:
            log.exception("Austritt von %s konnte nicht gespeichert werden", member.id)

    # ---- Prefix-Commands -------------------------------------------------- #

    def _tracking_warning(self, guild: discord.Guild) -> str | None:
        if guild.id in self._untracked:
            return "⚠️ Tracking inaktiv: Dem Bot fehlt die Berechtigung „Server verwalten“."
        return None

    @commands.command(name=cfg.COMMAND_INVITES, usage="[nutzer]")
    async def invites_command(self, ctx: commands.Context, nutzer: discord.User | None = None) -> None:
        """Zeigt die Invite-Statistiken eines Nutzers (ohne Angabe: deine eigenen)."""
        guild = ctx.guild
        target = nutzer or ctx.author
        stats = await self.db.get_inviter_stats(guild.id, target.id)

        embed = discord.Embed(title=f"Invites von {target.display_name}", color=EMBED_COLOR)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="✅ Aktiv", value=str(stats.active))
        embed.add_field(name="🚪 Verlassen", value=str(stats.left))
        embed.add_field(name="📊 Gesamt", value=str(stats.total))

        links = sorted(
            (inv for inv in self.cache.get_invites(guild.id) if inv.inviter_id == target.id),
            key=lambda inv: inv.uses,
            reverse=True,
        )
        if links:
            lines = [
                f"`{inv.code}` – {inv.uses}{f'/{inv.max_uses}' if inv.max_uses else ''} Nutzungen"
                for inv in links[:MAX_LISTED_LINKS]
            ]
            if len(links) > MAX_LISTED_LINKS:
                lines.append(f"… und {len(links) - MAX_LISTED_LINKS} weitere")
            embed.add_field(name="🔗 Aktive Links", value="\n".join(lines), inline=False)

        if warning := self._tracking_warning(guild):
            embed.set_footer(text=warning)
        await _reply(ctx, embed=embed)

    @commands.command(name=cfg.COMMAND_INVITE_LEADERBOARD)
    async def invite_leaderboard(self, ctx: commands.Context) -> None:
        """Zeigt die Top-Inviter des Servers."""
        guild = ctx.guild
        top = await self.db.get_leaderboard(guild.id, cfg.INVITE_LEADERBOARD_SIZE)
        unknown = await self.db.count_unknown_joins(guild.id)

        embed = discord.Embed(title=f"🏆 Invite-Leaderboard – {guild.name}", color=EMBED_COLOR)
        if top:
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            embed.description = "\n".join(
                f"{medals.get(rank, f'`#{rank}`')} <@{s.inviter_id}> – **{s.active}** "
                f"Invite{'s' if s.active != 1 else ''} ({s.left} verlassen, {s.total} gesamt)"
                for rank, s in enumerate(top, start=1)
            )
        else:
            embed.description = "Bisher wurden keine Einladungen erfasst."

        footer = [f"{unknown} Beitritt(e) ohne eindeutige Einladung"] if unknown else []
        if warning := self._tracking_warning(guild):
            footer.append(warning)
        if footer:
            embed.set_footer(text=" • ".join(footer))
        await _reply(ctx, embed=embed)

    @commands.command(name=cfg.COMMAND_INVITED_BY, usage="[nutzer]")
    async def invitedby(self, ctx: commands.Context, nutzer: discord.User | None = None) -> None:
        """Zeigt, wer einen Nutzer eingeladen hat (ohne Angabe: dich selbst)."""
        target = nutzer or ctx.author
        row = await self.db.get_join(ctx.guild.id, target.id)

        embed = discord.Embed(title=f"Einladung von {target.display_name}", color=EMBED_COLOR)
        embed.set_thumbnail(url=target.display_avatar.url)

        if row is None:
            embed.description = (
                f"Für {target.mention} liegen keine Daten vor – "
                "vermutlich vor Aktivierung des Trackers beigetreten."
            )
        else:
            joined_at = datetime.fromisoformat(row["joined_at"])
            source = _format_invite_source(row["join_type"], row["inviter_id"], row["invite_code"])
            embed.description = f"{target.mention} wurde eingeladen von: {source}"
            embed.add_field(name="Beigetreten", value=discord.utils.format_dt(joined_at, "R"))
            if row["left_at"]:
                left_at = datetime.fromisoformat(row["left_at"])
                embed.add_field(name="Verlassen", value=discord.utils.format_dt(left_at, "R"))
            if row["join_count"] > 1:
                embed.add_field(name="Beitritte", value=str(row["join_count"]))

        await _reply(ctx, embed=embed)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.NoPrivateMessage):
            text = "Das geht nur auf einem Server."
        elif isinstance(error, WrongGuild):
            text = "Der Invite-Tracker ist auf diesem Server nicht aktiv."
        elif isinstance(error, commands.UserNotFound):
            text = "Diesen Nutzer habe ich nicht gefunden."
        elif isinstance(error, commands.CheckFailure):
            text = "Das darfst du hier nicht."
        else:
            log.error("Fehler in .%s", ctx.command.qualified_name if ctx.command else "?", exc_info=error)
            text = "❌ Beim Ausführen des Befehls ist ein Fehler aufgetreten."
        try:
            await _reply(ctx, text)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    _validate_config()
    await bot.add_cog(InviteTracker(bot, InviteDatabase(cfg.INVITE_DB_PATH)))
