from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config as cfg
from .formatting import format_number

ASSETS = Path(__file__).parent / "assets"
TEMPLATE_PATH = ASSETS / "rankcard_template.png"
FONT_DIR = ASSETS / "fonts"

# Schrift: erst CARD_FONT aus config.py, dann eigene Datei in assets/fonts,
# dann System-Schriften (Windows: Georgia/Times, Linux: Liberation/DejaVu).
FONT_CANDIDATES = [
    *([cfg.CARD_FONT] if cfg.CARD_FONT else []),
    *sorted(FONT_DIR.glob("*.ttf")),
    *sorted(FONT_DIR.glob("*.otf")),
    "georgia.ttf",
    "times.ttf",
    "LiberationSerif-Regular.ttf",
    "DejaVuSerif.ttf",
]

# --- Layout (Pixel, gemessen an der Vorlage) --------------------------------
AVATAR_CENTER = (323.5, 328.0)
AVATAR_RADIUS = 183  # weiße Innenfläche des Silberrings

TEXT_LEFT = 593
TEXT_RIGHT = 2044
NAME_MAX_WIDTH = 1110  # absolute Obergrenze (Ende des Burg-Bereichs)
NAME_LEVEL_GAP = 60    # Mindestabstand zwischen Name und "LEVEL xx"

# (Grundlinie y, Versalhöhe in px) – exakt wie im Entwurf
NAME_STYLE = (205, 66)
LEVEL_STYLE = (189, 50)
RANK_STYLE = (250, 32)
XP_STYLE = (484, 36)

BAR_BOX = (593, 363, 2046, 412)  # Innenraum der Glasröhre (x0, y0, x1, y1)

COLOR_MAIN = (58, 58, 60)
COLOR_SUB = (88, 88, 92)

SUPERSAMPLE = 4  # Kantenglättung für Kreis und Balken


@dataclass(slots=True)
class RankCardData:
    username: str
    level: int
    rank: int
    xp_current: int   # XP innerhalb des aktuellen Levels
    xp_needed: int    # XP, die für das nächste Level nötig sind
    xp_total: int
    avatar_bytes: bytes | None = None  # None -> weißer Platzhalter bleibt


# --- Bausteine (auch für das Leaderboard) -----------------------------------
@lru_cache(maxsize=1)
def _font_source() -> str:
    for candidate in FONT_CANDIDATES:
        try:
            ImageFont.truetype(str(candidate), 20)
            return str(candidate)
        except OSError:
            continue
    raise RuntimeError(
        "Keine Schrift gefunden. Lege eine .ttf in modules/assets/fonts/ ab "
        "(z. B. EBGaramond-Medium.ttf) oder setze CARD_FONT in config.py."
    )


@lru_cache(maxsize=64)
def font_for_cap_height(cap_height: int) -> ImageFont.FreeTypeFont:
    """Wählt die Schriftgröße so, dass ein 'H' genau cap_height Pixel hoch ist.

    Dadurch passt das Layout unabhängig davon, welche Schrift du einsetzt.
    """
    src = _font_source()
    size = cap_height
    for _ in range(40):
        font = ImageFont.truetype(src, size)
        top, bottom = font.getbbox("H")[1], font.getbbox("H")[3]
        if bottom - top >= cap_height:
            return font
        size += 1
    return font


def fit_text(
    draw: ImageDraw.ImageDraw, text: str, cap_height: int, max_width: float
) -> tuple[str, ImageFont.FreeTypeFont]:
    """Text in Versalien; bei Überlänge erst verkleinern (bis 70 %), dann kürzen."""
    text = text.upper()
    for cap in range(cap_height, int(cap_height * 0.7) - 1, -2):
        font = font_for_cap_height(cap)
        if draw.textlength(text, font=font) <= max_width:
            return text, font
    font = font_for_cap_height(int(cap_height * 0.7))
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…", font


def circle_avatar(avatar_bytes: bytes, radius: int) -> Image.Image:
    size = radius * 2
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    # mittig quadratisch zuschneiden, falls das Bild nicht 1:1 ist
    w, h = avatar.size
    side = min(w, h)
    avatar = avatar.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)

    big = size * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    avatar.putalpha(mask)
    return avatar


def progress_of(xp_current: int, xp_needed: int) -> float:
    return 0.0 if xp_needed <= 0 else min(max(xp_current / xp_needed, 0.0), 1.0)


def glass_bar(full_width: int, height: int, progress: float) -> Image.Image | None:
    """Silberner Glas-Füllbalken (nur die Füllung, ohne Röhre) – None, wenn nichts zu zeichnen ist."""
    width = round(full_width * progress)
    if width <= 0:
        return None
    if width < height:
        return None  # zu kurz für eine runde Kappe – wie im Entwurf bleibt die Röhre leer

    s = SUPERSAMPLE
    w, h = width * s, height * s
    radius = h // 2

    # vertikaler Silberverlauf: hell oben, dunkler Kern, Reflex unten
    stops = [
        (0.00, (252, 252, 254)),
        (0.22, (236, 237, 241)),
        (0.50, (196, 198, 206)),
        (0.62, (176, 178, 188)),
        (0.85, (214, 215, 222)),
        (1.00, (240, 240, 244)),
    ]
    gradient = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / (h - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0)
                gradient.putpixel((0, y), (*(round(a + (b - a) * f) for a, b in zip(c0, c1)), 255))
                break
    fill = gradient.resize((w, h))

    draw = ImageDraw.Draw(fill)
    # Glanzlinie oben
    draw.rounded_rectangle(
        (radius // 2, int(h * 0.12), w - radius // 2, int(h * 0.24)),
        radius=int(h * 0.06), fill=(255, 255, 255, 170),
    )

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    fill.putalpha(mask)

    # feine dunkle Kontur für den Chrom-Look
    outline = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(outline).rounded_rectangle(
        (0, 0, w - 1, h - 1), radius=radius, outline=(130, 132, 142, 200), width=2 * s
    )
    fill = Image.alpha_composite(fill, outline)
    return fill.resize((width, height), Image.Resampling.LANCZOS)


def to_png(image: Image.Image) -> io.BytesIO:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# --- Rangkarte --------------------------------------------------------------
@lru_cache(maxsize=1)
def template() -> Image.Image:
    return Image.open(TEMPLATE_PATH).convert("RGBA")


def render_rank_card(data: RankCardData) -> io.BytesIO:
    """Erzeugt die Rangkarte als PNG im Speicher (blockierend -> in Thread ausführen)."""
    card = template().copy()

    # 1) Avatar
    if data.avatar_bytes:
        try:
            avatar = circle_avatar(data.avatar_bytes, AVATAR_RADIUS)
            cx, cy = AVATAR_CENTER
            card.alpha_composite(avatar, (round(cx - AVATAR_RADIUS), round(cy - AVATAR_RADIUS)))
        except Exception:
            pass  # kaputtes Bild -> weißer Platzhalter bleibt stehen

    # 2) Fortschrittsbalken
    x0, y0, x1, y1 = BAR_BOX
    fill = glass_bar(x1 - x0, y1 - y0, progress_of(data.xp_current, data.xp_needed))
    if fill is not None:
        card.alpha_composite(fill, (x0, y0))

    # 3) Texte (Anker 'ls' = links/Grundlinie, 'rs' = rechts/Grundlinie)
    draw = ImageDraw.Draw(card)
    level_text = f"LEVEL {data.level}"
    level_font = font_for_cap_height(LEVEL_STYLE[1])
    level_left = TEXT_RIGHT - draw.textlength(level_text, font=level_font)
    name_max = min(NAME_MAX_WIDTH, int(level_left - NAME_LEVEL_GAP - TEXT_LEFT))

    name, name_font = fit_text(draw, data.username, NAME_STYLE[1], name_max)
    draw.text((TEXT_LEFT, NAME_STYLE[0]), name, font=name_font, fill=COLOR_MAIN, anchor="ls")
    draw.text((TEXT_RIGHT, LEVEL_STYLE[0]), level_text, font=level_font, fill=COLOR_MAIN, anchor="rs")
    draw.text((TEXT_RIGHT, RANK_STYLE[0]), f"RANG #{data.rank}",
              font=font_for_cap_height(RANK_STYLE[1]), fill=COLOR_SUB, anchor="rs")

    xp_font = font_for_cap_height(XP_STYLE[1])
    draw.text((TEXT_LEFT, XP_STYLE[0]),
              f"{format_number(data.xp_current)} / {format_number(data.xp_needed)} XP",
              font=xp_font, fill=COLOR_SUB, anchor="ls")
    draw.text((TEXT_RIGHT, XP_STYLE[0]), f"Gesamt: {format_number(data.xp_total)} XP",
              font=xp_font, fill=COLOR_SUB, anchor="rs")

    return to_png(card)
