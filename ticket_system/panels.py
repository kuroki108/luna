from __future__ import annotations

import discord
from discord.ext import commands

from ticket_system import embed_builder
from ticket_system.views import SupportPanelView, ApplicationPanelView


class PanelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="setup-support")
    @commands.has_permissions(administrator=True)
    async def setup_support(self, ctx: commands.Context) -> None:
        embed = embed_builder.support_panel()
        await ctx.channel.send(
            embed=embed,
            file=embed_builder.support_panel_file(),
            view=SupportPanelView(),
        )




    @commands.command(name="setup-bewerbung")
    @commands.has_permissions(administrator=True)
    async def setup_bewerbung(self, ctx: commands.Context) -> None:
        embed = embed_builder.application_panel()
        await ctx.channel.send(embed=embed, view=ApplicationPanelView())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelsCog(bot))
