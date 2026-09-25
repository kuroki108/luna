from __future__ import annotations

import discord

import config
from ticket_system import embed_builder, permissions
from ticket_system import ticket_manager
from ticket_system.storage import store
from ticket_system.ticket_manager import TicketLimitReached
from ticket_system.modals import (
    SupporterApplicationModal,
)


class SupportPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _open(self, interaction: discord.Interaction, ticket_type: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            channel = await ticket_manager.create_ticket(
                guild=interaction.guild, member=interaction.user, ticket_type=ticket_type
            )
        except TicketLimitReached:
            await interaction.followup.send(
                "❌ Du hast bereits zu viele offene Tickets. Bitte warte, bis diese bearbeitet wurden.",
                ephemeral=True,
            )
            return

        embed = embed_builder.ticket_welcome(interaction.user, ticket_type)
        await channel.send(content=interaction.user.mention, embed=embed, view=TicketControlView())
        await channel.send(embed=embed_builder.ticket_info(ticket_type))
        await interaction.followup.send(f"✅ Dein Ticket wurde erstellt: {channel.mention}", ephemeral=True)

    @discord.ui.button(
        label="Support",
        emoji=config.EMOJI_OPEN_TICKET,
        style=discord.ButtonStyle.secondary,
        custom_id="za_open_support",
    )
    async def open_support(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._open(interaction, "support")

    @discord.ui.button(
        label="Report",
        emoji=config.EMOJI_REPORT,
        style=discord.ButtonStyle.secondary,
        custom_id="za_open_report",
    )
    async def open_report(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._open(interaction, "support_report")

    @discord.ui.button(
        label="Admin",
        emoji=config.EMOJI_ADMIN,
        style=discord.ButtonStyle.secondary,
        custom_id="za_open_admin",
    )
    async def open_admin(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._open(interaction, "support_admin")


class ApplicationPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Hier bewerben!",
        emoji=config.EMOJI_HELPER,
        style=discord.ButtonStyle.secondary,
        custom_id="za_open_app_supporter",
        row=0,
    )
    async def apply_supporter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SupporterApplicationModal())


# ---------------------------------------------------------------------------
# Nutzerauswahl für Add User (kurzlebige, ephemere Hilfs-Views)
# ---------------------------------------------------------------------------
class _AddUserSelectView(discord.ui.View):
    def __init__(self, ticket_channel_id: int) -> None:
        super().__init__(timeout=60)
        self.ticket_channel_id = ticket_channel_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Nutzer auswählen...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
        target = select.values[0]
        ticket = await store.get_ticket(self.ticket_channel_id)
        if not ticket:
            await interaction.response.edit_message(content="❌ Ticket wurde nicht gefunden.", view=None)
            return
        ok = await ticket_manager.add_user(interaction.channel, target, ticket)
        if not ok:
            await interaction.response.edit_message(
                content=f"⚠️ {target.mention} ist bereits im Ticket oder ist der Ersteller.", view=None
            )
            return
        await interaction.response.edit_message(content=f"✅ {target.mention} wurde hinzugefügt.", view=None)
        await interaction.channel.send(f"➕ {target.mention} wurde von {interaction.user.mention} zum Ticket hinzugefügt.")


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, ticket_channel_id: int, requester_id: int | None = None) -> None:
        super().__init__(timeout=30)
        self.ticket_channel_id = ticket_channel_id
        self.requester_id = requester_id

    @discord.ui.button(label="Ja, endgültig löschen", style=discord.ButtonStyle.secondary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.requester_id is not None and interaction.user.id != self.requester_id:
            await interaction.response.send_message("❌ Nur der Nutzer, der die Löschung angefordert hat, kann bestätigen.", ephemeral=True)
            return
        ticket = await store.get_ticket(self.ticket_channel_id)
        if not ticket:
            await interaction.response.edit_message(content="❌ Ticket wurde nicht gefunden.", view=None)
            return
        await interaction.response.edit_message(content="🗑️ Ticket wird gelöscht...", view=None)
        await ticket_manager.delete_ticket(interaction.channel, interaction.user, ticket)

    @discord.ui.button(label="Abbrechen", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.requester_id is not None and interaction.user.id != self.requester_id:
            await interaction.response.send_message("❌ Nur der Nutzer, der die Löschung angefordert hat, kann abbrechen.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Abgebrochen.", view=None)


# ---------------------------------------------------------------------------
# Ticket-Steuerung: wird in jedes Ticket gepostet
# ---------------------------------------------------------------------------
class TicketControlView(discord.ui.View):
    def __init__(self, show_add_user: bool = True) -> None:
        super().__init__(timeout=None)
        # Bei Bewerbungen gibt es keinen "Add User"-Button.
        if not show_add_user:
            self.remove_item(self.add_user)

    async def _get_ticket_or_warn(self, interaction: discord.Interaction):
        ticket = await store.get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Dies ist kein aktiver Ticket-Kanal.", ephemeral=True)
            return None
        return ticket

    @discord.ui.button(label="Add User", emoji=config.EMOJI_ADD_USER, style=discord.ButtonStyle.secondary, custom_id="za_adduser")
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self._get_ticket_or_warn(interaction)
        if not ticket:
            return
        if not permissions.is_staff_for_ticket_type(interaction.user, ticket.type):
            await interaction.response.send_message("❌ Nur Teammitglieder können Nutzer hinzufügen.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Wähle den Nutzer aus, der hinzugefügt werden soll:", view=_AddUserSelectView(interaction.channel.id), ephemeral=True
        )

    @discord.ui.button(label="Close", emoji=config.EMOJI_DELETE, style=discord.ButtonStyle.secondary, custom_id="za_delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self._get_ticket_or_warn(interaction)
        if not ticket:
            return
        if not permissions.is_staff_for_ticket_type(interaction.user, ticket.type):
            await interaction.response.send_message("❌ Nur Teammitglieder können Tickets löschen.", ephemeral=True)
            return
        await interaction.response.send_message(
            "⚠️ Bist du sicher? Das Ticket wird gelöscht; das Transcript bleibt im Log-Kanal erhalten.",
            view=ConfirmDeleteView(interaction.channel.id, interaction.user.id),
            ephemeral=True,
        )


def all_persistent_views() -> list[discord.ui.View]:
    """Wird beim Bot-Start verwendet, um alle persistenten Views zu registrieren."""
    return [SupportPanelView(), ApplicationPanelView(), TicketControlView()]
