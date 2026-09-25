# Luna Projektanweisungen

## Projekt

Luna ist ein Python-Discord-Bot mit einem Ticket-System. Der Einstiegspunkt ist `bot.py`; der fachliche Kern liegt in `ticket_system/` und verwendet SQLite über `aiosqlite`.

## Umgebung

- Python-Umgebung: `env/`
- Abhängigkeiten: `requirements.txt`
- Datenbank: `data/tickets.sqlite3`
- Discord-Token: Umgebungsvariable `DISCORD_TOKEN`

## Prüfen und Starten

```powershell
env\Scripts\python.exe -m compileall -q bot.py config.py ticket_system
env\Scripts\python.exe -m pip check
env\Scripts\python.exe bot.py
```

Im Ticket-Kanal stehen diese Prefix-Commands zur Verfügung:

- `,adduser @User` fügt einen Nutzer hinzu.
- `,delete` fordert eine Bestätigung an und erstellt vor dem Löschen ein Transcript.

Der letzte Befehl startet den Bot mit dem konfigurierten Discord-Token und benötigt eine Netzwerkverbindung. Für lokale Änderungen am Speicher kann eine temporäre SQLite-Datei verwendet werden.

## Änderungsregeln

- Bestehende APIs und die Konfiguration in `config.py` beibehalten.
- Keine echten Tokens oder Serverdaten in Dateien eintragen.
- Änderungen am Ticket-Speicher mit einem isolierten SQLite-Test prüfen.
- Vor dem Abschluss mindestens den Syntaxcheck ausführen.