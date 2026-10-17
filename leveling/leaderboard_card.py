from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .formatting import format_number
from .rankcard import (
    COLOR_MAIN,
    COLOR_SUB,
    SUPERSAMPLE,
    circle_avatar,
    fit_text,
    font_for_cap_height,
    glass_bar,
    progress_of,
    template,
    to_png,
)

WIDTH = 1600

# --- Layout (Pixel) ---------------------------------------------------------
FRAME_INSET = 26
HEADER_H = 330
TITLE_STYLE = (200, 64)     # (Grundlinie y, Versalhöhe)
SUBTITLE_STYLE = (262, 26)

PODIUM_H = 545
# Platz -> (Mitte x, Mitte y relativ zum Podium-Anfang, Avatar-Radius)
PODIUM_SLOTS = {1: (800, 165, 128), 2: (400, 215, 100), 3: (1200, 215, 100)}
PODIUM_NAME_MAX = {1: 420, 2: 340, 3: 340}
PODIUM_NAME_BASELINE = 400  # relativ zum Podium-Anfang, für alle drei Plätze gleich

ROW_X = (80, 1520)
ROW_H = 118
ROW_GAP = 14
EMPTY_H = 200
FOOTER_H = 210

COLOR_LINE = (190, 192, 200)
MEDAL_COLORS = {1: (222, 196, 130), 2: (200, 202, 210), 3: (206, 160, 122)}

# Ausschnitte aus der Vorlage (x0, y0, x1, y1) – ohne Rahmen, Avatar-Ring und Röhre
CASTLE_CROP = (860, 45, 1800, 352)
ROSES_CROP = (540, 430, 2085, 668)  # rechts vom Avatar-Ring, unter der Röhre


@dataclass(slots=True)
class LeaderboardEntry:
    place: int
    name: str
    level: int
    xp_current: int   # XP innerhalb des aktuellen Levels
    xp_needed: int    # XP für das nächste Level
    xp_total: int
    avatar_bytes: bytes | None = None


@dataclass(slots=True)
class LeaderboardData:
    server_name: str
    entries: list[LeaderboardEntry]


# --- Bausteine --------------------------------------------------------------
def _gradient(size: tuple[int, int], stops: list[tuple[float, tuple[int, int, int]]]) -> Image.Image:
    """Vertikaler Farbverlauf (RGBA)."""
    w, h = size
    column = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 0
                column.putpixel((0, y), (*(round(a + (b - a) * f) for a, b in zip(c0, c1)), 255))
                break
    return column.resize((w, h))


def _metal_stops(base: tuple[int, int, int]) -> list[tuple[float, tuple[int, int, int]]]:
    def shade(f: float) -> tuple[int, int, int]:
        return tuple(max(0, min(255, round(c + (255 - c) * f if f > 0 else c * (1 + f)))) for c in base)
    return [(0.0, shade(0.85)), (0.35, shade(0.3)), (0.52, shade(-0.25)), (0.68, shade(0.35)), (1.0, shade(0.75))]


SILVER = (200, 202, 210)


def _ring(inner_radius: int, thickness: int, base: tuple[int, int, int] = SILVER) -> Image.Image:
    """Chrom-Ring wie um den Avatar der Rangkarte (innen transparent)."""
    s = SUPERSAMPLE
    outer = inner_radius + thickness
    d = outer * 2 * s
    ring = _gradient((d, d), _metal_stops(base))
    mask = Image.new("L", (d, d), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((0, 0, d - 1, d - 1), fill=255)
    md.ellipse((thickness * s, thickness * s, d - 1 - thickness * s, d - 1 - thickness * s), fill=0)
    ring.putalpha(mask)
    lines = ImageDraw.Draw(ring)
    edge = (128, 130, 140, 220)
    lines.ellipse((0, 0, d - 1, d - 1), outline=edge, width=s)
    lines.ellipse((thickness * s, thickness * s, d - 1 - thickness * s, d - 1 - thickness * s), outline=edge, width=s)
    return ring.resize((outer * 2, outer * 2), Image.Resampling.LANCZOS)


def _disc(radius: int, base: tuple[int, int, int]) -> Image.Image:
    """Metall-Medaille (Kreisscheibe mit Verlauf)."""
    s = SUPERSAMPLE
    d = radius * 2 * s
    disc = _gradient((d, d), _metal_stops(base))
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
    disc.putalpha(mask)
    ImageDraw.Draw(disc).ellipse((0, 0, d - 1, d - 1), outline=(120, 122, 132, 230), width=2 * s)
    return disc.resize((radius * 2, radius * 2), Image.Resampling.LANCZOS)


def _avatar(canvas: Image.Image, center: tuple[int, int], radius: int, avatar_bytes: bytes | None) -> None:
    """Avatar (oder weißer Platzhalter) mit Chrom-Ring."""
    cx, cy = center
    s = SUPERSAMPLE
    d = radius * 2 * s
    base = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    ImageDraw.Draw(base).ellipse((0, 0, d - 1, d - 1), fill=(251, 251, 253, 255))
    base = base.resize((radius * 2, radius * 2), Image.Resampling.LANCZOS)
    canvas.alpha_composite(base, (cx - radius, cy - radius))
    if avatar_bytes:
        try:
            canvas.alpha_composite(circle_avatar(avatar_bytes, radius), (cx - radius, cy - radius))
        except Exception:
            pass  # kaputtes Bild -> weißer Platzhalter bleibt
    thickness = max(5, round(radius * 0.085))
    ring = _ring(radius, thickness)
    canvas.alpha_composite(ring, (cx - radius - thickness, cy - radius - thickness))


def _glass_track(canvas: Image.Image, box: tuple[int, int, int, int], progress: float) -> None:
    """Leere Glasröhre plus Füllung (die Röhre ist bei der Rangkarte Teil der Vorlage)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    s = SUPERSAMPLE
    track = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    ImageDraw.Draw(track).rounded_rectangle(
        (0, 0, w * s - 1, h * s - 1), radius=h * s // 2,
        fill=(248, 248, 250, 200), outline=(160, 162, 172, 230), width=2 * s,
    )
    canvas.alpha_composite(track.resize((w, h), Image.Resampling.LANCZOS), (x0, y0))
    fill = glass_bar(w, h, progress)
    if fill is not None:
        canvas.alpha_composite(fill, (x0, y0))


def _star(canvas: Image.Image, center: tuple[int, int], size: int) -> None:
    """Vierzackiger Funkelstern wie in den Ecken der Vorlage."""
    s = SUPERSAMPLE
    d = size * 2 * s
    layer = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    c = d / 2
    long_, short_, waist = c * 0.98, c * 0.62, c * 0.07
    points = [
        (c, c - long_), (c + waist, c - waist), (c + short_, c), (c + waist, c + waist),
        (c, c + long_), (c - waist, c + waist), (c - short_, c), (c - waist, c - waist),
    ]
    draw.polygon(points, fill=(118, 118, 128, 235))
    glow = c * 0.16
    draw.ellipse((c - glow, c - glow, c + glow, c + glow), fill=(235, 235, 240, 255))
    layer = layer.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
    canvas.alpha_composite(layer, (center[0] - size, center[1] - size))


def _frame(canvas: Image.Image) -> None:
    """Silberner Chrom-Rahmen wie bei der Rangkarte."""
    w, h = canvas.size
    s = SUPERSAMPLE
    layer = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    i, r = FRAME_INSET * s, 46 * s
    box = (i, i, w * s - 1 - i, h * s - 1 - i)
    draw.rounded_rectangle(box, radius=r, outline=(150, 152, 162, 255), width=9 * s)
    inner = (box[0] + 2 * s, box[1] + 2 * s, box[2] - 2 * s, box[3] - 2 * s)
    draw.rounded_rectangle(inner, radius=r - 2 * s, outline=(222, 223, 229, 255), width=4 * s)
    hl = (box[0] + 3 * s, box[1] + 3 * s, box[2] - 3 * s, box[3] - 3 * s)
    draw.rounded_rectangle(hl, radius=r - 3 * s, outline=(252, 252, 254, 255), width=s)
    canvas.alpha_composite(layer.resize((w, h), Image.Resampling.LANCZOS))


def _feather(size: tuple[int, int], left: float, right: float, top: float, bottom: float) -> Image.Image:
    """Alpha-Maske, die zu den Rändern hin weich ausläuft (Anteile der Breite/Höhe)."""
    w, h = size

    def ramp(n: int, a: float, b: float) -> list[float]:
        out = []
        for k in range(n):
            t = k / max(n - 1, 1)
            v = 1.0
            if a > 0 and t < a:
                v = min(v, t / a)
            if b > 0 and t > 1 - b:
                v = min(v, (1 - t) / b)
            out.append(v * v * (3 - 2 * v))  # weicher Übergang
        return out

    xs, ys = ramp(w, left, right), ramp(h, top, bottom)
    col = Image.new("L", (1, h))
    col.putdata([round(255 * v) for v in ys])
    row = Image.new("L", (w, 1))
    row.putdata([round(255 * v) for v in xs])
    return ImageChops.multiply(row.resize((w, h)), col.resize((w, h)))


@lru_cache(maxsize=8)
def _background(height: int) -> Image.Image:
    """Weicher Silber-Nebel aus der Vorlage + Schloss oben + Rosen unten + Rahmen + Sterne."""
    tpl = template().convert("RGB")
    w, h = WIDTH, height

    # 1) Nebel: Bildmitte der Vorlage stark weichgezeichnet und aufgehellt
    small = tpl.resize((tpl.width // 8, tpl.height // 8), Image.Resampling.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(5))
    aspect = w / h
    cw = min(small.width, round(small.height * aspect))
    cx = small.width // 2
    small = small.crop((cx - cw // 2, 0, cx + cw // 2, small.height))
    bg = small.resize((w, h), Image.Resampling.BICUBIC)
    bg = Image.blend(bg, Image.new("RGB", (w, h), (248, 248, 251)), 0.45).convert("RGBA")

    # 2) Schloss hinter dem Titel
    castle = tpl.crop(CASTLE_CROP)
    scale = 1.25
    castle = castle.resize((round(castle.width * scale), round(castle.height * scale)), Image.Resampling.LANCZOS)
    castle = castle.convert("RGBA")
    castle.putalpha(_feather(castle.size, 0.3, 0.3, 0.15, 0.35))
    bg.alpha_composite(castle, ((w - castle.width) // 2, FRAME_INSET + 4))

    # 3) Rosen und Wasser am unteren Rand
    roses = tpl.crop(ROSES_CROP)
    rh = round(roses.height * w / roses.width)
    roses = roses.resize((w, rh), Image.Resampling.LANCZOS).convert("RGBA")
    roses.putalpha(_feather(roses.size, 0.0, 0.0, 0.55, 0.0))
    bg.alpha_composite(roses, (0, h - rh))

    # 4) Rahmen und Sterne
    _frame(bg)
    _star(bg, (FRAME_INSET + 70, FRAME_INSET + 90), 34)
    _star(bg, (w - FRAME_INSET - 85, FRAME_INSET + 250), 22)
    return bg


def _spaced_text(draw: ImageDraw.ImageDraw, center_x: float, baseline: float, text: str, cap: int,
                    tracking: float, fill: tuple[int, int, int]) -> None:
    """Zentrierter Text mit Sperrung (Buchstabenabstand)."""
    font = font_for_cap_height(cap)
    gap = cap * tracking
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + gap * (len(text) - 1)
    x = center_x - total / 2
    for ch, cw in zip(text, widths):
        draw.text((x, baseline), ch, font=font, fill=fill, anchor="ls")
        x += cw + gap


def _divider(canvas: Image.Image, y: int) -> None:
    draw = ImageDraw.Draw(canvas)
    x0, x1 = ROW_X[0] + 40, ROW_X[1] - 40
    mid = WIDTH // 2
    draw.line((x0, y, mid - 30, y), fill=COLOR_LINE, width=2)
    draw.line((mid + 30, y, x1, y), fill=COLOR_LINE, width=2)
    _star(canvas, (mid, y), 16)


# --- Teile des Leaderboards -------------------------------------------------
def _draw_podium(canvas: Image.Image, top: int, entries: list[LeaderboardEntry]) -> None:
    draw = ImageDraw.Draw(canvas)
    for entry in entries:
        cx, cy_rel, r = PODIUM_SLOTS[entry.place]
        cy = top + cy_rel
        _avatar(canvas, (cx, cy), r, entry.avatar_bytes)

        # Medaille mit Platzzahl unten am Ring
        mr = 30 if entry.place == 1 else 26
        canvas.alpha_composite(_disc(mr, MEDAL_COLORS[entry.place]), (cx - mr, cy + r - mr + 6))
        draw.text((cx, cy + r + 6), str(entry.place), font=font_for_cap_height(round(mr * 0.9)),
                  fill=COLOR_MAIN, anchor="mm")

        name_cap = 36 if entry.place == 1 else 30
        name_y = top + PODIUM_NAME_BASELINE
        name, font = fit_text(draw, entry.name, name_cap, PODIUM_NAME_MAX[entry.place])
        draw.text((cx, name_y), name, font=font, fill=COLOR_MAIN, anchor="ms")
        draw.text((cx, name_y + 44), f"LEVEL {entry.level}", font=font_for_cap_height(24),
                  fill=COLOR_MAIN, anchor="ms")
        draw.text((cx, name_y + 82), f"{format_number(entry.xp_total)} XP", font=font_for_cap_height(20),
                  fill=COLOR_SUB, anchor="ms")


def _draw_row(canvas: Image.Image, top: int, entry: LeaderboardEntry) -> None:
    x0, x1 = ROW_X
    s = SUPERSAMPLE

    # Milchglas-Panel
    panel = Image.new("RGBA", ((x1 - x0) * s, ROW_H * s), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(
        (0, 0, (x1 - x0) * s - 1, ROW_H * s - 1), radius=28 * s,
        fill=(255, 255, 255, 130), outline=(196, 198, 206, 255), width=2 * s,
    )
    canvas.alpha_composite(panel.resize((x1 - x0, ROW_H), Image.Resampling.LANCZOS), (x0, top))

    draw = ImageDraw.Draw(canvas)
    draw.text((x0 + 118, top + 72), f"#{entry.place}", font=font_for_cap_height(32), fill=COLOR_MAIN, anchor="rs")
    _avatar(canvas, (x0 + 196, top + ROW_H // 2), 40, entry.avatar_bytes)

    text_x = x0 + 266
    level_text = f"LEVEL {entry.level}"
    level_font = font_for_cap_height(26)
    right = x1 - 36
    name_max = right - draw.textlength(level_text, font=level_font) - 50 - text_x
    name, font = fit_text(draw, entry.name, 28, name_max)
    draw.text((text_x, top + 50), name, font=font, fill=COLOR_MAIN, anchor="ls")
    draw.text((right, top + 50), level_text, font=level_font, fill=COLOR_MAIN, anchor="rs")

    _glass_track(canvas, (text_x, top + 66, x0 + 1180, top + 86), progress_of(entry.xp_current, entry.xp_needed))
    draw.text((right, top + 90), f"{format_number(entry.xp_total)} XP", font=font_for_cap_height(22),
              fill=COLOR_SUB, anchor="rs")


# --- öffentliche API --------------------------------------------------------
def render_leaderboard(data: LeaderboardData) -> io.BytesIO:
    """Erzeugt das Leaderboard als PNG im Speicher (blockierend -> in Thread ausführen)."""
    podium = [e for e in data.entries if e.place <= 3]
    rows = [e for e in data.entries if e.place > 3]

    height = HEADER_H + FOOTER_H
    if podium:
        height += PODIUM_H
    height += len(rows) * (ROW_H + ROW_GAP) if rows else (0 if podium else EMPTY_H)

    canvas = _background(height).copy()
    draw = ImageDraw.Draw(canvas)

    _spaced_text(draw, WIDTH / 2, TITLE_STYLE[0], "LEADERBOARD", TITLE_STYLE[1], 0.28, COLOR_MAIN)
    sub, sub_font = fit_text(draw, data.server_name, SUBTITLE_STYLE[1], WIDTH - 2 * ROW_X[0] - 80)
    draw.text((WIDTH / 2, SUBTITLE_STYLE[0]), sub, font=sub_font, fill=COLOR_SUB, anchor="ms")

    y = HEADER_H
    if podium:
        _draw_podium(canvas, y, podium)
        y += PODIUM_H
        if rows:
            _divider(canvas, y - 16)
    for entry in rows:
        _draw_row(canvas, y, entry)
        y += ROW_H + ROW_GAP
    if not data.entries:
        draw.text((WIDTH / 2, y + EMPTY_H / 2), "Noch hat niemand XP gesammelt.",
                  font=font_for_cap_height(30), fill=COLOR_SUB, anchor="mm")

    return to_png(canvas)
