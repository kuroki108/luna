"""Design der Stats-Karten: Farben, Deckkraft, Texte, Asset-Pfade.

Die Einstellungen (Tracking, Zeiträume, Cooldown, Zeitzone, DB-Pfad) stehen in config.py
im Abschnitt STATS.
"""
from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
#  Dateien
# --------------------------------------------------------------------------- #

MODULE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = MODULE_DIR / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
BACKGROUND_PATH = ASSETS_DIR / "background.webp"   # fehlt die Datei, wird ein heller Verlauf genutzt

# --------------------------------------------------------------------------- #
#  Farben
# --------------------------------------------------------------------------- #

COLORS = {
    "text": (59, 65, 80),          # Schiefergrau
    "muted": (128, 134, 150),      # Silbergrau
    "gold": (176, 140, 82),        # Champagner-Gold (Akzent)
    "gold_soft": (201, 169, 110),
    "silver": (160, 166, 180),
    "bronze": (184, 132, 112),     # Rosé-Bronze für Platz 3
    "line": (217, 220, 227),       # Haarlinien
    "white": (255, 255, 255),
}

# Deckkraft (0-255) der Milchglas-Flächen
PANEL_ALPHA = 150
CHIP_ALPHA = 175
BACKGROUND_WASH_ALPHA = 70   # weißer Schleier über dem gesamten Hintergrund

# --------------------------------------------------------------------------- #
#  Texte
# --------------------------------------------------------------------------- #

LABELS = {
    "created": "Erstellt am",
    "joined": "Beigetreten am",
    "members": "Mitglieder",
    "ranks": "Server-Ränge",
    "rank_messages": "Nachrichten",
    "rank_voice": "Voice",
    "messages": "Nachrichten",
    "voice": "Voice-Aktivität",
    "unit_messages": "Nachr.",
    "unit_messages_long": "Nachrichten",
    "unit_hours": "Std.",
    "unit_hours_long": "Stunden Voice",
    "overview": "Server-Übersicht",
    "lookback": "Zeitraum",
    "top_messages": "Top Nachrichten",
    "top_voice": "Top Voice",
    "no_data": "Noch keine Daten",
    "footer": "Zeitraum: letzte {days} Tage  ·  Zeitzone: {tz}",
    "stand": "Stand {date}",
    "day_suffix": "d",
    "unknown_user": "Unbekannt",
    # Bot-Antworten
    "err_member": "Diesen User konnte ich auf dem Server nicht finden.",
    "err_cooldown": "Kurz warten – noch {sec:.0f} s.",
    "err_dm": "Das geht nur auf einem Server.",
    "err_guild": "Stats sind auf diesem Server nicht aktiv.",
    "err_generic": "Da ist etwas schiefgelaufen. Details stehen im Bot-Log.",
}

MONTHS = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni",
          "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]
