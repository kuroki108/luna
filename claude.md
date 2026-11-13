# Luna Projektanweisungen

## Projekt

Luna ist ein Python-Discord-Bot mit Ticket-System, Level-System, Invite-Tracker und Server-Log. Es gibt genau **einen Bot** (`bot.py`) und **eine Konfiguration** (`config.py`); alles andere sind Cogs:

| Paket | Cog | Inhalt |
| --- | --- | --- |
| `ticket_system/` | `PanelsCog`, `TicketCommandsCog` | Panels, Tickets, Transcripts, Ticket-Commands (SQLite `data/tickets.sqlite3`) |
| `leveling/` | `Leveling` (Extension `leveling.leveling`) | XP, Level-Rollen, Rang-/Levelup-/Leaderboard-Karten, XP-Boost (SQLite `data/leveling.sqlite3`) |
| `invite_tracker/` | `InviteTracker` (Extension `invite_tracker.invites`) | Erkennt den Invite-Link jedes Beitritts, Invite-Statistiken, Join-Log (SQLite `data/invites.sqlite3`) |
| `server_log/` | `LoggingCog` (Extension `server_log.log`) | Logs für gelöschte/bearbeitete Nachrichten, Beitritte/Austritte, Kicks, Banns, Entbannungen, vergebene/entfernte Rollen; per `.unlog` ausgenommene Kanäle (SQLite `data/server_log.sqlite3`) |

Ticket-System, Level-System, Invite-Tracker und Server-Log verwenden SQLite über `aiosqlite`. Level-System, Invite-Tracker und Server-Log laufen nur auf der Guild `GUILD_ID` aus `config.py` und ignorieren andere Server. Das Ticket-System nutzt zusätzlich den Entbannungsserver (`UNBAN_*`-Einstellungen).

Fehler bei Prefix-Commands: Cogs mit eigenem `cog_command_error` (Leveling, Invite-Tracker) antworten selbst; `on_command_error` in `bot.py` überspringt diese und ignoriert unbekannte Commands.

## Umgebung

- Python-Umgebung: `env/` (Python 3.13)
- Abhängigkeiten: `requirements.txt` (discord.py, aiosqlite, python-dotenv, Pillow)
- Datenbanken: `data/tickets.sqlite3`, `data/leveling.sqlite3`, `data/invites.sqlite3`, `data/server_log.sqlite3`
- Discord-Token: Umgebungsvariable `DISCORD_TOKEN` (siehe `.env.example`)
- Konfiguration: nur `config.py`. Reihenfolge: Ticket-System, Level-System (Namen mit `LEVEL_`-Präfix, wo sie sonst mit dem Ticket-System kollidieren würden), Abschnitt `INVITE-TRACKER` (Präfix `INVITE_`), Abschnitt `SERVER-LOG` (`MESSAGE_LOG_CHANNEL_ID`, `MEMBER_LOG_CHANNEL_ID`, `MOD_LOG_CHANNEL_ID`, `ROLE_LOG_CHANNEL_ID`, `SERVER_LOG_DB_PATH`). Kanal-IDs mit `0` bedeuten „aus“.
- Bot-Berechtigungen: „Server verwalten“ (Invite-Tracker), „Audit-Log anzeigen“ (Server-Log: wer gekickt/gebannt/Rollen geändert hat), „Rollen verwalten“ (Level-Rollen), „Nachrichten verwalten“ (`.unlog` löscht den Befehl)

## Prüfen und Starten

```powershell
env\Scripts\python.exe -m compileall -q bot.py config.py ticket_system leveling invite_tracker server_log
env\Scripts\python.exe -m pip check
env\Scripts\python.exe bot.py
```

Der letzte Befehl startet den Bot mit dem konfigurierten Discord-Token und benötigt eine Netzwerkverbindung. Für lokale Änderungen am Speicher kann eine temporäre SQLite-Datei verwendet werden.

## Commands (Prefix `.`)

Die vollständige Liste mit Berechtigungen steht in `commands.txt`. Bei neuen oder geänderten Commands beide Stellen aktualisieren.

Ticket-System:

- `.setup-support`, `.setup-ban`, `.setup-jail`, `.setup-bewerbung` senden die Panels.
- `.adduser @User` fügt im Ticket-Kanal einen Nutzer hinzu.
- `.delete` fordert eine Bestätigung an und erstellt vor dem Löschen ein Transcript.
- `.transcript` (Admin) erstellt ein Transcript des aktuellen Textkanals und sendet es in `CHANNEL_TRANSCRIPT_LOG_CHANNEL_ID` (0 = `TRANSCRIPT_LOG_CHANNEL_ID`).

Level-System:

- `.rank [Mitglied]`, `.leaderboard` zeigen Karten.
- `.xp add|remove`, `.xprise <prozent> <dauer> [text|voice]` (Boost, `status`/`stop`), `.level-config show` sind Admin-Befehle.

Invite-Tracker:

- `.invites [Nutzer]`, `.invite-leaderboard`, `.invitedby [Nutzer]` zeigen Invite-Statistiken.
- Beitritte werden in `INVITE_LOG_CHANNEL_ID` gemeldet (0 = aus), getrennt vom Member-Log des Server-Logs.

Server-Log:

- `.unlog` (Administrator) schaltet das Log für gelöschte/bearbeitete Nachrichten im aktuellen Kanal (inkl. seiner Threads) aus; erneutes `.unlog` schaltet es wieder ein. Der Bot löscht den Befehl (ohne ihn zu loggen), die Antwort verschwindet nach `UNLOG_REPLY_SECONDS`. Beitritte, Kicks und Banns sind nicht betroffen.

## Änderungsregeln

- Bestehende APIs und die Konfiguration in `config.py` beibehalten; keine zweite Config oder zweiten Bot anlegen, neue Funktionen als Cog-Paket ergänzen und in `bot.py` laden.
- Keine echten Tokens oder Serverdaten in Dateien eintragen.
- Datenbanken nie löschen oder überschreiben; Änderungen am Speicher (Ticket, Level, Invites oder Server-Log) mit einem isolierten SQLite-Test auf einer Kopie prüfen.
- Vor dem Abschluss mindestens den Syntaxcheck ausführen.
