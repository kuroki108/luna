"""Vorschaubilder ohne Discord.

Aufruf aus dem Projekt-Root:  env\\Scripts\\python.exe -m stats.preview [ordner]
Erzeugt preview_user.png und preview_server.png im angegebenen (Standard: aktuellen) Ordner.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .render import ServerCardData, UserCardData, render_server_card, render_user_card


def _render_previews(out_dir: Path) -> None:
    now = datetime.now(timezone.utc)
    user = UserCardData(
        display_name="フィン ⊹ ☾", username="kuroki_108", server_name="lunaR palace ₊ ⊹",
        avatar=None, created_at=datetime(2024, 3, 20, tzinfo=timezone.utc),
        joined_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        message_rank=10, voice_rank=4, message_values=[18, 180, 262],
        voice_seconds=[7128, 39888, 57312], generated_at=now,
    )
    t = time.perf_counter()
    (out_dir / "preview_user.png").write_bytes(render_user_card(user).getvalue())
    t_user = time.perf_counter() - t

    server = ServerCardData(
        server_name="lunaR palace ₊ ⊹ 🌙", icon=None, member_count=1284,
        created_at=datetime(2026, 2, 10, tzinfo=timezone.utc), highlight_days=14,
        highlight_messages=11700, highlight_voice_seconds=843480,
        message_values=[651, 5930, 26000], voice_seconds=[158112, 523188, 2842668],
        top_messages=[("_4rei.h", 3940), ("ysshi", 850), ("xiamafk", 600), ("フィン", 262), ("tomlh7", 120)],
        top_voice=[("_4rei.h", 141408), ("xiamafk", 118008), ("tomlh7", 105768), ("フィン ☾", 57312)],
        generated_at=now,
    )
    t = time.perf_counter()
    (out_dir / "preview_server.png").write_bytes(render_server_card(server).getvalue())
    t_server = time.perf_counter() - t
    print(f"Vorschau: user {t_user:.2f}s, server {t_server:.2f}s -> {out_dir.resolve()}")


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    _render_previews(out_dir)


if __name__ == "__main__":
    main()
