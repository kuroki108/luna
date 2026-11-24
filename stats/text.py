"""Text mit Schrift-Fallback zeichnen (Pillow wechselt die Schrift nicht von allein).

Jeder Text wird in Läufe zerlegt; jeder Lauf nutzt die erste Schrift der Kette, die das
Zeichen enthält. So funktionieren Namen wie "フィン ⊹ ☾ 🌙" in einem Rutsch.
"""
from __future__ import annotations

import functools
import logging
import os
import threading
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont, features

from . import design

log = logging.getLogger(__name__)

# Shaping-Engine verfügbar? (Linux/macOS meist ja, Windows-Wheels nein)
HAS_RAQM = bool(features.check("raqm"))

# Zeichen, die nur Varianten steuern und außerhalb von Emoji-Sequenzen nicht gezeichnet werden
_INVISIBLE = {0xFE0E, 0xFE0F, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}
_BITMAP_EMOJI_PPEM = 109  # CBDT-Emoji-Fonts (z. B. Noto Color Emoji unter Linux) gibt es nur in dieser Größe

_SYSTEM_SYMBOLS = [
    "C:/Windows/Fonts/seguisym.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]
_SYSTEM_CJK = [
    "C:/Windows/Fonts/YuGothM.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
_SYSTEM_EMOJI = [
    "C:/Windows/Fonts/seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf",
]


class Face:
    """Eine Schriftdatei (+ optionales Gewicht) mit bekannter Zeichenabdeckung."""

    def __init__(self, path: str | Path, weight: int | None = None, color: bool = False) -> None:
        self.path = str(path)
        self.weight = weight
        self.color = color
        with TTFont(self.path, fontNumber=0, lazy=True) as tt:
            self.cmap: set[int] = set((tt.getBestCmap() or {}).keys())
            self.bitmap = "CBDT" in tt or "sbix" in tt
            self.axes = [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in tt["fvar"].axes] if "fvar" in tt else []
        self._cache: dict[int, ImageFont.FreeTypeFont] = {}
        self._lock = threading.Lock()

    def has(self, cp: int) -> bool:
        return cp in self.cmap

    def font(self, size: int) -> ImageFont.FreeTypeFont:
        load = _BITMAP_EMOJI_PPEM if self.bitmap else size
        with self._lock:
            f = self._cache.get(load)
            if f is None:
                f = ImageFont.truetype(self.path, load)
                if self.axes:
                    values = []
                    for tag, lo, default, hi in self.axes:
                        if tag == "wght" and self.weight:
                            v = self.weight
                        elif tag == "opsz":
                            v = size / 2  # Karten werden in 2x gerendert
                        else:
                            v = default
                        values.append(max(lo, min(hi, v)))
                    f.set_variation_by_axes(values)
                self._cache[load] = f
            return f

    def scale(self, size: int) -> float:
        return size / _BITMAP_EMOJI_PPEM if self.bitmap else 1.0


def _usable_color_font(path: str) -> bool:
    """Reine COLRv1-Fonts kann FreeType/Pillow nicht farbig zeichnen -> überspringen.

    COLRv1-Tabellen mit zusätzlichen v0-Ebenen (z. B. Segoe UI Emoji) funktionieren.
    """
    try:
        with TTFont(path, fontNumber=0, lazy=True) as tt:
            if "COLR" in tt:
                # Nur den Header lesen (version, numBaseGlyphRecords) statt die ganze Tabelle zu parsen
                raw = tt.reader["COLR"][:4]
                version, num_base_glyphs = int.from_bytes(raw[:2], "big"), int.from_bytes(raw[2:4], "big")
                return version == 0 or num_base_glyphs > 0
            return "CBDT" in tt or "sbix" in tt
    except Exception:
        return False


def _is_modifier(cp: int) -> bool:
    """Hautfarben, Keycap und Tag-Zeichen – nie allein zeichnen."""
    return 0x1F3FB <= cp <= 0x1F3FF or cp == 0x20E3 or 0xE0020 <= cp <= 0xE007F


def _is_regional(cp: int) -> bool:
    return 0x1F1E6 <= cp <= 0x1F1FF


def _emoji_cluster_end(text: str, start: int) -> int:
    """Ende (exklusiv) einer Emoji-Sequenz ab `start`: Selektoren, Hautfarben, ZWJ-Ketten, Flaggen."""
    n = len(text)
    if _is_regional(ord(text[start])):
        return start + 2 if start + 1 < n and _is_regional(ord(text[start + 1])) else start + 1
    i = start + 1
    while i < n:
        cp = ord(text[i])
        if cp in (0xFE0E, 0xFE0F) or _is_modifier(cp):
            i += 1
        elif cp == 0x200D and i + 1 < n:
            i += 2  # ZWJ + nächstes Element gehören dazu
        else:
            break
    return i


def _first_existing(paths: list[str]) -> list[str]:
    return [p for p in paths if os.path.exists(p)]


class FontChain:
    def __init__(self, faces: list[Face]) -> None:
        self.faces = faces
        self.primary = faces[0]

    def face_for(self, cp: int) -> Face | None:
        for face in self.faces:
            if face.has(cp):
                return face
        return None

    def _emoji_face(self) -> Face | None:
        return next((f for f in self.faces if f.color), None)

    def runs(self, text: str) -> list[tuple[str, Face]]:
        out: list[tuple[str, Face]] = []
        emoji = self._emoji_face()
        i = 0
        while i < len(text):
            ch = text[i]
            cp = ord(ch)
            if cp in _INVISIBLE or _is_modifier(cp):
                i += 1
                continue
            face = None
            # Bild-Emoji (🌙) und Zeichen mit Emoji-Selektor (☾️) bunt statt als Textsymbol
            wants_emoji = cp >= 0x1F000 or text[i + 1:i + 2] == "\uFE0F"
            if wants_emoji and emoji is not None and emoji.has(cp):
                face = emoji
                end = _emoji_cluster_end(text, i)
                # Mit raqm setzt die Emoji-Schrift Sequenzen (👨‍👩‍👧, 👍🏽) zu einem Bild zusammen.
                # Ohne raqm nur das erste Emoji zeichnen statt einzelner Bruchstücke/Farbquadrate.
                if HAS_RAQM:
                    ch = text[i:end]
                elif _is_regional(cp) and end - i == 2:
                    ch = text[i:end]  # Flagge: beide Buchstaben-Symbole zeigen
                i = end
            else:
                i += 1
            if face is None:
                face = self.face_for(cp)
            if face is None:
                continue  # unbekanntes Zeichen lieber weglassen als □ zeichnen
            if out and out[-1][1] is face:
                out[-1] = (out[-1][0] + ch, face)
            else:
                out.append((ch, face))
        return out

    # --------------------------------------------------------------- metrics
    def width(self, text: str, size: int) -> float:
        return sum(face.font(size).getlength(run) * face.scale(size) for run, face in self.runs(text))

    def cap_height(self, size: int) -> int:
        top = self.primary.font(size).getbbox("H", anchor="ls")[1]
        return -top

    def truncate(self, text: str, size: int, max_width: float) -> str:
        if self.width(text, size) <= max_width:
            return text
        ell = "…"
        while text and self.width(text.rstrip() + ell, size) > max_width:
            text = text[:-1]
        return text.rstrip() + ell if text else ""

    # ------------------------------------------------------------------ draw
    def draw(
        self,
        img: Image.Image,
        xy: tuple[float, float],
        text: str,
        size: int,
        fill: tuple[int, ...],
        align: str = "left",
        valign: str = "baseline",
    ) -> float:
        """Zeichnet `text`; xy ist (x, Grundlinie) bzw. (x, Mitte) bei valign="middle".

        Gibt die gezeichnete Breite zurück.
        """
        x, y = xy
        total = self.width(text, size)
        if align == "right":
            x -= total
        elif align == "center":
            x -= total / 2
        if valign == "middle":
            y += self.cap_height(size) / 2

        d = ImageDraw.Draw(img, "RGBA")
        for run, face in self.runs(text):
            font = face.font(size)
            if face.bitmap:
                x += _draw_bitmap_emoji(img, (x, y), run, face, size)
                continue
            d.text((x, y), run, font=font, fill=fill, anchor="ls", embedded_color=face.color)
            x += font.getlength(run)
        return total


def _draw_bitmap_emoji(img: Image.Image, xy: tuple[float, float], run: str, face: Face, size: int) -> float:
    font = face.font(size)
    w = int(font.getlength(run)) + 4
    asc, desc = font.getmetrics()
    tmp = Image.new("RGBA", (w, asc + desc), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((0, asc), run, font=font, anchor="ls", embedded_color=True)
    s = face.scale(size)
    tmp = tmp.resize((max(1, round(w * s)), max(1, round((asc + desc) * s))), Image.LANCZOS)
    x, y = xy
    img.paste(tmp, (round(x), round(y - asc * s)), tmp)
    return font.getlength(run) * s


# --------------------------------------------------------------------------- #
#  Fertige Ketten
# --------------------------------------------------------------------------- #

_chains: dict[str, FontChain] = {}
_chains_lock = threading.Lock()


@functools.cache
def _fallback_faces() -> tuple[Face, ...]:
    faces: list[Face] = []
    jp = design.FONT_DIR / "NotoSansJP.ttf"
    if jp.exists():
        faces.append(Face(jp, weight=500))
    sym = design.FONT_DIR / "NotoSansSymbols2-Regular.ttf"
    if sym.exists():
        faces.append(Face(sym))
    for p in _first_existing(_SYSTEM_SYMBOLS) + _first_existing(_SYSTEM_CJK):
        try:
            faces.append(Face(p))
        except Exception:  # pragma: no cover - kaputte Systemschrift
            log.debug("Systemschrift %s nicht lesbar", p)

    emoji_candidates = sorted(str(p) for p in design.FONT_DIR.glob("*moji*.tt[fc]")) + _first_existing(_SYSTEM_EMOJI)
    for p in emoji_candidates:
        if _usable_color_font(p):
            faces.append(Face(p, color=True))
            break
    else:
        log.warning("Keine farbige Emoji-Schrift gefunden – Emoji in Namen werden ausgelassen.")
    return tuple(faces)


def chain(role: str) -> FontChain:
    """Rollen: serif (Titel), sans (Text), sans_medium, sans_semibold, sans_bold."""
    with _chains_lock:
        if role in _chains:
            return _chains[role]
        weights = {"sans": 400, "sans_medium": 500, "sans_semibold": 600, "sans_bold": 700}
        if role == "serif":
            primary = Face(design.FONT_DIR / "CormorantGaramond.ttf", weight=600)
        elif role == "serif_bold":
            primary = Face(design.FONT_DIR / "CormorantGaramond.ttf", weight=700)
        elif role in weights:
            primary = Face(design.FONT_DIR / "Inter.ttf", weight=weights[role])
        else:
            raise KeyError(role)
        _chains[role] = FontChain([primary, *_fallback_faces()])
        return _chains[role]
