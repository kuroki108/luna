# Luna Projektanweisungen

## Projekt

Luna ist ein Python-Discord-Bot mit Ticket-System und Level-System. Es gibt genau **einen Bot** (`bot.py`) und **eine Konfiguration** (`config.py`); alles andere sind Cogs:

| Paket | Cog | Inhalt |
| --- | --- | --- |
| `ticket_system/` | `PanelsCog`, `TicketCommandsCog` | Panels, Tickets, Transcripts, Ticket-Commands (SQLite `data/tickets.sqlite3`) |
| `leveling/` | `Leveling` (Extension `leveling.leveling`) | XP, Level-Rollen, Rang-/Levelup-/Leaderboard-Karten, XP-Boost (SQLite `data/leveling.sqlite3`) |

Beide Systeme verwenden SQLite über `aiosqlite`. Alles läuft nur auf der Guild `GUILD_ID` aus `config.py`.

## Umgebung

- Python-Umgebung: `env/`
- Abhängigkeiten: `requirements.txt` (discord.py, aiosqlite, python-dotenv, Pillow)
- Datenbanken: `data/tickets.sqlite3`, `data/leveling.sqlite3`
- Discord-Token: Umgebungsvariable `DISCORD_TOKEN` (siehe `.env.example`)
- Konfiguration: nur `config.py`; Level-Einstellungen stehen im Abschnitt `LEVEL-SYSTEM` (Namen mit `LEVEL_`-Präfix, wo sie sonst mit dem Ticket-System kollidieren würden)

## Prüfen und Starten

```powershell
env\Scripts\python.exe -m compileall -q bot.py config.py ticket_system leveling
env\Scripts\python.exe -m pip check
env\Scripts\python.exe bot.py
```

Der letzte Befehl startet den Bot mit dem konfigurierten Discord-Token und benötigt eine Netzwerkverbindung. Für lokale Änderungen am Speicher kann eine temporäre SQLite-Datei verwendet werden.

## Commands (Prefix `.`)

Ticket-System:

- `.setup-support`, `.setup-ban`, `.setup-jail`, `.setup-bewerbung` senden die Panels.
- `.adduser @User` fügt im Ticket-Kanal einen Nutzer hinzu.
- `.delete` fordert eine Bestätigung an und erstellt vor dem Löschen ein Transcript.

Level-System:

- `.rank [Mitglied]`, `.leaderboard` zeigen Karten.
- `.xp add|remove`, `.xprise <prozent> <dauer> [text|voice]` (Boost, `status`/`stop`), `.level-config show` sind Admin-Befehle.

## Änderungsregeln

- Bestehende APIs und die Konfiguration in `config.py` beibehalten; keine zweite Config oder zweiten Bot anlegen, neue Funktionen als Cog ergänzen.
- Keine echten Tokens oder Serverdaten in Dateien eintragen.
- Datenbanken nie löschen oder überschreiben; Änderungen am Speicher (Ticket oder Level) mit einem isolierten SQLite-Test auf einer Kopie prüfen.
- Vor dem Abschluss mindestens den Syntaxcheck ausführen.
