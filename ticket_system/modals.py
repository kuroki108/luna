from __future__ import annotations

import discord

from ticket_system import embed_builder, ticket_manager
from ticket_system.ticket_manager import TicketLimitReached


async def _finish_application(interaction: discord.Interaction, ticket_type: str, answers: dict[str, str]) -> None:
    from ticket_system.views import TicketControlView  # lokaler Import verhindert Zirkelbezug

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        channel = await ticket_manager.create_ticket(
            guild=interaction.guild,
            member=interaction.user,
            ticket_type=ticket_type,
            answers=answers,
        )
    except TicketLimitReached:
        await interaction.followup.send(
            "❌ Du hast bereits eine offene Bewerbung dieser Art. Bitte warte, bis diese bearbeitet wurde.",
            ephemeral=True,
        )
        return

    embed = embed_builder.application_ticket(interaction.user, ticket_type, answers)
    await channel.send(
        content=ticket_manager.opening_mentions(interaction.user, ticket_type),
        embed=embed,
        view=TicketControlView(show_add_user=False),
    )
    await channel.send(embed=embed_builder.ticket_info(ticket_type))
    await interaction.followup.send(f"✅ Deine Bewerbung wurde erstellt: {channel.mention}", ephemeral=True)


class SupporterApplicationModal(discord.ui.Modal, title="Bewerbung: Supporter"):
    alter = discord.ui.TextInput(label="Wie alt bist du?", max_length=10, required=True)
    erfahrung = discord.ui.TextInput(
        label="Hast du Erfahrung als Moderator?", style=discord.TextStyle.paragraph, max_length=500, required=True
    )
    motivation = discord.ui.TextInput(
        label="Warum möchtest du Helper werden?", style=discord.TextStyle.paragraph, max_length=500, required=True
    )
    verfuegbarkeit = discord.ui.TextInput(label="Wie viel Zeit hast du pro Woche?", max_length=100, required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = {
            "Alter": self.alter.value,
            "Erfahrung als Moderator": self.erfahrung.value,
            "Motivation": self.motivation.value,
            "Verfügbarkeit pro Woche": self.verfuegbarkeit.value,
        }
        await _finish_application(interaction, "application_supporter", answers)