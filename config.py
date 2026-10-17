import os
from pathlib import Path


BOT_TOKEN: str = os.environ.get("DISCORD_TOKEN", "")

GUILD_ID: int = 1509590685081272401  # ID deines Discord-Servers (gilt für Tickets, Slash-Commands und Level-System)

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


# =======================================================
# LEVEL-SYSTEM (leveling/)
# =======================================================

# ======================================================================
# Datenbank & Logging
# ======================================================================

# Standard: <Projekt-Root>/data/leveling.sqlite3
LEVEL_DB_PATH = Path(__file__).resolve().parent / "data" / "leveling.sqlite3"
LEVEL_LOGGER_NAME = "leveling"

# ======================================================================
# Command-Namen
# Anpassen, falls ein Name schon von einem anderen Cog belegt ist –
# sonst schlägt das Laden mit `CommandRegistrationError` fehl.
# ======================================================================

# Prefix-Commands (es gibt keine Slash-Commands)
COMMAND_RANK = "rank"
COMMAND_LEADERBOARD = "leaderboard"

COMMAND_XP = "xp"
COMMAND_XP_BOOST = "xprise"  # .xprise <prozent> <dauer> [text|voice] – zeitlich begrenzter XP-Boost (Admin)

COMMAND_LEVEL_CONFIG = "level-config"  # nur noch `show` (Anzeige der Einstellungen)

# ======================================================================
# Darstellung
# ======================================================================

LEVEL_EMBED_COLOR = 0x00E5FF    # für das Admin-Embed (level-config show)

# ======================================================================
# Bilder: Rangkarte & Leaderboard
# ======================================================================

# Pfad zu einer .ttf/.otf-Schrift. None = erste Schrift in modules/assets/fonts/,
# sonst Georgia/Times (Windows) bzw. Liberation/DejaVu Serif (Linux).
# Passend zum Entwurf: EB Garamond (Google Fonts, OFL), z. B. EBGaramond-Medium.ttf.
CARD_FONT: str | None = None
CARD_COOLDOWN_SECONDS = 5  # Pro Nutzer zwischen `rank`/`leaderboard`-Aufrufen (Rendern kostet CPU; 0 = aus)
LEADERBOARD_SIZE = 10      # So viele Plätze zeigt das Leaderboard (1–25); die Top 3 stehen auf dem Podium

# ======================================================================
# Text-XP
# ======================================================================

XP_MIN = 15            # XP pro Nachricht: Zufallswert von XP_MIN bis XP_MAX (1 ≤ XP_MIN ≤ XP_MAX)
XP_MAX = 25
COOLDOWN_SECONDS = 60  # So lange gibt es nach einer XP-Nachricht keine neuen Text-XP (0 = kein Cooldown)

# ======================================================================
# Kanäle ohne XP
# ======================================================================


NO_XP_CHANNELS: list[int] = [1509590687010783239, 1528773508899799060, 1518300447486513283, 1509590687010783233, 1546944555038023721, 1509590685689446468, 1509590685844770957, 1509590685844770964, 1509590686012539021, 1509590686704603266, 1509590686012539025, 1532084834451853452, 1529675022690553957]

# ======================================================================
# Levelup
# Neue Level-Rolle erreicht: Levelup-Bild (Name + Rollenname), danach eine Nachricht nur mit dem Ping.
# Sonst: nur die Rangkarte – ohne Text und ohne Ping.
# ======================================================================

# Kanal-ID für Levelup-Karten. None = Kanal, in dem das Levelup passiert.
# (Ein fester Kanal gilt nur auf seinem Server – auf anderen Servern wird der Levelup-Kanal genutzt.)
LEVELUP_CHANNEL_ID: int | None = 1550166157183684719

# ======================================================================
# Level-Rollen
# ======================================================================

# Level → Rollen-ID. Jede Rolle darf nur einmal vorkommen.
# Vergeben wird beim Levelup, beim Wiederbeitritt auf den Server und beim Bot-Start (gleicht alle Mitglieder ab).
# Die Bot-Rolle muss in den Server-Einstellungen ÜBER diesen Rollen stehen und der Bot braucht "Rollen verwalten".
# Level 0 = Mitglieder ohne XP (z. B. eine Neuling-Rolle direkt beim Beitritt).
# Wird eine Rolle hier gelöscht, behalten Mitglieder sie – dann in Discord manuell entfernen.
# Beispiel: LEVEL_ROLES = {1: 123456789012345678, 10: 234567890123456789, 25: 345678901234567890}
LEVEL_ROLES: dict[int, int] = {1: 1509590685114961991, 5: 1509590685114961992, 10: 1509590685114961993, 15:1509590685114961994, 20:1509590685114961995, 25:1509590685114961996, 30: 1509590685114961997, 40: 1509590685114961998, 50: 1509590685114961999, 60: 1530182441581412485, 70:1530182796805668945, 80: 1530182900354519191, 90: 1530182963231199293, 100: 1530183436185243678}

# True = alle erreichten Level-Rollen behalten, False = nur die höchste.
STACK_ROLES = False

# ======================================================================
# Level-Kurve
# Level 1 gibt es mit der ersten XP (erste Nachricht bzw. erste Voice-Minute).
# XP von Level n auf n+1 (ab n = 1) = A·(n-1)² + B·(n-1) + C  (C > 0, A und B ≥ 0)
# Sobald eine Stufe dadurch um mehr als MAX_GROWTH XP teurer würde als die vorige, wird sie
# ab dort nur noch um MAX_GROWTH XP pro Level teurer (linear statt quadratisch). None = keine Deckelung.
# Achtung: Eine Änderung verschiebt die Level aller Mitglieder (ihre Gesamt-XP bleibt gleich).
# ======================================================================

LEVEL_CURVE_A = 5
LEVEL_CURVE_B = 50
LEVEL_CURVE_C = 100
# 115 = Kurve bis Level 8 wie gehabt, Level 100 nach ~1 Jahr bei täglich 90 Min. Voice + 30 Nachrichten
LEVEL_CURVE_MAX_GROWTH: int | None = 115

# ======================================================================
# Voice-XP
# ======================================================================

VOICE_XP_ENABLED = True
VOICE_XP_PER_MIN = 10
VOICE_DAILY_CAP_MINUTES = 90   # Max. Minuten mit Voice-XP pro Tag (0 = kein Limit, Reset 00:00 UTC)
VOICE_REQUIRE_UNMUTED = True  # True = stummgeschaltete Nutzer bekommen keine Voice-XP

VOICE_MIN_MEMBERS = 2
