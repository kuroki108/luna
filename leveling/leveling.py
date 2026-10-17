from __future__ import annotations

import asyncio
import logging
import random
import time

import discord
from discord.ext import commands, tasks
from PIL import ImageFont

import config as cfg
from .boost import BoostMixin
from .database import LevelingDatabase
from .display import EMBED_COLOR, DisplayMixin
from .formatting import format_number, reply
from .leveling_math import level_from_total_xp

log = logging.getLogger(cfg.LEVEL_LOGGER_NAME)

XP_MESSAGE_TYPES = frozenset({discord.MessageType.default, discord.MessageType.reply})
NO_XP_CHANNELS = frozenset(cfg.NO_XP_CHANNELS)
LEVEL_ROLES: list[tuple[int, int]] = sorted(cfg.LEVEL_ROLES.items())  # [(level, role_id), ...] aufsteigend


class WrongGuild(commands.CheckFailure):
    """Command auf einem anderen Server als GUILD_ID."""


# ======================================================================
# Helfer
# ======================================================================

def _validate_config() -> None:
    """Prüft die Werte aus config.py, damit Fehler beim Laden auffallen und nicht erst bei der ersten Nachricht."""
    problems = []
    if not 1 <= cfg.XP_MIN <= cfg.XP_MAX:
        problems.append("XP_MIN muss ≥ 1 und ≤ XP_MAX sein")
    if cfg.COOLDOWN_SECONDS < 0:
        problems.append("COOLDOWN_SECONDS muss ≥ 0 sein")
    if cfg.VOICE_XP_PER_MIN < 0:
        problems.append("VOICE_XP_PER_MIN muss ≥ 0 sein")
    if cfg.VOICE_DAILY_CAP_MINUTES < 0:
        problems.append("VOICE_DAILY_CAP_MINUTES muss ≥ 0 sein")
    if cfg.VOICE_MIN_MEMBERS < 1:
        problems.append("VOICE_MIN_MEMBERS muss ≥ 1 sein")
    if not 1 <= cfg.LEADERBOARD_SIZE <= 25:
        problems.append("LEADERBOARD_SIZE muss zwischen 1 und 25 liegen")
    if not all(isinstance(i, int) for i in cfg.NO_XP_CHANNELS):
        problems.append("NO_XP_CHANNELS darf nur Kanal-/Kategorie-IDs als Zahlen enthalten (ohne Anführungszeichen)")
    if not all(
        isinstance(lv, int) and lv >= 0 and isinstance(role_id, int) for lv, role_id in cfg.LEVEL_ROLES.items()
    ):
        problems.append("LEVEL_ROLES muss so aussehen: {level: rollen_id} – Level ≥ 0, IDs als Zahlen")
    elif len(set(cfg.LEVEL_ROLES.values())) != len(cfg.LEVEL_ROLES):
        problems.append("LEVEL_ROLES: jede Rollen-ID darf nur einmal vorkommen")
    if cfg.CARD_COOLDOWN_SECONDS < 0:
        problems.append("CARD_COOLDOWN_SECONDS muss ≥ 0 sein")
    if cfg.CARD_FONT:
        try:
            ImageFont.truetype(cfg.CARD_FONT, 20)
        except OSError:
            problems.append(f"CARD_FONT '{cfg.CARD_FONT}' lässt sich nicht laden")
    if problems:
        raise ValueError("Ungültige Werte in config.py: " + "; ".join(problems))


def _relevant_channel_ids(channel: discord.abc.GuildChannel | discord.Thread) -> set[int]:
    """Kanal-ID plus Elternkanal (bei Threads) plus Kategorie – für die No-XP-Prüfung."""
    ids = {channel.id}
    if isinstance(channel, discord.Thread):
        ids.add(channel.parent_id)
        channel = channel.parent  # Kategorie hängt am Elternkanal
    category_id = getattr(channel, "category_id", None)
    if category_id:
        ids.add(category_id)
    return ids


async def _send_group_help(ctx: commands.Context) -> None:
    group = ctx.command
    assert isinstance(group, commands.Group)
    lines = [
        f"`{f'{ctx.clean_prefix}{cmd.qualified_name} {cmd.usage or cmd.signature}'.strip()}` – {cmd.short_doc}"
        for cmd in group.commands
    ]
    await reply(ctx, f"**{ctx.clean_prefix}{group.qualified_name}** – Unterbefehle:\n" + "\n".join(lines))


# ======================================================================
# Cog – Levelup-Karte, `.rank` und `.leaderboard` stehen in display.py
# (Bilder: rankcard.py, levelup_card.py, leaderboard_card.py),
# `.xprise` (XP-Boost) in boost.py
# ======================================================================

class Leveling(BoostMixin, DisplayMixin, commands.Cog):
    def __init__(self, bot: commands.Bot, db: LevelingDatabase) -> None:
        self.bot = bot
        self.db = db
        self._warned_missing_perms: set[int] = set()
        self._role_sync_task: asyncio.Task[None] | None = None
        self._boosts: dict[str, tuple[int, int]] = {}

    async def cog_load(self) -> None:
        self._warn_missing_intents()
        await self.db.connect()
        await self._load_boosts()
        self.voice_xp_task.start()
        if LEVEL_ROLES:
            self._role_sync_task = asyncio.create_task(self._sync_roles_on_startup())

    def _warn_missing_intents(self) -> None:
        """Der Cog läuft auch ohne diese Intents, aber Teile funktionieren dann nicht richtig."""
        consequences = {
            "message_content": "Commands werden nicht erkannt und Befehle geben XP",
            "members": "Level-Rollen werden beim Bot-Start und Wiederbeitritt nicht vergeben",
            "voice_states": "es gibt keine Voice-XP",
        }
        for intent, consequence in consequences.items():
            if not getattr(self.bot.intents, intent):
                log.warning("Intent '%s' ist im Bot nicht aktiviert – %s.", intent, consequence)

    async def cog_unload(self) -> None:
        if self._role_sync_task is not None:
            self._role_sync_task.cancel()
        self.voice_xp_task.cancel()
        await self.db.close()

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        if ctx.guild.id != cfg.GUILD_ID:
            raise WrongGuild()
        return True

    # ==================================================================
    # Text-XP
    # ==================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.guild.id != cfg.GUILD_ID:
            return
        if message.author.bot or message.webhook_id is not None:
            return
        if message.type not in XP_MESSAGE_TYPES or not isinstance(message.author, discord.Member):
            return

        if NO_XP_CHANNELS and _relevant_channel_ids(message.channel) & NO_XP_CHANNELS:  # type: ignore[arg-type]
            return

        # Prefix-Commands (z. B. ".leaderboard") geben keine XP
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        gained = self._boosted("text", random.randint(cfg.XP_MIN, cfg.XP_MAX))
        new_total = await self.db.add_text_xp(
            message.author.id, gained, int(time.time()), cfg.COOLDOWN_SECONDS
        )
        if new_total is None:
            return  # Cooldown aktiv

        await self._after_xp_gain(message.author, new_total - gained, new_total, message.channel)

    # ==================================================================
    # Voice-XP: jede Minute für alle verbundenen, nicht tauben Nutzer
    # ==================================================================

    @tasks.loop(seconds=60)
    async def voice_xp_task(self) -> None:
        day = discord.utils.utcnow().date().isoformat()  # Tageslimit setzt um 00:00 UTC zurück
        guild = self.bot.get_guild(cfg.GUILD_ID)
        if guild is None:
            return
        try:
            await self._voice_tick(guild, day)
        except Exception:
            # Ein Fehler darf den Loop nicht stoppen
            log.exception("Voice-XP-Tick fehlgeschlagen (Guild %s)", guild.id)

    @voice_xp_task.before_loop
    async def _before_voice_xp_task(self) -> None:
        await self.bot.wait_until_ready()

    async def _voice_tick(self, guild: discord.Guild, day: str) -> None:
        if not cfg.VOICE_XP_ENABLED or cfg.VOICE_XP_PER_MIN <= 0:
            return

        afk_id = guild.afk_channel.id if guild.afk_channel else None

        amount = self._boosted("voice", cfg.VOICE_XP_PER_MIN)
        for channel in guild.voice_channels:
            if channel.id == afk_id or _relevant_channel_ids(channel) & NO_XP_CHANNELS:
                continue
            members = [m for m in channel.members if self._earns_voice_xp(m)]
            if len(members) < cfg.VOICE_MIN_MEMBERS:
                continue  # z. B. alleine im Channel → kein XP (AFK-Farming)

            for member in members:
                try:
                    new_total = await self.db.add_voice_xp(
                        member.id, amount, day, cfg.VOICE_DAILY_CAP_MINUTES
                    )
                    if new_total is not None:
                        await self._after_xp_gain(member, new_total - amount, new_total, channel)
                except Exception:
                    log.exception("Voice-XP für %s in Guild %s fehlgeschlagen", member.id, guild.id)

    @staticmethod
    def _earns_voice_xp(member: discord.Member) -> bool:
        voice = member.voice
        if member.bot or voice is None or voice.self_deaf or voice.deaf:
            return False
        if cfg.VOICE_REQUIRE_UNMUTED and (voice.self_mute or voice.mute):
            return False
        return True

    # ==================================================================
    # Levelup & Rollen
    # ==================================================================

    async def _after_xp_gain(
        self,
        member: discord.Member,
        old_total: int,
        new_total: int,
        fallback_channel: discord.abc.Messageable | None,
    ) -> None:
        old_level, _ = level_from_total_xp(old_total)
        new_level, _ = level_from_total_xp(new_total)
        if new_level <= old_level:
            return
        await self._announce_levelup(member, old_level, new_level, fallback_channel)  # display.py
        await self._sync_level_roles(member, new_level)

    async def _sync_level_roles(self, member: discord.Member, level: int) -> bool:
        """Gleicht die Level-Rollen eines Mitglieds an sein Level an. Returns: ob etwas geändert wurde."""
        guild = member.guild
        if not LEVEL_ROLES or member.bot:
            return False

        reached = [role_id for lv, role_id in LEVEL_ROLES if lv <= level]
        if cfg.STACK_ROLES:
            target_ids = set(reached)
        else:
            target_ids = {reached[-1]} if reached else set()

        to_add: list[discord.Role] = []
        to_remove: list[discord.Role] = []
        for _, role_id in LEVEL_ROLES:
            role = guild.get_role(role_id)
            if role is None or not role.is_assignable():
                continue
            has_role = role in member.roles
            if role_id in target_ids and not has_role:
                to_add.append(role)
            elif role_id not in target_ids and has_role:
                to_remove.append(role)

        if not to_add and not to_remove:
            return False

        if not guild.me.guild_permissions.manage_roles:
            if guild.id not in self._warned_missing_perms:
                self._warned_missing_perms.add(guild.id)
                log.warning("Bot fehlt 'Rollen verwalten' in Guild %s – Level-Rollen inaktiv", guild.id)
            return False

        try:
            if to_add:
                await member.add_roles(*to_add, reason=f"Level-Belohnung (Level {level})")
            if to_remove:
                await member.remove_roles(*to_remove, reason=f"Level-Rollen angepasst (Level {level})")
        except discord.HTTPException as exc:
            log.warning("Rollen für %s in Guild %s nicht angepasst: %s", member.id, guild.id, exc)
            return False
        return True

    async def _sync_all_members(self, guild: discord.Guild) -> tuple[int, int]:
        """Gleicht die Level-Rollen aller gespeicherten Mitglieder ab. Returns: (geprüft, geändert)."""
        checked = changed = 0
        for user_id, total_xp in await self.db.get_all_users():
            member = guild.get_member(user_id)
            if member is None:
                continue  # hat den Server verlassen oder ist nicht im Cache
            checked += 1
            level, _ = level_from_total_xp(total_xp)
            if await self._sync_level_roles(member, level):
                changed += 1
        return checked, changed

    async def _sync_roles_on_startup(self) -> None:
        """Gleicht beim Bot-Start die Level-Rollen aller Mitglieder ab (z. B. nach Änderungen an LEVEL_ROLES)."""
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(cfg.GUILD_ID)
        if guild is None:
            log.warning("Bot ist nicht auf dem Server %s (GUILD_ID in config.py) – kein Rollen-Abgleich", cfg.GUILD_ID)
            return
        for level, role_id in LEVEL_ROLES:
            role = guild.get_role(role_id)
            if role is None:
                log.warning("Level-Rolle %s (Level %s) gibt es auf dem Server nicht – ID prüfen", role_id, level)
            elif not role.is_assignable():
                log.warning(
                    "Level-Rolle '%s' (Level %s) kann nicht vergeben werden – die Bot-Rolle muss "
                    "über ihr stehen", role.name, level,
                )
        try:
            checked, changed = await self._sync_all_members(guild)
        except Exception:
            log.exception("Level-Rollen-Abgleich fehlgeschlagen (Guild %s)", guild.id)
            return
        log.info("Level-Rollen abgeglichen (Guild %s): %d geprüft, %d angepasst", guild.id, checked, changed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Gibt zurückkehrenden Mitgliedern ihre Level-Rollen wieder (die XP bleiben gespeichert)."""
        if not LEVEL_ROLES or member.bot or member.guild.id != cfg.GUILD_ID:
            return
        level, _ = level_from_total_xp(await self.db.get_total_xp(member.id))
        await self._sync_level_roles(member, level)

    # ==================================================================
    # Fehlerbehandlung für alle Commands dieses Cogs
    # ==================================================================

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        # Hinweis: Hat der Haupt-Bot einen eigenen globalen `on_command_error`, läuft der zusätzlich.
        # Doppelte Antworten verhindert dort: `if ctx.cog and ctx.cog.has_error_handler(): return`
        usage = (
            f"`{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.command.usage or ctx.command.signature}`"
            if ctx.command else ""
        )
        if isinstance(error, commands.NoPrivateMessage):
            text = "Das geht nur auf einem Server."
        elif isinstance(error, commands.MissingPermissions):
            text = "Dafür brauchst du die Berechtigung **Server verwalten**."
        elif isinstance(error, commands.MissingRequiredArgument):
            text = f"Da fehlt etwas. Nutzung: {usage}"
        elif isinstance(error, commands.RangeError):
            text = f"`{error.value}` liegt außerhalb von {error.minimum}–{error.maximum}."
        elif isinstance(error, commands.MemberNotFound):
            text = f"Mitglied `{error.argument}` nicht gefunden."
        elif isinstance(error, commands.BadArgument):
            text = f"Ungültige Eingabe: {error}\nNutzung: {usage}"
        elif isinstance(error, commands.CommandOnCooldown):
            text = f"Kurz warten – noch {error.retry_after:.0f}s."
        elif isinstance(error, WrongGuild):
            text = "Leveling ist auf diesem Server nicht aktiv."
        elif isinstance(error, commands.CheckFailure):
            text = "Das darfst du hier nicht."
        else:
            log.error("Fehler in .%s", ctx.command.qualified_name if ctx.command else "?", exc_info=error)
            text = "Da ist etwas schiefgelaufen. Details stehen im Bot-Log."
        try:
            await reply(ctx, text)
        except discord.HTTPException:
            pass

    # ==================================================================
    # Admin: .xp …
    # ==================================================================

    @commands.group(name=cfg.COMMAND_XP)
    @commands.has_guild_permissions(manage_guild=True)
    async def xp_group(self, ctx: commands.Context) -> None:
        """XP eines Mitglieds verwalten (Admin)."""
        if ctx.invoked_subcommand is None:
            await _send_group_help(ctx)

    async def _apply_admin_change(self, member: discord.Member, new_total: int) -> int:
        level, _ = level_from_total_xp(new_total)
        await self._sync_level_roles(member, level)
        return level

    @xp_group.command(name="add")
    async def xp_add(
        self, ctx: commands.Context, mitglied: discord.Member, betrag: commands.Range[int, 1, 1_000_000]
    ) -> None:
        """Fügt einem Mitglied XP hinzu."""
        new_total = await self.db.change_xp(mitglied.id, betrag)
        level = await self._apply_admin_change(mitglied, new_total)
        await reply(ctx, f"{format_number(betrag)} XP zu {mitglied.mention} hinzugefügt (jetzt Level {level}).")

    @xp_group.command(name="remove")
    async def xp_remove(
        self, ctx: commands.Context, mitglied: discord.Member, betrag: commands.Range[int, 1, 1_000_000]
    ) -> None:
        """Zieht einem Mitglied XP ab."""
        new_total = await self.db.change_xp(mitglied.id, -betrag)
        level = await self._apply_admin_change(mitglied, new_total)
        await reply(ctx, f"{format_number(betrag)} XP von {mitglied.mention} abgezogen (jetzt Level {level}).")

    # ==================================================================
    # Admin: .level-config …
    # ==================================================================

    @commands.group(name=cfg.COMMAND_LEVEL_CONFIG)
    @commands.has_guild_permissions(manage_guild=True)
    async def config_group(self, ctx: commands.Context) -> None:
        """Leveling-Einstellungen anzeigen (Admin)."""
        if ctx.invoked_subcommand is None:
            await _send_group_help(ctx)

    @config_group.command(name="show")
    async def config_show(self, ctx: commands.Context) -> None:
        """Zeigt die Einstellungen aus config.py."""
        guild = ctx.guild
        assert guild is not None
        channel = guild.get_channel(cfg.LEVELUP_CHANNEL_ID) if cfg.LEVELUP_CHANNEL_ID else None
        cap = f"{cfg.VOICE_DAILY_CAP_MINUTES} min/Tag" if cfg.VOICE_DAILY_CAP_MINUTES else "kein Limit"
        voice = (
            f"{cfg.VOICE_XP_PER_MIN} XP/min · {cap}" + (" · nur unmuted" if cfg.VOICE_REQUIRE_UNMUTED else "")
            if cfg.VOICE_XP_ENABLED else "deaktiviert"
        )

        embed = discord.Embed(title="Leveling-Konfiguration", color=EMBED_COLOR)
        embed.add_field(
            name="Text-XP", value=f"{cfg.XP_MIN}–{cfg.XP_MAX} pro Nachricht · {cfg.COOLDOWN_SECONDS}s Cooldown"
        )
        embed.add_field(name="Voice-XP", value=voice)
        embed.add_field(name="XP-Boost", value="\n".join(self._boost_lines()) or "–", inline=False)
        embed.add_field(
            name="Levelup-Channel",
            value=channel.mention if channel else "Kanal, in dem das Levelup passiert",
            inline=False,
        )
        embed.add_field(
            name="Levelup",
            value="Neue Level-Rolle: Ping + Levelup-Bild · sonst keine Nachricht",
            inline=False,
        )
        no_xp = [f"<#{i}>" for i in cfg.NO_XP_CHANNELS if guild.get_channel(i)]
        embed.add_field(name="Ohne XP", value=" ".join(no_xp)[:1024] or "–", inline=False)
        level_roles = []
        for level, role_id in LEVEL_ROLES:
            role = guild.get_role(role_id)
            if role is None:
                continue  # Rolle existiert nicht (mehr)
            status = "" if role.is_assignable() else " (Bot-Rolle steht nicht darüber)"
            level_roles.append(f"Level {level} → {role.mention}{status}")
        mode = "alle erreichten behalten" if cfg.STACK_ROLES else "nur die höchste"
        embed.add_field(
            name=f"Level-Rollen ({mode})", value="\n".join(level_roles)[:1024] or "–", inline=False
        )
        embed.set_footer(text="Ändern: config.py, danach Bot neu starten")
        await reply(ctx, embed=embed)



async def setup(bot: commands.Bot) -> None:
    _validate_config()
    await bot.add_cog(Leveling(bot, LevelingDatabase(cfg.LEVEL_DB_PATH)))
