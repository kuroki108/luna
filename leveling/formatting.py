"""Kleine Text-Helfer für Ausgaben in Discord."""
from __future__ import annotations

import discord
from discord.ext import commands

NO_PINGS = discord.AllowedMentions.none()


def format_number(value: int) -> str:
    """12345 -> '12.345'"""
    return f"{value:,}".replace(",", ".")


async def reply(ctx: commands.Context, content: str | None = None, **kwargs) -> discord.Message:
    """Antwortet ohne jemanden zu pingen (auch nicht den Autor)."""
    kwargs.setdefault("allowed_mentions", NO_PINGS)
    return await ctx.reply(content, mention_author=False, **kwargs)
