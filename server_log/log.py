from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

import config as cfg

from .database import ServerLogDatabase

log = logging.getLogger(__name__)

EMBED_COLOR = cfg.EMBED_COLOR
LOG_CHANNEL_SETTINGS = ("MESSAGE_LOG_CHANNEL_ID", "MEMBER_LOG_CHANNEL_ID", "MOD_LOG_CHANNEL_ID")


def truncate(text: str, limit: int = 1024) -> str:
    if not text:
        return "*(leer / kein Inhalt)*"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _is_tracked(guild: discord.Guild | None) -> bool:
    return guild is not None and guild.id == cfg.GUILD_ID


def _validate_config() -> None:
    wrong = [name for name in LOG_CHANNEL_SETTINGS if not isinstance(getattr(cfg, name), int)]
    if wrong:
        raise ValueError(
            "Ungültige Werte in config.py: " + ", ".join(wrong) + " müssen Kanal-IDs als Zahl sein (0 = aus)"
        )


class LoggingCog(commands.Cog):
    """Server-Log: gelöschte/bearbeitete Nachrichten, Beitritte/Austritte, Kicks, Banns."""

    def __init__(self, bot: commands.Bot, db: ServerLogDatabase) -> None:
        self.bot = bot
        self.db = db
        self._warned_channels: set[int] = set()
        # Kanäle, deren Nachrichten per `.unlog` nicht geloggt werden.
        self._unlogged: set[int] = set()

    async def cog_load(self) -> None:
        await self.db.connect()
        self._unlogged = await self.db.get_unlogged_channels(cfg.GUILD_ID)
        for name in LOG_CHANNEL_SETTINGS:
            if not getattr(cfg, name):
                log.info("%s ist 0 – dieser Log ist aus.", name)

    async def cog_unload(self) -> None:
        await self.db.close()

    def _is_unlogged(self, channel: discord.abc.GuildChannel | discord.Thread) -> bool:
        """True, wenn der Kanal (bei Threads auch der Elternkanal) per `.unlog` ausgenommen ist."""
        if channel.id in self._unlogged:
            return True
        parent_id = getattr(channel, "parent_id", None)
        return parent_id is not None and parent_id in self._unlogged

    async def _send(self, channel_id: int, embed: discord.Embed) -> None:
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            if channel_id not in self._warned_channels:
                self._warned_channels.add(channel_id)
                log.warning("Log-Kanal %s nicht gefunden.", channel_id)
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("Log-Nachricht in Kanal %s nicht gesendet: %s", channel_id, exc)

    # -----------------------------------------------------------------
    # NACHRICHTEN: Edit / Delete
    # -----------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not _is_tracked(message.guild) or message.author.bot or self._is_unlogged(message.channel):
            return

        embed = discord.Embed(
            title="🗑️ Nachricht gelöscht",
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Autor", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=False)
        embed.add_field(name="Inhalt", value=truncate(message.content), inline=False)
        if message.attachments:
            embed.add_field(
                name="Anhänge",
                value=truncate("\n".join(a.url for a in message.attachments)),
                inline=False,
            )
        embed.set_footer(text=f"Message-ID: {message.id}")
        await self._send(cfg.MESSAGE_LOG_CHANNEL_ID, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not _is_tracked(before.guild) or before.author.bot or self._is_unlogged(before.channel):
            return
        if before.content == after.content:
            # Nur echte Text-Aenderungen loggen (kein Embed-Unfurl-Trigger etc.)
            return

        embed = discord.Embed(
            title="✏️ Nachricht bearbeitet",
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Autor", value=f"{before.author} ({before.author.id})", inline=False)
        embed.add_field(name="Channel", value=before.channel.mention, inline=False)
        embed.add_field(name="Vorher", value=truncate(before.content), inline=False)
        embed.add_field(name="Nachher", value=truncate(after.content), inline=False)
        embed.add_field(name="Sprung", value=f"[Zur Nachricht]({after.jump_url})", inline=False)
        embed.set_footer(text=f"Message-ID: {before.id}")
        await self._send(cfg.MESSAGE_LOG_CHANNEL_ID, embed)

    # -----------------------------------------------------------------
    # COMMAND: .unlog
    # -----------------------------------------------------------------
    @commands.command(name="unlog")
    @commands.has_guild_permissions(administrator=True)
    async def unlog_command(self, ctx: commands.Context) -> None:
        """Schaltet das Nachrichten-Log für den aktuellen Kanal aus bzw. wieder ein."""
        if not _is_tracked(ctx.guild):
            await ctx.send("Der Server-Log läuft nur auf dem Hauptserver.", delete_after=5)
            return

        channel = ctx.channel
        if channel.id in self._unlogged:
            await self.db.remove_unlogged_channel(channel.id)
            self._unlogged.discard(channel.id)
            await ctx.send(f"🔔 {channel.mention} wird wieder geloggt.")
        else:
            await self.db.add_unlogged_channel(ctx.guild.id, channel.id, ctx.author.id)
            self._unlogged.add(channel.id)
            await ctx.send(
                f"🔕 Gelöschte und bearbeitete Nachrichten in {channel.mention} werden nicht mehr geloggt. "
                "Mit `.unlog` wieder einschalten."
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.id in self._unlogged:
            await self.db.remove_unlogged_channel(channel.id)
            self._unlogged.discard(channel.id)

    # -----------------------------------------------------------------
    # MEMBER: Join / Leave / Kick
    # -----------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not _is_tracked(member.guild):
            return
        embed = discord.Embed(
            title="📥 Mitglied beigetreten",
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        account_age = datetime.now(timezone.utc) - member.created_at
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="Account erstellt", value=f"{member.created_at:%Y-%m-%d} ({account_age.days} Tage alt)", inline=False)
        embed.add_field(name="Mitgliederzahl", value=str(member.guild.member_count), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send(cfg.MEMBER_LOG_CHANNEL_ID, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not _is_tracked(member.guild):
            return
        # Kurze Verzoegerung, damit der Audit-Log-Eintrag (falls Kick) sicher existiert
        await asyncio.sleep(1.0)

        kicked_by = None
        reason = None

        if member.guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in member.guild.audit_logs(
                    limit=5, action=discord.AuditLogAction.kick
                ):
                    if entry.target and entry.target.id == member.id:
                        delta = datetime.now(timezone.utc) - entry.created_at
                        if delta.total_seconds() < 5:
                            kicked_by = entry.user
                            reason = entry.reason
                            break
            except discord.HTTPException:
                pass

        if kicked_by:
            embed = discord.Embed(
                title="👢 Mitglied gekickt",
                color=EMBED_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
            embed.add_field(name="Von", value=f"{kicked_by} ({kicked_by.id})", inline=False)
            embed.add_field(name="Grund", value=reason or "*(kein Grund angegeben)*", inline=False)
            await self._send(cfg.MOD_LOG_CHANNEL_ID, embed)
        else:
            embed = discord.Embed(
                title="📤 Mitglied verlassen",
                color=EMBED_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
            joined = member.joined_at
            if joined:
                embed.add_field(name="Server beigetreten am", value=f"{joined:%Y-%m-%d %H:%M UTC}", inline=False)
            await self._send(cfg.MEMBER_LOG_CHANNEL_ID, embed)

    # -----------------------------------------------------------------
    # MODERATION: Ban / Unban
    # -----------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if not _is_tracked(guild):
            return
        banned_by = None
        reason = None
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                    if entry.target and entry.target.id == user.id:
                        banned_by = entry.user
                        reason = entry.reason
                        break
            except discord.HTTPException:
                pass

        embed = discord.Embed(
            title="🔨 Mitglied gebannt",
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
        if banned_by:
            embed.add_field(name="Von", value=f"{banned_by} ({banned_by.id})", inline=False)
        embed.add_field(name="Grund", value=reason or "*(kein Grund angegeben)*", inline=False)
        await self._send(cfg.MOD_LOG_CHANNEL_ID, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if not _is_tracked(guild):
            return
        unbanned_by = None
        if guild.me.guild_permissions.view_audit_log:
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                    if entry.target and entry.target.id == user.id:
                        unbanned_by = entry.user
                        break
            except discord.HTTPException:
                pass

        embed = discord.Embed(
            title="🔓 Bann aufgehoben",
            color=EMBED_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
        if unbanned_by:
            embed.add_field(name="Von", value=f"{unbanned_by} ({unbanned_by.id})", inline=False)
        await self._send(cfg.MOD_LOG_CHANNEL_ID, embed)


async def setup(bot: commands.Bot) -> None:
    _validate_config()
    await bot.add_cog(LoggingCog(bot, ServerLogDatabase(cfg.SERVER_LOG_DB_PATH)))
