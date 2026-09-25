from __future__ import annotations

import logging

import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  

import config
from ticket_system.panels import PanelsCog
from ticket_system import permissions, ticket_manager
from ticket_system.storage import store as ticket_store
from ticket_system.views import ConfirmDeleteView, all_persistent_views

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("luna")

intents = discord.Intents.default()
intents.members = True 
intents.message_content = True 
intents.voice_states = True 


class LunaBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=",", intents=intents)
    async def setup_hook(self) -> None:
        await ticket_store.connect()
        log.info("SQLite-Datenbank verbunden.")

        for view in all_persistent_views():
            self.add_view(view)

        await self.add_cog(PanelsCog(self))

        if config.GUILD_ID:
            guild_obj = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            log.info("Slash-Commands für Guild %s synchronisiert.", config.GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Slash-Commands global synchronisiert (kann bis zu 1h dauern, bis sie überall sichtbar sind).")

    async def close(self) -> None:
        await ticket_store.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Eingeloggt als %s (ID: %s)", self.user, self.user.id)
        log.info("Bereit! Bot ist aktiv.")
        print(f"\n{'─'*45}")
        print(f"  ✅  Eingeloggt als : {self.user} ({self.user.id})")
        print(f"  📡  Server        : {len(self.guilds)}")
        print(f"{'─'*45}\n")

    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.MissingAnyRole, commands.MissingPermissions, commands.MissingRole)):
            await ctx.send("Du hast keine Berechtigung diesen Befehl auszuführen.", delete_after=3)
        else:
            raise error


bot = LunaBot()


@bot.command(name="adduser")
@commands.guild_only()
async def adduser_command(ctx: commands.Context, member: discord.Member) -> None:
    """Fügt einen Nutzer zum Ticket-Kanal hinzu."""
    ticket = await ticket_store.get_ticket(ctx.channel.id)
    if not ticket:
        await ctx.send("❌ Dies ist kein aktiver Ticket-Kanal.", delete_after=5)
        return
    if not permissions.is_staff_for_ticket_type(ctx.author, ticket.type):
        await ctx.send("❌ Nur Teammitglieder können Nutzer hinzufügen.", delete_after=5)
        return
    if not await ticket_manager.add_user(ctx.channel, member, ticket):
        await ctx.send("⚠️ Der Nutzer ist bereits im Ticket oder ist der Ersteller.", delete_after=5)
        return
    await ctx.send(f"✅ {member.mention} wurde von {ctx.author.mention} zum Ticket hinzugefügt.")


@bot.command(name="delete")
@commands.guild_only()
async def delete_command(ctx: commands.Context) -> None:
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


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit(
            "Kein Bot-Token gefunden. Setze die Umgebungsvariable DISCORD_TOKEN "
            "(siehe .env.example) bevor du den Bot startest."
        )

    bot.run(config.BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
