from __future__ import annotations

import discord
from discord.ext import commands

from ticket_system import embed_builder
from ticket_system.views import ApplicationPanelView, JailPanelView, SupportPanelView, UnbanPanelView


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

    @commands.command(name="setup-ban")
    @commands.has_permissions(administrator=True)
    async def setup_ban(self, ctx: commands.Context) -> None:
        await ctx.channel.send(
            embed=embed_builder.unban_panel(),
            file=embed_builder.support_panel_file(),
            view=UnbanPanelView(),
        )

    @commands.command(name="setup-jail")
    @commands.has_permissions(administrator=True)
    async def setup_jail(self, ctx: commands.Context) -> None:
        await ctx.channel.send(
            embed=embed_builder.jail_panel(),
            file=embed_builder.support_panel_file(),
            view=JailPanelView(),
        )

    @commands.command(name="setup-bewerbung")
    @commands.has_permissions(administrator=True)
    async def setup_bewerbung(self, ctx: commands.Context) -> None:
        # 1. Begrüßungs-Embed
        await ctx.channel.send(
            embed=embed_builder.application_panel(ctx),
            file=embed_builder.support_panel_file(),
        )
        # 2. Anforderungen-Embed, darunter die Bewerben-Buttons aller Rollen
        await ctx.channel.send(
            embed=embed_builder.application_panel_Anforderungen(ctx),
            file=embed_builder.banner_file(),
            view=ApplicationPanelView(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelsCog(bot))
