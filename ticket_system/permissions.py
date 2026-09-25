from __future__ import annotations

import discord

import config


def _has_role(member: discord.Member, role_id: int) -> bool:
    if not role_id:
        return False
    return any(r.id == role_id for r in member.roles)


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or _has_role(member, config.ADMIN_ROLE_ID)


def is_support_staff(member: discord.Member) -> bool:
    return is_admin(member) or _has_role(member, config.SUPPORT_STAFF_ROLE_ID)


def is_application_staff(member: discord.Member) -> bool:
    return is_admin(member) or _has_role(member, config.APPLICATION_STAFF_ROLE_ID)


def is_staff_for_ticket_type(member: discord.Member, ticket_type: str) -> bool:
    if ticket_type == "support_admin":
        return is_admin(member)
    if ticket_type.startswith("support"):
        return is_support_staff(member)
    if ticket_type.startswith("application"):
        return is_application_staff(member)
    return is_admin(member)
