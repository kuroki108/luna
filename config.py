import os


BOT_TOKEN: str = os.environ.get("DISCORD_TOKEN", "")

GUILD_ID: int = 1550585300974178355  # ID deines Discord-Servers

# -------------------------------------------------------
# Admin-/Staff-Rollen
# -------------------------------------------------------

# Für das Ticket-System (ticket_system/permissions.py).
ADMIN_ROLE_ID: int = 1527446804533215334

SUPPORT_STAFF_ROLE_ID: int = 1509590685131604067
APPLICATION_STAFF_ROLE_ID: int = 1527446804533215334
# -------------------------------------------------------
# Ticket-System
# -------------------------------------------------------

SUPPORT_CATEGORY_ID: int = 1540834808723148820       # Kategorie für Support-Tickets
REPORT_CATEGORY_ID: int = 1540834871163748384          # Kategorie für Report-Tickets
ADMIN_CATEGORY_ID: int = 1540834743350722620         # Kategorie für Admin-Tickets
APPLICATION_CATEGORY_ID: int = 1552431927620010035   # Kategorie für Bewerbungs-Tickets

# Entbannungsserver (0 = nicht gesetzt)
UNBAN_CATEGORY_ID: int = 1547387694919712809              # Kategorie für Entbannungs-Tickets
UNBAN_STAFF_ROLE_ID: int = 1547386930860396674              # Rolle, die Entbannungs-Tickets bearbeitet
UNBAN_TRANSCRIPT_LOG_CHANNEL_ID: int = 1547390291919634443  # Log-Kanal auf dem Entbannungsserver (0 = TRANSCRIPT_LOG_CHANNEL_ID)

# Jail-Support (0 = nicht gesetzt)
JAIL_CATEGORY_ID: int = 1555967931630751815                                 # Kategorie für Jail-Tickets (0 = ohne Kategorie)
JAIL_STAFF_ROLE_ID: int = SUPPORT_STAFF_ROLE_ID            # Rolle, die Jail-Tickets bearbeitet

TRANSCRIPT_LOG_CHANNEL_ID: int = 1518365223310856232

MAX_OPEN_SUPPORT_TICKETS_PER_USER: int = 3
MAX_OPEN_APPLICATION_TICKETS_PER_USER: int = 1

# Präfix für automatisch generierte Kanalnamen
SUPPORT_CHANNEL_PREFIX: str = "support"
REPORT_CHANNEL_PREFIX: str = "report"
ADMIN_CHANNEL_PREFIX: str = "admin"
APPLICATION_CHANNEL_PREFIX: str = "bewerbung"
UNBAN_CHANNEL_PREFIX: str = "entbannung"
JAIL_CHANNEL_PREFIX: str = "jail"

# Emojis für Panel-Buttons (frei anpassbar)
EMOJI_OPEN_TICKET = ":lunaRpalace:1534751812068970606"
EMOJI_REPORT = ":lunaRpalace:1534751812068970606"
EMOJI_ADMIN = ":lunaRpalace:1534751812068970606"
EMOJI_DELETE = ":lunaRpalace:1544143111335182446"
EMOJI_ADD_USER = ":lunaRpalace:1541149690760921139"
EMOJI_HELPER = ":lunaRpalace:1544143111335182446"

# Serverfarbe für Embeds (Hex als int, z. B. 0x5865F2)
EMBED_COLOR: int = 0xFFFFFF

