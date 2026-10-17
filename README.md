# Luna

Discord-Bot mit Ticket-System und Level-System (Python, discord.py, SQLite).

## Aufbau

- `bot.py` – einziger Bot, lädt alle Cogs
- `config.py` – einzige Konfiguration (Server-ID, Rollen, Kategorien, Level-Einstellungen)
- `ticket_system/` – Panels, Tickets, Transcripts
- `leveling/` – XP, Level-Rollen, Rang-/Levelup-/Leaderboard-Karten, XP-Boost
- `data/` – SQLite-Datenbanken (`tickets.sqlite3`, `leveling.sqlite3`)
- `assets/` – Bilder für die Panels

## Start

```powershell
python -m venv env
env\Scripts\python.exe -m pip install -r requirements.txt
$env:DISCORD_TOKEN = "..."   # oder in .env (siehe .env.example)
env\Scripts\python.exe bot.py
```

Im Developer Portal müssen die Intents *Server Members* und *Message Content* aktiviert sein.

## Commands (Prefix `.`)

| Befehl | Zweck |
| --- | --- |
| `.setup-support`, `.setup-ban`, `.setup-jail`, `.setup-bewerbung` | Ticket-Panels senden |
| `.adduser @User`, `.delete` | im Ticket-Kanal: Nutzer hinzufügen, Ticket löschen (mit Transcript) |
| `.rank [Mitglied]`, `.leaderboard` | Rang- und Leaderboard-Karte |
| `.xp add\|remove`, `.xprise`, `.level-config show` | Level-Verwaltung (Admin) |
