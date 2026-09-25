from __future__ import annotations

import io
import logging
import re
from typing import Optional

import discord

import config
from ticket_system import embed_builder
from ticket_system.storage import TicketData, store
from ticket_system.transcript import build_transcript

log = logging.getLogger(__name__)


def _sanitize(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\-]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name[:20] or "user"


def _category_and_prefix(ticket_type: str) -> tuple[int, str]:
    if ticket_type == "support_report":
        return config.REPORT_CATEGORY_ID, config.REPORT_CHANNEL_PREFIX
    if ticket_type == "support_admin":
        return config.ADMIN_CATEGORY_ID, config.ADMIN_CHANNEL_PREFIX
    if ticket_type == "support":
        return config.SUPPORT_CATEGORY_ID, config.SUPPORT_CHANNEL_PREFIX
    return config.APPLICATION_CATEGORY_ID, config.APPLICATION_CHANNEL_PREFIX


def _staff_role_id(ticket_type: str) -> int:
    if ticket_type == "support_admin":
        return config.ADMIN_ROLE_ID
    if ticket_type.startswith("support"):
        return config.SUPPORT_STAFF_ROLE_ID
    return config.APPLICATION_STAFF_ROLE_ID


class TicketLimitReached(Exception):
    """Wird ausgelöst, wenn ein Nutzer bereits die maximale Anzahl offener Tickets dieses Typs hat."""


async def create_ticket(
    guild: discord.Guild,
    member: discord.Member,
    ticket_type: str,
    answers: Optional[dict[str, str]] = None,
) -> discord.TextChannel:
    """Erstellt einen neuen Ticket-Kanal inkl. Berechtigungen, Speicherung und Begrüßungsnachricht."""

    # Limit pruefen + Zaehler ziehen: atomar in einem Lock, damit zwei gleichzeitige
    # Ticket-Erstellungen desselben Nutzers das Limit nicht umgehen koennen.
    prefix_for_limit = "application" if ticket_type.startswith("application") else "support"
    max_allowed = (
        config.MAX_OPEN_APPLICATION_TICKETS_PER_USER
        if prefix_for_limit == "application"
        else config.MAX_OPEN_SUPPORT_TICKETS_PER_USER
    )
    counter_key = "application" if prefix_for_limit == "application" else "support"
    number = await store.reserve_ticket_slot(
        member.id, ticket_type if prefix_for_limit == "application" else "support", max_allowed, counter_key
    )
    if number is None:
        raise TicketLimitReached()

    category_id, channel_prefix = _category_and_prefix(ticket_type)
    category = guild.get_channel(category_id) if category_id else None
    staff_role_id = _staff_role_id(ticket_type)
    staff_role = guild.get_role(staff_role_id) if staff_role_id else None
    admin_role = guild.get_role(config.ADMIN_ROLE_ID) if config.ADMIN_ROLE_ID else None

    channel_name = f"{channel_prefix}-{number:04d}-{_sanitize(member.name)}"

    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True, read_message_history=True
        ),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_messages=True
        )
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_messages=True
        )

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        topic=f"Ticket-Typ: {ticket_type} | Ersteller: {member.id}",
        reason=f"Ticket erstellt von {member} ({member.id})",
    )

    ticket = TicketData(channel_id=channel.id, type=ticket_type, opener_id=member.id, answers=answers or {})
    await store.save_ticket(ticket)

    return channel


async def generate_transcript_file(channel: discord.TextChannel) -> discord.File:
    html_content = await build_transcript(channel)
    buffer = io.BytesIO(html_content.encode("utf-8"))
    return discord.File(buffer, filename=f"transcript-{channel.name}.html")


async def delete_ticket(channel: discord.TextChannel, deleter: discord.Member, ticket: TicketData) -> None:
    log_channel = None
    if config.TRANSCRIPT_LOG_CHANNEL_ID:
        log_channel = channel.guild.get_channel(config.TRANSCRIPT_LOG_CHANNEL_ID)

    if not log_channel:
        log.error("Transcript-Log-Kanal %s wurde nicht gefunden.", config.TRANSCRIPT_LOG_CHANNEL_ID)
        return

    try:
        file = await generate_transcript_file(channel)
        opener = channel.guild.get_member(ticket.opener_id)
        embed = embed_builder.ticket_deleted_log(channel, ticket.type, opener, ticket.opener_id, deleter)
        await log_channel.send(embed=embed, file=file)
    except Exception:
        log.exception("Transcript für Ticket %s konnte nicht archiviert werden.", channel.id)
        return

    await store.delete_ticket(channel.id)
    await channel.delete(reason=f"Ticket gelöscht von {deleter} ({deleter.id})")


async def add_user(channel: discord.TextChannel, target: discord.Member, ticket: TicketData) -> bool:
    if target.id == ticket.opener_id or target.id in ticket.added_users:
        return False
    ticket.added_users.append(target.id)
    await store.save_ticket(ticket)
    await channel.set_permissions(target, view_channel=True, send_messages=True, read_message_history=True)
    return True

