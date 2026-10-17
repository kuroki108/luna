"""Setzt Mitglieder direkt auf ein Level (Gesamt-XP = Start-XP dieses Levels).

    python leveling/tools/set_level.py <user_id> <level> [<user_id> <level> ...]

Vorhandene XP werden überschrieben.
Die Level-Rollen vergibt der Bot beim nächsten Start (Rollen-Abgleich) – am besten bei gestopptem Bot ausführen.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import config as cfg  # noqa: E402
from leveling.leveling_math import level_from_total_xp, total_xp_for_level  # noqa: E402

args = sys.argv[1:]
if not args or len(args) % 2:
    sys.exit(__doc__)
pairs = [(int(args[i]), int(args[i + 1])) for i in range(0, len(args), 2)]

conn = sqlite3.connect(cfg.LEVEL_DB_PATH)

with conn:
    for user_id, level in pairs:
        total = total_xp_for_level(level)
        conn.execute(
            """
            INSERT INTO users (user_id, total_xp) VALUES (?, ?)
            ON CONFLICT (user_id) DO UPDATE SET total_xp = excluded.total_xp
            """,
            (user_id, total),
        )
        assert level_from_total_xp(total)[0] == level
        print(f"{user_id}: Level {level} ({total} XP)")
conn.close()
