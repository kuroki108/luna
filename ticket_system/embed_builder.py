from __future__ import annotations

from pathlib import Path

import discord

import config

# Pfad zum GIF, das im Support-Panel angezeigt wird (unabhängig vom Arbeitsverzeichnis)
GIF_PATH = Path(__file__).resolve().parent.parent / "assets" / "gif.gif"
# Banner für das Anforderungen-Embed im Bewerbungs-Panel
BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "banner.png"

# Menschlich lesbare Labels für die Ticket-Typen (u. a. für Embeds/Kanalnamen)
TICKET_TYPE_LABELS = {
    "support": "Support",
    "support_report": "Report",
    "support_admin": "Admin",
    "support_unban": "Entbannung",
    "support_jail": "Jail",
    "application_supporter": "Bewerbung - Palace Helper",
    "application_creator": "Bewerbung - Content Creator",
}

# Inhalt des separaten Info-Embeds, das nach jedem Ticket-Öffnen geschickt wird.
# (Titel, Beschreibung) pro Ticket-Typ – frei anpassbar.
TICKET_INFO_TEXTS: dict[str, tuple[str, str]] = {
    "support": (
        "<a:lunaRpalace:1532899555715055616> Wichtige Infos",
        "• Beschreibe dein Problem so genau wie möglich.\n"
        "• Screenshots helfen uns oft weiter.\n"
        "• Bitte pinge das Team nicht unnötig an.",
    ),
    "support_report": (
        "<a:lunaRpalace:1532899555715055616> So meldest du jemanden",
        "• **Wen** möchtest du melden? (Name + ID)\n"
        "• **Was** ist passiert?\n"
        "• **Beweise** (Screenshots, Nachrichtenlinks)",
    ),
    "support_admin": (
        "<a:lunaRpalace:1532899555715055616> Admin-Ticket",
        "• Dieses Ticket sehen nur Admins.\n"
        "• Bitte nutze es nur für Anliegen, die nicht der normale Support klären kann.",
    ),
    "support_unban": (
        "<a:lunaRpalace:1532899555715055616> Dein Entbannungsantrag",
        "• **Wann** und **warum** wurdest du gebannt?\n"
        "• Warum sollten wir dich entbannen?\n"
        "• Bitte bleib ehrlich und respektvoll.",
    ),
    "support_jail": (
        "<a:lunaRpalace:1532899555715055616> Wichtige Infos",
        "• Beschreibe dein Problem so genau wie möglich.\n"
        "• Screenshots helfen uns oft weiter.\n"
        "• Bitte pinge das Team nicht unnötig an.",
    ),
    "application_supporter": (
        "<a:lunaRpalace:1532899555715055616> Wie geht es weiter?",
        "• Das Team prüft deine Bewerbung.\n"
        "• Rückfragen stellen wir dir hier im Ticket.\n"
        "• Bitte hab etwas Geduld und frag nicht ständig nach.",
    ),
    "application_creator": (
        "<a:lunaRpalace:1532899555715055616> Wie geht es weiter?",
        "• Das Team prüft deine Bewerbung.\n"
        "• Rückfragen stellen wir dir hier im Ticket.\n"
        "• Bitte hab etwas Geduld und frag nicht ständig nach.",
    ),
}


def type_label(ticket_type: str) -> str:
    return TICKET_TYPE_LABELS.get(ticket_type, ticket_type)


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------
def support_panel_file() -> discord.File:
    """GIF-Anhang für das Support-Panel – muss zusammen mit dem Embed gesendet werden."""
    return discord.File(GIF_PATH, filename="gif.gif")


def banner_file() -> discord.File:
    """Banner-Anhang für das Anforderungen-Embed – muss zusammen mit dem Embed gesendet werden."""
    return discord.File(BANNER_PATH, filename="banner.png")


def support_panel() -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <a:lunaRpalace:1533125760884281355> __SUPPORT__\n"
            "_ _\n"
            "Um ein Ticket zu öffnen, wähle bitte unten eine Option aus.\n\n"
            "**Report**\n"
            "-# Melde einen Nutzer\n\n"
            "**Support**\n"
            "-# Hilfe bei allgemeinen Fragen und Problemen\n\n"
            "**Admin**\n"
            "-# Direkte Fragen an unsere Admins:\n"
            "-# • Anliegen an einen Admin\n"
            "-# • Fragen oder Wünsche zu unserem Bot\n"
            "-# • Partnerschaften\n\n"
            "-# Das Team wird sich so schnell wie möglich um dein Anliegen kümmern.\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
    )
    embed.set_image(url="attachment://gif.gif")
    return embed


def unban_panel() -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <a:lunaRpalace:1533125760884281355> __ENTBANNUNG__\n"
            "_ _\n"
            "-# Stelle einen Antrag auf Entbannung vom Hauptserver\n\n"
            "-# Das Team wird sich so schnell wie möglich um deinen Antrag kümmern.\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
    )
    embed.set_image(url="attachment://gif.gif")
    return embed


def jail_panel() -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <a:lunaRpalace:1533125760884281355> __JAIL-SUPPORT__\n"
            "_ _\n"
            "Um ein Ticket zu öffnen, klicke bitte unten auf „**Ticket erstellen!**“.\n\n"
            "-# Das Team wird sich so schnell wie möglich um dein Anliegen kümmern.\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
    )
    embed.set_image(url="attachment://gif.gif")
    return embed


def application_panel(ctx) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <:lunaRpalace:1541149690760921139> __Team-Bewerbung__\n\n"
            "### Willkommen auf __lunaR palace!__\n"
            "-# Du hast Lust, unsere Community mitzugestalten?\n"
            "-# Dann werde gerne ein Teil von uns!"
        ),
        color=config.EMBED_COLOR,
    )
    embed.set_image(url="attachment://gif.gif")
    if ctx.guild and ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    return embed


def application_panel_Anforderungen(ctx=None) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "### Anforderungen\n\n"
            "Um angenommen zu werden, musst du folgende Kriterien erfüllen:\n\n"
            "<:lunaRpalace:1541211249797242881> mindestens 16 Jahre alt\n"
            "<:lunaRpalace:1541211249797242881> ein funktionierendes Mikrofon\n"
            "<:lunaRpalace:1541211249797242881> Teamfähigkeit/Ehrlichkeit\n"
            "<:lunaRpalace:1541211249797242881> Erfahrung im jeweiligen Bereich von Vorteil\n"
            "<:lunaRpalace:1541211249797242881> Motivation & Zuverlässigkeit\n\n"
            "Wähle unten deine Wunschrolle aus und werde Teil unseres Teams! <a:lunaRpalace:1532899555715055616>\n\n"
            "-# Bitte beachte, dass die Bearbeitung etwas Zeit in Anspruch nehmen kann."
        ),
        color=config.EMBED_COLOR,
    )
    embed.set_image(url="attachment://banner.png")
    return embed


# ---------------------------------------------------------------------------
# Nachrichten im Ticket
# ---------------------------------------------------------------------------
def ticket_welcome(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <a:lunaRpalace:1533125760884281355> __SUPPORT-TICKET__\n\n"
            f"### Willkommen {member.mention}!\n"
            "Bitte beschreibe dein Anliegen so genau wie möglich.\n\n"
            "-# Ein Teammitglied meldet sich in Kürze bei dir.\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    # Kleines Bot-Profilbild vorne im Footer
    embed.set_footer(text="⟣ 🪽 lunaR palace ₊ ⊹", icon_url=member.guild.me.display_avatar.url)
    return embed


def report_welcome(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <a:lunaRpalace:1533125760884281355> __REPORT-TICKET__\n\n"
            f"### Willkommen {member.mention}!\n"
            "Bitte beschreibe dein Anliegen so genau wie möglich.\n\n"
            "-# Ein Teammitglied meldet sich in Kürze bei dir.\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text="⟣ 🪽 lunaR palace ₊ ⊹", icon_url=member.guild.me.display_avatar.url)
    return embed


def admin_welcome(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <a:lunaRpalace:1533125760884281355> __ADMIN-TICKET__\n\n"
            f"### Willkommen {member.mention}!\n"
            "Bitte beschreibe dein Anliegen so genau wie möglich.\n\n"
            "-# Ein Teammitglied meldet sich in Kürze bei dir.\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text="⟣ 🪽 lunaR palace ₊ ⊹", icon_url=member.guild.me.display_avatar.url)
    return embed


def unban_welcome(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <a:lunaRpalace:1533125760884281355> __ENTBANNUNGS-TICKET__\n\n"
            f"### Willkommen {member.mention}!\n"
            "Bitte beschreibe dein Anliegen so genau wie möglich.\n\n"
            "-# Ein Teammitglied meldet sich in Kürze bei dir.\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text="⟣ 🪽 lunaR palace ₊ ⊹", icon_url=member.guild.me.display_avatar.url)
    return embed


def jail_welcome(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        description=(
            "# <a:lunaRpalace:1533125760884281355> __JAIL-TICKET__\n\n"
            f"### Willkommen {member.mention}!\n"
            "Bitte beschreibe dein Anliegen so genau wie möglich.\n\n"
            "-# Ein Teammitglied meldet sich in Kürze bei dir.\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    guild = member.guild
    embed.set_footer(text=guild.name, icon_url=guild.icon.url if guild.icon else None)
    return embed


def welcome_for(member: discord.Member, ticket_type: str) -> discord.Embed:
    """Wählt das passende Willkommens-Embed für den Ticket-Typ."""
    if ticket_type == "support_jail":
        return jail_welcome(member)
    if ticket_type == "support_report":
        return report_welcome(member)
    if ticket_type == "support_admin":
        return admin_welcome(member)
    if ticket_type == "support_unban":
        return unban_welcome(member)
    return ticket_welcome(member)


def ticket_info(ticket_type: str) -> discord.Embed:
    title, description = TICKET_INFO_TEXTS.get(ticket_type, TICKET_INFO_TEXTS["support"])
    return discord.Embed(title=title, description=description, color=config.EMBED_COLOR)


def application_ticket(member: discord.Member, ticket_type: str, answers: dict[str, str]) -> discord.Embed:
    answers_text = "\n\n".join(f"**{q}**\n{a}" for q, a in answers.items())
    role = type_label(ticket_type).removeprefix("Bewerbung - ")
    embed = discord.Embed(
        description=(
            f"# <:lunaRpalace:1541149690760921139> __BEWERBUNG – {role}__\n\n"
            f"### Bewerbung von {member.mention}!\n\n"
            f"{answers_text}\n"
            "_ _"
        ),
        color=config.EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="⟣ 🪽 lunaR palace ₊ ⊹", icon_url=member.guild.me.display_avatar.url)
    return embed


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------
def ticket_deleted_log(
    channel: discord.TextChannel,
    ticket_type: str,
    opener: discord.Member | None,
    opener_id: int,
    deleter: discord.Member,
) -> discord.Embed:
    return discord.Embed(
        title="Ticket gelöscht",
        description=(
            f"**Kanal:** #{channel.name}\n"
            f"**Typ:** {type_label(ticket_type)}\n"
            f"**Ersteller:** {opener.mention if opener else opener_id}\n"
            f"**Gelöscht von:** {deleter.mention}"
        ),
        color=config.EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
