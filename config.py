import os


BOT_TOKEN: str = os.environ.get("DISCORD_TOKEN", "")

GUILD_ID: int = 1550585300974178355  # ID deines Discord-Servers

# -------------------------------------------------------
# Admin-/Staff-Rollen
# -------------------------------------------------------

# Für das Ticket-System (ticket_system/permissions.py).
ADMIN_ROLE_ID: int = 1539357870225629305

SUPPORT_STAFF_ROLE_ID: int = 1550585300974178356
APPLICATION_STAFF_ROLE_ID: int = 1550585300974178356
# -------------------------------------------------------
# Ticket-System
# -------------------------------------------------------

SUPPORT_CATEGORY_ID: int = 1550585302194716702       # Kategorie für Support-Tickets
REPORT_CATEGORY_ID: int = 1550585302194716707         # Kategorie für Report-Tickets
ADMIN_CATEGORY_ID: int = 1550585302509424732         # Kategorie für Admin-Tickets
APPLICATION_CATEGORY_ID: int = 1550585302509424736   # Kategorie für Bewerbungs-Tickets


TRANSCRIPT_LOG_CHANNEL_ID: int = 1552772622436012196

MAX_OPEN_SUPPORT_TICKETS_PER_USER: int = 3
MAX_OPEN_APPLICATION_TICKETS_PER_USER: int = 1

# Präfix für automatisch generierte Kanalnamen
SUPPORT_CHANNEL_PREFIX: str = "support"
REPORT_CHANNEL_PREFIX: str = "report"
ADMIN_CHANNEL_PREFIX: str = "admin"
APPLICATION_CHANNEL_PREFIX: str = "bewerbung"

# Emojis für Panel-Buttons (frei anpassbar)
EMOJI_OPEN_TICKET = "🎫"
EMOJI_REPORT = "🚨"
EMOJI_ADMIN = "🛡️"
EMOJI_DELETE = "🗑️"
EMOJI_ADD_USER = "➕"
EMOJI_HELPER = "🧑‍💻"

# Serverfarbe für Embeds (Hex als int, z. B. 0x5865F2)
EMBED_COLOR: int = 0xFFFFFF

