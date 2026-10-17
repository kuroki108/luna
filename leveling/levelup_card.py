from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .rankcard import circle_avatar, fit_text, font_for_cap_height, to_png

TEMPLATE_PATH = Path(__file__).parent / "assets" / "levelup_template.png"

# --- Layout (Pixel, gemessen an der Vorlage 2169 × 725) ----------------------
AVATAR_CENTER = (323.0, 326.5)
AVATAR_RADIUS = 182  # weiße Innenfläche des Silberrings

TEXT_CENTER_X = 1083.5  # Mitte unter "new chapter" bzw. Mitte des Namensschilds

# (Grundlinie y, Versalhöhe in px, max. Breite) – exakt wie im Entwurf
NAME_STYLE = (383, 36, 700)
ROLE_STYLE = (528, 28, 580)  # Innenraum des Schilds: x 762–1404
ROLE_TRACKING = 0.95         # Buchstabenabstand im Schild, relativ zur Versalhöhe

COLOR_TEXT = (70, 64, 70)


@dataclass(slots=True)
class LevelupCardData:
    username: str
    role_name: str
    avatar_bytes: bytes | None = None  # None -> weißer Platzhalter bleibt


@lru_cache(maxsize=1)
def template() -> Image.Image:
    return Image.open(TEMPLATE_PATH).convert("RGBA")


@lru_cache(maxsize=4096)
def _has_glyph(font: ImageFont.FreeTypeFont, char: str) -> bool:
    """False, wenn die Schrift das Zeichen nur als leeres Kästchen zeichnen würde (z. B. Emojis)."""
    if char.isspace():
        return True
    notdef = font.getmask("\U0010fffd")
    mask = font.getmask(char)
    return mask.size != notdef.size or bytes(mask) != bytes(notdef)


def printable(text: str, font: ImageFont.FreeTypeFont) -> str:
    """Entfernt Zeichen, die die Schrift nicht kennt, und überzählige Leerzeichen."""
    return " ".join("".join(c for c in text if _has_glyph(font, c)).split())


def _tracked_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, tracking: float) -> float:
    return sum(draw.textlength(c, font=font) for c in text) + tracking * max(len(text) - 1, 0)


def fit_tracked_text(
    draw: ImageDraw.ImageDraw, text: str, cap_height: int, max_width: float
) -> tuple[str, ImageFont.FreeTypeFont, float]:
    """Gesperrter Versaltext: bei Überlänge erst Sperrung halbieren, dann verkleinern (bis 70 %), dann kürzen."""
    text = text.upper()
    for cap in range(cap_height, int(cap_height * 0.7) - 1, -2):
        font = font_for_cap_height(cap)
        for tracking in (cap * ROLE_TRACKING, cap * ROLE_TRACKING / 2):
            if _tracked_width(draw, text, font, tracking) <= max_width:
                return text, font, tracking
    cap = int(cap_height * 0.7)
    font, tracking = font_for_cap_height(cap), cap * ROLE_TRACKING / 2
    while text and _tracked_width(draw, text + "…", font, tracking) > max_width:
        text = text[:-1]
    return text.rstrip() + "…", font, tracking


def draw_tracked_centered(
    draw: ImageDraw.ImageDraw, center_x: float, baseline: int, text: str,
    font: ImageFont.FreeTypeFont, tracking: float,
) -> None:
    x = center_x - _tracked_width(draw, text, font, tracking) / 2
    for char in text:
        draw.text((x, baseline), char, font=font, fill=COLOR_TEXT, anchor="ls")
        x += draw.textlength(char, font=font) + tracking


def render_levelup_card(data: LevelupCardData) -> io.BytesIO:
    """Erzeugt das Levelup-Bild (neue Level-Rolle) als PNG im Speicher (blockierend -> in Thread ausführen)."""
    card = template().copy()

    # 1) Avatar
    if data.avatar_bytes:
        try:
            avatar = circle_avatar(data.avatar_bytes, AVATAR_RADIUS)
            cx, cy = AVATAR_CENTER
            card.alpha_composite(avatar, (round(cx - AVATAR_RADIUS), round(cy - AVATAR_RADIUS)))
        except Exception:
            pass  # kaputtes Bild -> weißer Platzhalter bleibt stehen

    draw = ImageDraw.Draw(card)

    # 2) Name (Anker 'ms' = Mitte/Grundlinie)
    baseline, cap, max_width = NAME_STYLE
    username = printable(data.username, font_for_cap_height(cap)) or "?"
    name, name_font = fit_text(draw, username, cap, max_width)
    draw.text((TEXT_CENTER_X, baseline), name, font=name_font, fill=COLOR_TEXT, anchor="ms")

    # 3) Rollenname im Schild (gesperrt)
    baseline, cap, max_width = ROLE_STYLE
    role_name = printable(data.role_name, font_for_cap_height(cap))
    if role_name:
        role, role_font, tracking = fit_tracked_text(draw, role_name, cap, max_width)
        draw_tracked_centered(draw, TEXT_CENTER_X, baseline, role, role_font, tracking)

    return to_png(card)
