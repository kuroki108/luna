from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ticket_system import embed_builder
from ticket_system.views import SupportPanelView, ApplicationPanelView


class PanelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="setup-support", description="Postet das Support-Ticket-Panel in diesem Kanal.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_support(self, interaction: discord.Interaction) -> None:
        embed = embed_builder.support_panel()
        await interaction.channel.send(embed=embed, view=SupportPanelView())
        await interaction.response.send_message("Support-Panel wurde gepostet.", ephemeral=True)




    @app_commands.command(name="setup-bewerbung", description="Postet das Bewerbungs-Panel in diesem Kanal.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_bewerbung(self, interaction: discord.Interaction) -> None:
        embed = embed_builder.application_panel()
        await interaction.channel.send(embed=embed, view=ApplicationPanelView())
        await interaction.response.send_message("Bewerbungs-Panel wurde gepostet.", ephemeral=True)

    @setup_support.error
    @setup_bewerbung.error
    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Dafür benötigst du Administrator-Rechte.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Ein Fehler ist aufgetreten: {error}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelsCog(bot))
