from __future__ import annotations

from pathlib import Path

import discord

import config

# Pfad zum GIF, das im Support-Panel angezeigt wird (unabhängig vom Arbeitsverzeichnis)
GIF_PATH = Path(__file__).resolve().parent.parent / "assets" / "gif.gif"

# Menschlich lesbare Labels für die Ticket-Typen (u. a. für Embeds/Kanalnamen)
TICKET_TYPE_LABELS = {
    "support": "Support",
    "support_report": "Report",
    "support_admin": "Admin",
    "application_supporter": "Bewerbung - Supporter",
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
    "application_supporter": (
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


def application_panel() -> discord.Embed:
    return discord.Embed(
        title="📋 Werde Teil des Teams",
        description=(
            "Wir suchen aktuell Verstärkung! Wähle unten aus, für welche Position "
            "du dich bewerben möchtest. Es öffnet sich ein kurzes Formular."
        ),
        color=config.EMBED_COLOR,
    )


# ---------------------------------------------------------------------------
# Nachrichten im Ticket
# ---------------------------------------------------------------------------
def ticket_welcome(member: discord.Member, ticket_type: str) -> discord.Embed:
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


def application_ticket(member: discord.Member, ticket_type: str, answers: dict[str, str]) -> discord.Embed:
    desc = "\n".join(f"**{q}**\n{a}" for q, a in answers.items())
    embed = discord.Embed(
        title=f"📋 {type_label(ticket_type)}",
        description=f"Bewerbung von {member.mention}\n\n{desc}",
        color=config.EMBED_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
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
