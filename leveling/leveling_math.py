from __future__ import annotations

import config as cfg

A, B, C = cfg.LEVEL_CURVE_A, cfg.LEVEL_CURVE_B, cfg.LEVEL_CURVE_C
D = cfg.LEVEL_CURVE_MAX_GROWTH
if C <= 0 or A < 0 or B < 0 or (D is not None and D < 0):
    # Sonst bräuchte ein Level 0 XP und level_from_total_xp() liefe endlos
    raise ValueError(
        "config.py: LEVEL_CURVE_C muss > 0 sein, LEVEL_CURVE_A, LEVEL_CURVE_B und LEVEL_CURVE_MAX_GROWTH ≥ 0."
    )


# Level 0 = noch keine XP. Mit der ersten XP ist man Level 1, danach folgt die Kurve:
# Level n → n+1 (n ≥ 1) kostet _curve(n - 1). Die XP für Level 1 zählen schon zum Fortschritt auf Level 2.
# Die Kurve ist quadratisch, bis eine Stufe um mehr als D XP teurer würde als die vorige –
# ab dort (Index _KNEE) wächst sie nur noch linear um D pro Level.

def _quadratic(n: int) -> int:
    return A * n**2 + B * n + C


def _find_knee() -> int | None:
    """Letzter Index, an dem die quadratische Kurve gilt (None = sie gilt immer)."""
    if D is None or (A == 0 and B <= D):
        return None
    knee = 0
    # _quadratic(k) - _quadratic(k - 1) = A·(2k - 1) + B
    while A * (2 * (knee + 1) - 1) + B <= D:
        knee += 1
    return knee


_KNEE = _find_knee()


def _curve(n: int) -> int:
    if _KNEE is None or n <= _KNEE:
        return _quadratic(n)
    return _quadratic(_KNEE) + D * (n - _KNEE)


def _quadratic_sum(n: int) -> int:
    """Summe von _quadratic(0) bis _quadratic(n - 1)."""
    return A * ((n - 1) * n * (2 * n - 1) // 6) + B * ((n - 1) * n // 2) + C * n


def xp_for_next_level(level: int) -> int:
    """XP, die (laut Fortschrittsbalken) nötig sind, um von `level` auf `level + 1` zu kommen."""
    return 1 if level <= 0 else _curve(level - 1)


def total_xp_for_level(level: int) -> int:
    """Kumulative XP, die insgesamt nötig sind, um `level` zu erreichen (geschlossene Formel)."""
    if level <= 0:
        return 0
    n = level - 1
    if _KNEE is None or n <= _KNEE + 1:
        return max(1, _quadratic_sum(n))
    tail = n - _KNEE - 1
    return _quadratic_sum(_KNEE + 1) + tail * _quadratic(_KNEE) + D * (tail * (tail + 1) // 2)


def level_from_total_xp(total_xp: int) -> tuple[int, int]:
    """Gibt (level, xp_im_level) für eine Gesamt-XP zurück."""
    if total_xp <= 0:
        return 0, 0
    level = 1
    remaining = total_xp
    while remaining >= (needed := _curve(level - 1)):
        remaining -= needed
        level += 1
    return level, remaining
