"""Text mit Schrift-Fallback für die Karten (Rang, Leaderboard, Levelup).

EB Garamond kennt keine Emojis, Symbole (⋆ ☾ ✧ …), Zierbuchstaben (𝓡𝓮𝓲) oder
japanische/chinesische/koreanische Zeichen. Pillow zeichnet solche Zeichen als
leere Kästchen. Hier wird deshalb jedes Zeichen einzeln geprüft:

1. Kennt die Hauptschrift das Zeichen -> Hauptschrift.
2. Zierbuchstaben (𝓡, ᴿ, Ｒ …) werden per Unicode-NFKC auf normale Buchstaben
   zurückgeführt, damit sie im Stil der Karte erscheinen (siehe clean_text).
3. Sonst die erste Fallback-Schrift, die das Zeichen hat
   (assets/fonts/fallback/, danach System-Schriften für CJK).
4. Kennt keine Schrift das Zeichen, wird es weggelassen – nie ein Kästchen.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import ImageDraw, ImageFont

FALLBACK_DIR = Path(__file__).parent / "assets" / "fonts" / "fallback"

# Nach den mitgelieferten Noto-Schriften: System-Schriften, vor allem für CJK
# (Windows: Segoe/Yu Gothic/Malgun/SimSun, Linux: Noto CJK/DejaVu).
SYSTEM_FALLBACKS = [
    "seguisym.ttf",
    "YuGothM.ttc",
    "msgothic.ttc",
    "malgun.ttf",
    "simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "NotoSansCJK-Regular.ttc",
    "DejaVuSans.ttf",
]

_PROBE_SIZE = 48


@lru_cache(maxsize=1)
def _fallback_sources() -> tuple[str, ...]:
    candidates = [*sorted(FALLBACK_DIR.glob("*.tt[fc]")), *sorted(FALLBACK_DIR.glob("*.otf")), *SYSTEM_FALLBACKS]
    sources = []
    for candidate in candidates:
        try:
            ImageFont.truetype(str(candidate), _PROBE_SIZE)
        except OSError:
            continue
        sources.append(str(candidate))
    return tuple(sources)


@lru_cache(maxsize=32)
def _probe_font(src: str) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(src, _PROBE_SIZE)


@lru_cache(maxsize=16384)
def has_glyph(src: str, char: str) -> bool:
    """False, wenn die Schrift das Zeichen nur als Kästchen (.notdef) zeichnen würde."""
    if char == " ":
        return True
    font = _probe_font(src)
    notdef = font.getmask("\U0010fffd")
    mask = font.getmask(char)
    return mask.size != notdef.size or bytes(mask) != bytes(notdef)


def _is_invisible(char: str) -> bool:
    """Steuer-/Formatzeichen und Variantenselektoren (z. B. U+FE0F hinter Emojis, ZWJ)."""
    if unicodedata.category(char) in ("Cc", "Cf", "Co", "Cs", "Cn"):
        return True
    code = ord(char)
    return 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF


def _cap_height(font: ImageFont.FreeTypeFont) -> int:
    top, bottom = font.getbbox("H")[1::2]
    return bottom - top


@lru_cache(maxsize=256)
def _fallback_font(src: str, primary_src: str, size: int) -> ImageFont.FreeTypeFont:
    """Fallback-Schrift in der Größe, deren Versalhöhe zur Hauptschrift passt."""
    font = ImageFont.truetype(src, size)
    if has_glyph(src, "H"):
        primary_cap = _cap_height(ImageFont.truetype(primary_src, size))
        own_cap = _cap_height(font)
        if primary_cap > 0 and own_cap > 0:
            scaled = round(size * min(max(primary_cap / own_cap, 0.7), 1.4))
            if scaled != size:
                font = ImageFont.truetype(src, scaled)
    return font


def clean_text(text: str, font: ImageFont.FreeTypeFont) -> str:
    """Entfernt unsichtbare Zeichen, ersetzt Zierbuchstaben (𝓡 -> R) und fasst Leerraum zusammen."""
    out = []
    for char in text:
        if char.isspace():
            out.append(" ")
            continue
        if _is_invisible(char):
            continue
        if not has_glyph(font.path, char):
            normalized = unicodedata.normalize("NFKC", char)
            if normalized != char and normalized.strip() and all(has_glyph(font.path, c) for c in normalized):
                char = normalized
        out.append(char)
    return " ".join("".join(out).split())


def _runs(text: str, font: ImageFont.FreeTypeFont) -> list[tuple[str, ImageFont.FreeTypeFont]]:
    """Zerlegt den Text in Abschnitte, die jeweils mit einer Schrift gezeichnet werden."""
    runs: list[tuple[str, ImageFont.FreeTypeFont]] = []
    current = font
    for char in text:
        if char.isspace():
            chosen = current
            char = " "
        elif _is_invisible(char):
            continue
        elif has_glyph(font.path, char):
            chosen = font
        elif unicodedata.category(char) == "Mn" and has_glyph(current.path, char):
            chosen = current  # Akzent/Kombinationszeichen bleibt beim Grundbuchstaben
        else:
            src = next((s for s in _fallback_sources() if has_glyph(s, char)), None)
            if src is None:
                continue  # keine Schrift kennt das Zeichen -> weglassen statt Kästchen
            chosen = _fallback_font(src, font.path, round(font.size))
        if runs and runs[-1][1] is chosen:
            runs[-1] = (runs[-1][0] + char, chosen)
        else:
            runs.append((char, chosen))
        current = chosen
    return runs


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    return sum(draw.textlength(part, font=f) for part, f in _runs(text, font))


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, ...],
    anchor: str = "ls",
) -> None:
    """Wie draw.text, aber mit Schrift-Fallback. anchor: 'ls', 'ms' oder 'rs' (Grundlinie)."""
    runs = _runs(text, font)
    x, baseline = xy
    width = sum(draw.textlength(part, font=f) for part, f in runs)
    if anchor[0] == "m":
        x -= width / 2
    elif anchor[0] == "r":
        x -= width
    for part, f in runs:
        draw.text((x, baseline), part, font=f, fill=fill, anchor="ls")
        x += draw.textlength(part, font=f)
