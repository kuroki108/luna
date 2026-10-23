from __future__ import annotations

import discord
from discord.ext import commands

from ticket_system import permissions, ticket_manager
from ticket_system.storage import store as ticket_store
from ticket_system.views import ConfirmDeleteView


class TicketCommandsCog(commands.Cog):
    """Prefix-Commands: `adduser` und `delete` im Ticket-Kanal, `transcript` für den aktuellen Kanal."""

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

    @commands.command(name="transcript")
    @commands.guild_only()
    async def transcript_command(self, ctx: commands.Context) -> None:
        """Erstellt ein Transcript des aktuellen Kanals und sendet es in den Log-Kanal."""
        if not permissions.is_admin(ctx.author):
            await ctx.send("Nur Admins können Transcripts erstellen.", delete_after=5)
            return
        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("Transcripts gehen nur für Textkanäle.", delete_after=5)
            return

        try:
            async with ctx.typing():
                log_channel = await ticket_manager.archive_channel_transcript(channel, ctx.author)
        except discord.Forbidden:
            await ctx.send(f"Ich habe keinen Zugriff auf den Verlauf von {channel.mention}.", delete_after=5)
            return
        if not log_channel:
            await ctx.send("Der Transcript-Log-Kanal wurde nicht gefunden.", delete_after=5)
            return
        await ctx.send(f"Transcript von {channel.mention} wurde in {log_channel.mention} gespeichert.")
