"""Pillow-Renderer für die User- und die Server-Karte (2x-Auflösung, 1600 px breit)."""
from __future__ import annotations

import functools
import io
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter

import config as cfg

from . import design
from .text import chain

C = design.COLORS
L = design.LABELS

W = 1600
PAD = 56
GAP = 28
PANEL_RADIUS = 30
CHIP_RADIUS = 18
SS = 3  # Supersampling für weiche Kanten

Box = tuple[int, int, int, int]


# --------------------------------------------------------------------------- #
#  Daten
# --------------------------------------------------------------------------- #

@dataclass
class UserCardData:
    display_name: str
    username: str
    server_name: str
    avatar: bytes | None
    created_at: datetime
    joined_at: datetime | None
    message_rank: int | None
    voice_rank: int | None
    message_values: Sequence[int]          # passend zu windows
    voice_seconds: Sequence[int]
    windows: Sequence[int] = cfg.STATS_USER_LOOKBACK
    lookback_days: int = cfg.STATS_RANK_DAYS
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ServerCardData:
    server_name: str
    icon: bytes | None
    member_count: int
    created_at: datetime
    highlight_days: int
    highlight_messages: int
    highlight_voice_seconds: int
    message_values: Sequence[int]
    voice_seconds: Sequence[int]
    top_messages: Sequence[tuple[str, int]]
    top_voice: Sequence[tuple[str, int]]          # (Name, Sekunden)
    windows: Sequence[int] = cfg.STATS_SERVER_LOOKBACK
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------- #
#  Formatierung
# --------------------------------------------------------------------------- #

def _num(s: str) -> str:
    return s.replace(".", cfg.STATS_DECIMAL_SEP)


def fmt_int(n: int) -> str:
    """Ganze Zahl mit Tausendertrennzeichen passend zu DECIMAL_SEP (1,284 bzw. 1.284)."""
    thousands = "." if cfg.STATS_DECIMAL_SEP == "," else ","
    return f"{n:,}".replace(",", thousands)


def fmt_count(n: int) -> str:
    if n < 1000:
        return str(n)
    div, suffix = (1_000_000, "M") if n >= 999_500 else (1000, "k")
    v = n / div
    s = f"{v:.2f}" if v < 10 else f"{v:.1f}" if v < 100 else f"{v:.0f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return _num(s) + suffix


def fmt_hours(seconds: int) -> str:
    h = seconds / 3600
    return _num(f"{h:.2f}" if h < 1000 else f"{h:.1f}")


def _local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(cfg.STATS_TIMEZONE))


def fmt_date(dt: datetime) -> str:
    d = _local(dt)
    return f"{d.day}. {design.MONTHS[d.month - 1]} {d.year}"


def fmt_stand(dt: datetime) -> str:
    d = _local(dt)
    return L["stand"].format(date=f"{d.day:02d}.{d.month:02d}.{d.year}, {d.hour:02d}:{d.minute:02d}")


# --------------------------------------------------------------------------- #
#  Grundbausteine
# --------------------------------------------------------------------------- #

def _rounded_mask(w: int, h: int, r: int, outline: int = 0) -> Image.Image:
    """Weiche Maske eines abgerundeten Rechtecks (oder nur dessen Rand)."""
    m = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(m)
    box = (0, 0, w * SS - 1, h * SS - 1)
    if outline:
        d.rounded_rectangle(box, r * SS, outline=255, width=outline * SS)
    else:
        d.rounded_rectangle(box, r * SS, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def _circle_mask(d: int) -> Image.Image:
    m = Image.new("L", (d * SS, d * SS), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d * SS - 1, d * SS - 1), fill=255)
    return m.resize((d, d), Image.LANCZOS)


def _scaled(mask: Image.Image, alpha: int) -> Image.Image:
    return mask.point(lambda v: v * alpha // 255)


def _cover(img: Image.Image, w: int, h: int, focus_x: float = 0.55, focus_y: float = 0.4) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((math.ceil(img.width * scale), math.ceil(img.height * scale)), Image.LANCZOS)
    left = min(max(0, int(img.width * focus_x - w / 2)), img.width - w)
    top = min(max(0, int(img.height * focus_y - h / 2)), img.height - h)
    return img.crop((left, top, left + w, top + h))


def _gradient(w: int, h: int) -> Image.Image:
    top, bottom = (250, 249, 252), (232, 234, 240)
    g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        g.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return g.resize((w, h))


@functools.lru_cache(maxsize=1)
def _source_background() -> Image.Image | None:
    try:
        return Image.open(design.BACKGROUND_PATH).convert("RGB")
    except (FileNotFoundError, OSError):
        return None


@functools.lru_cache(maxsize=8)
def _backgrounds(w: int, h: int) -> tuple[Image.Image, Image.Image]:
    """(Hintergrund, Milchglas-Version) – einmal pro Kartengröße berechnet."""
    src = _source_background()
    img = _cover(src, w, h) if src is not None else _gradient(w, h)
    white = Image.new("RGB", (w, h), C["white"])
    base = Image.blend(img.filter(ImageFilter.GaussianBlur(2)), white, design.BACKGROUND_WASH_ALPHA / 255)
    # weißer Verlauf am unteren Rand, damit die Fußzeile über den Rosen lesbar bleibt
    fade = 240
    ramp = Image.linear_gradient("L").resize((1, fade)).point(lambda v: int(v * 0.86))
    base.paste(C["white"], (0, h - fade, w, h), ramp.resize((w, fade)))
    frosted = img.filter(ImageFilter.GaussianBlur(24))
    return base, frosted


# --------------------------------------------------------------------------- #
#  Icons (Vektor, Einheitskoordinaten 0..1)
# --------------------------------------------------------------------------- #

def _icon_hash(d: ImageDraw.ImageDraw, u: Callable[[float], float]) -> None:
    w = round(u(0.1))
    for a, b in (((0.40, 0.08), (0.30, 0.92)), ((0.72, 0.08), (0.62, 0.92)),
                 ((0.12, 0.35), (0.94, 0.35)), ((0.06, 0.65), (0.88, 0.65))):
        d.line((u(a[0]), u(a[1]), u(b[0]), u(b[1])), fill=255, width=w)


def _icon_speaker(d: ImageDraw.ImageDraw, u: Callable[[float], float]) -> None:
    d.polygon([(u(0.06), u(0.36)), (u(0.26), u(0.36)), (u(0.50), u(0.12)),
               (u(0.50), u(0.88)), (u(0.26), u(0.64)), (u(0.06), u(0.64))], fill=255)
    w = round(u(0.08))
    for r in (0.2, 0.36):
        d.arc((u(0.52 - r), u(0.5 - r), u(0.52 + r), u(0.5 + r)), -50, 50, fill=255, width=w)


def _icon_trophy(d: ImageDraw.ImageDraw, u: Callable[[float], float]) -> None:
    d.rectangle((u(0.24), u(0.08), u(0.76), u(0.3)), fill=255)
    d.chord((u(0.24), u(-0.05), u(0.76), u(0.62)), 0, 180, fill=255)
    w = round(u(0.07))
    d.arc((u(0.04), u(0.14), u(0.34), u(0.44)), 90, 270, fill=255, width=w)
    d.arc((u(0.66), u(0.14), u(0.96), u(0.44)), -90, 90, fill=255, width=w)
    d.rectangle((u(0.45), u(0.58), u(0.55), u(0.76)), fill=255)
    d.rounded_rectangle((u(0.27), u(0.76), u(0.73), u(0.9)), u(0.04), fill=255)


def _icon_clock(d: ImageDraw.ImageDraw, u: Callable[[float], float]) -> None:
    w = round(u(0.09))
    d.ellipse((u(0.07), u(0.07), u(0.93), u(0.93)), outline=255, width=w)
    d.line((u(0.5), u(0.52), u(0.5), u(0.25)), fill=255, width=w)
    d.line((u(0.5), u(0.52), u(0.7), u(0.62)), fill=255, width=w)


def _icon_calendar(d: ImageDraw.ImageDraw, u: Callable[[float], float]) -> None:
    w = round(u(0.08))
    d.rounded_rectangle((u(0.08), u(0.16), u(0.92), u(0.92)), u(0.1), outline=255, width=w)
    d.rectangle((u(0.08), u(0.16), u(0.92), u(0.38)), fill=255)
    for x in (0.3, 0.7):
        d.line((u(x), u(0.04), u(x), u(0.24)), fill=255, width=w)


def _icon_users(d: ImageDraw.ImageDraw, u: Callable[[float], float]) -> None:
    d.ellipse((u(0.32), u(0.06), u(0.68), u(0.42)), fill=255)
    d.pieslice((u(0.14), u(0.5), u(0.86), u(1.22)), 180, 360, fill=255)


def _icon_sparkle(d: ImageDraw.ImageDraw, u: Callable[[float], float]) -> None:
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        r = 0.5 if i % 2 == 0 else 0.11
        pts.append((u(0.5 + r * math.cos(ang)), u(0.5 + r * math.sin(ang))))
    d.polygon(pts, fill=255)


_ICONS = {
    "hash": _icon_hash, "speaker": _icon_speaker, "trophy": _icon_trophy, "clock": _icon_clock,
    "calendar": _icon_calendar, "users": _icon_users, "sparkle": _icon_sparkle,
}


# --------------------------------------------------------------------------- #
#  Canvas
# --------------------------------------------------------------------------- #

class Canvas:
    def __init__(self, h: int) -> None:
        self.w, self.h = W, h
        base, self.frosted = _backgrounds(W, h)
        self.img = base.copy()

    # Flächen -------------------------------------------------------------
    def fill(self, box: Box, color: tuple[int, int, int], alpha: int, radius: int) -> None:
        x0, y0, x1, y1 = box
        mask = _scaled(_rounded_mask(x1 - x0, y1 - y0, radius), alpha)
        self.img.paste(color, (x0, y0, x1, y1), mask)

    def outline(self, box: Box, color: tuple[int, int, int], alpha: int, radius: int, width: int = 2) -> None:
        x0, y0, x1, y1 = box
        mask = _scaled(_rounded_mask(x1 - x0, y1 - y0, radius, outline=width), alpha)
        self.img.paste(color, (x0, y0, x1, y1), mask)

    def shadows(self, boxes: Sequence[Box], radius: int = PANEL_RADIUS) -> None:
        layer = Image.new("L", (self.w, self.h), 0)
        for x0, y0, x1, y1 in boxes:
            layer.paste(_rounded_mask(x1 - x0, y1 - y0, radius), (x0, y0 + 10))
        layer = _scaled(layer.filter(ImageFilter.GaussianBlur(22)), 46)
        self.img.paste(C["text"], (0, 0, self.w, self.h), layer)

    def glass(self, box: Box, radius: int = PANEL_RADIUS, alpha: int = design.PANEL_ALPHA) -> None:
        x0, y0, x1, y1 = box
        region = self.frosted.crop(box)
        region = Image.blend(region, Image.new("RGB", region.size, C["white"]), alpha / 255)
        self.img.paste(region, (x0, y0), _rounded_mask(x1 - x0, y1 - y0, radius))
        self.outline(box, C["white"], 235, radius, 2)

    def chip(self, box: Box, radius: int = CHIP_RADIUS) -> None:
        self.fill(box, C["white"], design.CHIP_ALPHA, radius)
        self.outline(box, C["line"], 200, radius, 2)

    # Icons & Bilder -----------------------------------------------------
    def icon(self, kind: str, center: tuple[float, float], size: int, color: tuple[int, int, int], alpha: int = 255) -> None:
        big = size * 4
        m = Image.new("L", (big, big), 0)
        _ICONS[kind](ImageDraw.Draw(m), lambda v: v * (big - 1))
        m = _scaled(m.resize((size, size), Image.LANCZOS), alpha)
        x, y = round(center[0] - size / 2), round(center[1] - size / 2)
        self.img.paste(color, (x, y, x + size, y + size), m)

    def round_image(self, data: bytes | None, box: tuple[int, int], d: int, fallback_text: str) -> None:
        x, y = box
        # goldener Ring + weißer Innenrand
        ring = 6
        self.img.paste(C["gold_soft"], (x - ring, y - ring, x + d + ring, y + d + ring), _circle_mask(d + 2 * ring))
        self.img.paste(C["white"], (x - 2, y - 2, x + d + 2, y + d + 2), _circle_mask(d + 4))
        pic: Image.Image | None = None
        if data:
            try:
                src = Image.open(io.BytesIO(data)).convert("RGBA").resize((d, d), Image.LANCZOS)
                # Transparente Avatare/Icons auf Weiß statt auf Schwarz legen
                pic = Image.new("RGB", (d, d), C["white"])
                pic.paste(src, (0, 0), src)
            except OSError:
                pic = None
        if pic is None:
            pic = Image.new("RGB", (d, d), (244, 238, 226))
            letter = (fallback_text.strip() or "?")[0].upper()
            chain("serif").draw(pic, (d / 2, d / 2), letter, int(d * 0.5), C["gold"], align="center", valign="middle")
        self.img.paste(pic, (x, y), _circle_mask(d))

    def text(self, role: str, xy: tuple[float, float], text: str, size: int,
             color: tuple[int, int, int], **kw) -> float:
        return chain(role).draw(self.img, xy, text, size, color, **kw)

    # Ausgabe ------------------------------------------------------------
    def finish(self) -> io.BytesIO:
        out = self.img.convert("RGBA")
        out.putalpha(_rounded_mask(self.w, self.h, 44))
        border = _rounded_mask(self.w, self.h, 44, outline=3)
        out.paste((255, 255, 255, 255), (0, 0, self.w, self.h), _scaled(border, 220))
        buf = io.BytesIO()
        out.save(buf, "PNG", compress_level=6)
        buf.seek(0)
        return buf


# --------------------------------------------------------------------------- #
#  Zusammengesetzte Elemente
# --------------------------------------------------------------------------- #

def _decor(cv: Canvas) -> None:
    """Ein paar zarte Funkel-Sterne wie im Hintergrundbild."""
    for (fx, fy, s, a) in ((0.965, 0.05, 30, 200), (0.94, 0.085, 14, 160)):
        cv.icon("sparkle", (cv.w * fx, cv.h * fy), s, C["white"], a)


def _badge(cv: Canvas, right: int, top: int, icon: str, label: str, value: str) -> int:
    """Kleines Info-Feld oben rechts. Gibt die linke Kante zurück."""
    lw = chain("sans_medium").width(label, 23) + 34
    vw = chain("sans_semibold").width(value, 31)
    w = int(max(lw, vw) + 56)
    h = 108
    box = (right - w, top, right, top + h)
    cv.shadows([box], 22)
    cv.glass(box, 22)
    x = box[0] + 28
    cv.icon(icon, (x + 11, top + 33), 22, C["gold"])
    cv.text("sans_medium", (x + 34, top + 33), label, 23, C["muted"], valign="middle")
    cv.text("sans_semibold", (x, top + 78), value, 31, C["text"], valign="middle")
    return box[0]


def _header(cv: Canvas, image: bytes | None, d: int, title: str, after_title: str,
            subline: str, badges: Sequence[tuple[str, str, str]]) -> int:
    """Kopfbereich. Gibt die Unterkante zurück."""
    cv.round_image(image, (PAD, PAD), d, title)
    right = W - PAD
    for icon, label, value in reversed(badges):
        right = _badge(cv, right, PAD + 8, icon, label, value) - 18

    x = PAD + d + 40
    avail = right - 24 - x
    cy = PAD + d / 2
    title_size = 78 if d >= 160 else 72
    serif = chain("serif")
    after_w = chain("sans").width(after_title, 32) + 20 if after_title else 0
    title = serif.truncate(title, title_size, max(avail * 0.55, avail - after_w))
    tw = cv.text("serif", (x, cy + 4), title, title_size, C["text"])
    if after_title:
        rest = avail - tw - 20
        if rest > 60:
            cv.text("sans", (x + tw + 20, cy + 4), chain("sans").truncate(after_title, 32, rest), 32, C["muted"])

    cv.icon("sparkle", (x + 12, cy + 50), 24, C["gold"])
    cv.text("sans_medium", (x + 36, cy + 50), chain("sans_medium").truncate(subline, 30, avail - 36), 30,
            C["muted"], valign="middle")
    return PAD + d


def _panel(cv: Canvas, box: Box, title: str, icon: str, suffix: str = "") -> int:
    """Milchglas-Panel mit Titel. Gibt die y-Position für den Inhalt zurück."""
    x0, y0, x1, _ = box
    cv.glass(box)
    tw = cv.text("serif", (x0 + 30, y0 + 60), title, 44, C["text"])
    if suffix:
        cv.text("sans_medium", (x0 + 30 + tw + 14, y0 + 58), suffix, 26, C["muted"])
    cv.icon(icon, (x1 - 46, y0 + 46), 32, C["gold"])
    cv.fill((x0 + 30, y0 + 84, x1 - 30, y0 + 86), C["gold_soft"], 110, 1)
    return y0 + 106


def _period_rows(cv: Canvas, box: Box, top: int, windows: Sequence[int], values: Sequence[str], unit: str) -> None:
    x0, _, x1, _ = box
    for i, (days, val) in enumerate(zip(windows, values)):
        ry = top + i * 82
        chip = (x0 + 22, ry, x1 - 22, ry + 70)
        cv.chip(chip)
        cy = ry + 35
        pill = (chip[0] + 12, cy - 23, chip[0] + 12 + 86, cy + 23)
        cv.fill(pill, C["gold_soft"], 48, 14)
        cv.text("sans_bold", ((pill[0] + pill[2]) / 2, cy), f"{days}{L['day_suffix']}", 26, C["gold"],
                align="center", valign="middle")
        vx = pill[2] + 22
        vw = cv.text("sans_semibold", (vx, cy), val, 36, C["text"], valign="middle")
        cv.text("sans", (vx + vw + 10, cy), unit, 25, C["muted"], valign="middle")


def _rank_rows(cv: Canvas, box: Box, top: int, rows: Sequence[tuple[str, str, int | None]]) -> None:
    x0, _, x1, _ = box
    h = 110
    for i, (icon, label, rank) in enumerate(rows):
        ry = top + i * (h + 14)
        chip = (x0 + 22, ry, x1 - 22, ry + h)
        cv.chip(chip)
        cy = ry + h / 2
        cv.icon(icon, (chip[0] + 38, cy), 26, C["muted"])
        cv.text("sans_medium", (chip[0] + 66, cy), label, 32, C["text"], valign="middle")
        txt = f"#{rank}" if rank else "—"
        tw = chain("sans_bold").width(txt, 36)
        pill = (int(chip[2] - 18 - tw - 44), int(cy - 30), chip[2] - 18, int(cy + 30))
        cv.fill(pill, C["gold_soft"], 48 if rank else 0, 16)
        cv.text("sans_bold", ((pill[0] + pill[2]) / 2, cy), txt, 36, C["gold"] if rank else C["muted"],
                align="center", valign="middle")


def _top_rows(cv: Canvas, box: Box, top: int, rows: Sequence[tuple[str, str]], unit: str, n: int) -> None:
    x0, _, x1, _ = box
    if not rows:
        cv.text("sans_medium", ((x0 + x1) / 2, top + (n * 72 - 10) / 2), L["no_data"], 30, C["muted"],
                align="center", valign="middle")
        return
    medal = {1: C["gold_soft"], 2: C["silver"], 3: C["bronze"]}
    for i, (name, val) in enumerate(rows):
        ry = top + i * 72
        chip = (x0 + 22, ry, x1 - 22, ry + 62)
        cv.chip(chip)
        cy = ry + 31
        place = i + 1
        cx = chip[0] + 36
        if place in medal:
            cv.img.paste(medal[place], (cx - 20, int(cy) - 20, cx + 20, int(cy) + 20), _circle_mask(40))
            cv.text("sans_bold", (cx, cy), str(place), 22, C["white"], align="center", valign="middle")
        else:
            cv.outline((cx - 20, int(cy) - 20, cx + 20, int(cy) + 20), C["line"], 255, 20, 2)
            cv.text("sans_bold", (cx, cy), str(place), 22, C["muted"], align="center", valign="middle")

        right = chip[2] - 22
        uw = cv.text("sans", (right, cy), unit, 23, C["muted"], align="right", valign="middle")
        vw = cv.text("sans_semibold", (right - uw - 10, cy), val, 30, C["text"], align="right", valign="middle")
        name_x = cx + 40
        name_w = right - uw - vw - 30 - name_x
        cv.text("sans_medium", (name_x, cy), chain("sans_medium").truncate(name, 30, name_w), 30, C["text"],
                valign="middle")


def _footer(cv: Canvas, days: int, generated_at: datetime) -> None:
    y = cv.h - 44
    cv.icon("clock", (PAD + 12, y), 22, C["muted"])
    cv.text("sans", (PAD + 34, y), L["footer"].format(days=days, tz=cfg.STATS_TIMEZONE), 23, C["muted"], valign="middle")
    sw = cv.text("sans", (W - PAD, y), fmt_stand(generated_at), 23, C["muted"], align="right", valign="middle")
    cv.icon("sparkle", (W - PAD - sw - 22, y), 20, C["gold"])


def _columns(top: int, height: int, n: int) -> list[Box]:
    w = (W - 2 * PAD - (n - 1) * GAP) // n
    return [(PAD + i * (w + GAP), top, PAD + i * (w + GAP) + w, top + height) for i in range(n)]


# --------------------------------------------------------------------------- #
#  Karten
# --------------------------------------------------------------------------- #

ROW_PANEL_H = 106 + 3 * 82 - 12 + 28  # Titel + 3 Zeilen + Abstand unten


def render_user_card(data: UserCardData) -> io.BytesIO:
    avatar = 168
    panels_top = PAD + avatar + 44
    h = panels_top + ROW_PANEL_H + 96
    cv = Canvas(h)
    _decor(cv)

    badges = [("calendar", L["created"], fmt_date(data.created_at))]
    if data.joined_at:
        badges.append(("calendar", L["joined"], fmt_date(data.joined_at)))
    username = data.username if data.username != data.display_name else ""
    _header(cv, data.avatar, avatar, data.display_name, username, data.server_name, badges)

    ranks, msgs, voice = _columns(panels_top, ROW_PANEL_H, 3)
    cv.shadows([ranks, msgs, voice])

    top = _panel(cv, ranks, L["ranks"], "trophy")
    _rank_rows(cv, ranks, top, [("hash", L["rank_messages"], data.message_rank),
                                ("speaker", L["rank_voice"], data.voice_rank)])

    top = _panel(cv, msgs, L["messages"], "hash")
    _period_rows(cv, msgs, top, data.windows, [fmt_count(v) for v in data.message_values], L["unit_messages"])

    top = _panel(cv, voice, L["voice"], "speaker")
    _period_rows(cv, voice, top, data.windows, [fmt_hours(v) for v in data.voice_seconds], L["unit_hours"])

    _footer(cv, data.lookback_days, data.generated_at)
    return cv.finish()


def render_server_card(data: ServerCardData) -> io.BytesIO:
    icon = 152
    row1 = PAD + icon + 44
    top_h = 106 + cfg.STATS_TOP_N * 72 - 10 + 28
    row2 = row1 + ROW_PANEL_H + GAP
    h = row2 + top_h + 96
    cv = Canvas(h)
    _decor(cv)

    _header(cv, data.icon, icon, L["overview"], "", data.server_name, [
        ("users", L["members"], fmt_int(data.member_count)),
        ("calendar", L["created"], fmt_date(data.created_at)),
    ])

    hl, msgs, voice = _columns(row1, ROW_PANEL_H, 3)
    tm, tv = _columns(row2, top_h, 2)
    cv.shadows([hl, msgs, voice, tm, tv])

    # Zeitraum: beide Summen groß
    top = _panel(cv, hl, L["lookback"], "clock", f"· {data.highlight_days}{L['day_suffix']}")
    for i, (val, unit) in enumerate(((fmt_count(data.highlight_messages), L["unit_messages_long"]),
                                     (fmt_hours(data.highlight_voice_seconds), L["unit_hours_long"]))):
        ry = top + i * 123
        chip = (hl[0] + 22, ry, hl[2] - 22, ry + 111)
        cv.chip(chip)
        cx = (chip[0] + chip[2]) / 2
        cv.text("sans_semibold", (cx, ry + 60), val, 52, C["gold"], align="center")
        cv.text("sans", (cx, ry + 93), unit, 24, C["muted"], align="center")

    top = _panel(cv, msgs, L["messages"], "hash")
    _period_rows(cv, msgs, top, data.windows, [fmt_count(v) for v in data.message_values], L["unit_messages"])

    top = _panel(cv, voice, L["voice"], "speaker")
    _period_rows(cv, voice, top, data.windows, [fmt_hours(v) for v in data.voice_seconds], L["unit_hours"])

    top = _panel(cv, tm, L["top_messages"], "hash")
    _top_rows(cv, tm, top, [(n, fmt_count(v)) for n, v in data.top_messages], L["unit_messages"], cfg.STATS_TOP_N)

    top = _panel(cv, tv, L["top_voice"], "speaker")
    _top_rows(cv, tv, top, [(n, fmt_hours(v)) for n, v in data.top_voice], L["unit_hours"], cfg.STATS_TOP_N)

    _footer(cv, data.highlight_days, data.generated_at)
    return cv.finish()
