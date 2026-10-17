from __future__ import annotations

import discord
from discord.ext import commands

from ticket_system import permissions, ticket_manager
from ticket_system.storage import store as ticket_store
from ticket_system.views import ConfirmDeleteView


class TicketCommandsCog(commands.Cog):
    """Prefix-Commands im Ticket-Kanal: `adduser` und `delete`."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="adduser")
    @commands.guild_only()
    async def adduser_command(self, ctx: commands.Context, member: discord.Member) -> None:
        """Fügt einen Nutzer zum Ticket-Kanal hinzu."""
        ticket = await ticket_store.get_ticket(ctx.channel.id)
        if not ticket:
            await ctx.send("Dies ist kein aktiver Ticket-Kanal.", delete_after=5)
            return
        if not permissions.is_staff_for_ticket_type(ctx.author, ticket.type):
            await ctx.send("Nur Teammitglieder können Nutzer hinzufügen.", delete_after=5)
            return
        if not await ticket_manager.add_user(ctx.channel, member, ticket):
            await ctx.send("Der Nutzer ist bereits im Ticket oder ist der Ersteller.", delete_after=5)
            return
        await ctx.send(f"{member.mention} wurde von {ctx.author.mention} zum Ticket hinzugefügt.")

    @commands.command(name="delete")
    @commands.guild_only()
    async def delete_command(self, ctx: commands.Context) -> None:
        """Fordert die Bestätigung zum Löschen des aktuellen Tickets an."""
        ticket = await ticket_store.get_ticket(ctx.channel.id)
        if not ticket:
            await ctx.send("Dies ist kein aktiver Ticket-Kanal.", delete_after=5)
            return
        if not permissions.is_staff_for_ticket_type(ctx.author, ticket.type):
            await ctx.send("Nur Teammitglieder können Tickets löschen.", delete_after=5)
            return
        await ctx.send(
            "Bist du sicher? Das Ticket wird gelöscht; das Transcript bleibt im Log-Kanal erhalten.",
            view=ConfirmDeleteView(ctx.channel.id, ctx.author.id),
        )
