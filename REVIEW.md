# Code-Review: Luna

Stand: 18.11.2026 · Branch `test` (Commit `e2b7e17`) · Beim Review wurde nur gelesen, keine Datei außer dieser geändert.

## Umfang

Geprüft: `bot.py`, `config.py`, `requirements.txt`, `.gitignore`, `ticket_system/`, `leveling/` (inkl. `tools/`), `invite_tracker/`, `server_log/` und die Git-History.

Dein Prüfauftrag nennt auch Module, die es in luna nicht gibt:

| Aus dem Auftrag | In luna | Wie geprüft |
| --- | --- | --- |
| Jail | Kein Jail-Befehl, nur Jail-**Tickets** (`support_jail`) | Beim Ticket-System mitgeprüft. Rollen speichern/wiederherstellen und „Mods jailen“ gibt es hier nicht. |
| Stats | Gibt es nicht | Die Voice-Fragen (AFK, Mute, Bots, Neustart) habe ich bei den Voice-XP im Leveling geprüft. |
| Counting, Temp Voice | Liegen im Projekt `artemis` | Nicht geprüft (du wolltest nur luna). |

## 1. Kurzfazit

Luna ist insgesamt ordentlich gebaut: Alle Module nutzen aiosqlite mit einer festen Verbindung, alle SQL-Abfragen sind parametrisiert, Bilder werden in einem Thread gerendert, und der Token liegt sicher in der nicht eingecheckten `.env`. Kritische Probleme habe ich nicht gefunden. Die größten Baustellen sind das Ticket-System, das Fehler beim Erstellen und Löschen oft verschluckt und Tickets mit von Hand gelöschtem Kanal für immer als offen zählt, sowie zwei Datenbanken mit Nutzerdaten, die auf GitHub liegen. Der Server-Log verpasst nach einem Neustart gelöschte Nachrichten und fragt das Audit-Log bei jeder Rollenänderung per API ab. Leveling und Invite-Tracker sind die saubersten Module und eignen sich als Vorlage für den Rest.

## 2. Findings

**Schwere:** Kritisch = Datenverlust, Sicherheitslücke oder der ganze Bot fällt aus · Hoch = Nutzer sind dauerhaft betroffen oder Daten liegen offen · Mittel = eine Funktion versagt in realistischen Fällen · Niedrig = Code-Qualität, Absicherung, Kleinigkeiten.

**Kritisch:** keine.

| # | Schwere | Datei:Zeile | Problem | Warum schlimm | Fix-Vorschlag |
| --- | --- | --- | --- | --- | --- |
| 1 | Hoch (Kritisch, falls das Repo öffentlich ist) | `.gitignore:6`, `data/tickets.sqlite3`, `data/leveling.sqlite3` | Ticket- und Level-Datenbank sind in Git eingecheckt und liegen auf GitHub (`kuroki108/luna`). Ignoriert wird nur `invites.sqlite3`. | Die Ticket-DB enthält Bewerbungsantworten (Alter, Motivation), die Level-DB 74 Nutzer-IDs. Ist das Repo öffentlich, kann sie jeder herunterladen. Außerdem kann ein `git pull` auf dem Server die echte DB löschen oder mit einer alten Version überschreiben. Ob das Repo öffentlich ist, konnte ich nicht prüfen. | Erst Backup, dann `data/*.sqlite3*` in `.gitignore` und `git rm --cached` (Details unten, Vorsicht beim Pull auf dem Server). |
| 2 | Hoch | `ticket_system/storage.py:153-158`, `ticket_system/ticket_manager.py:174` | Ein Ticket wird nur aus der DB entfernt, wenn es über den Bot gelöscht wird. Löscht jemand den Kanal von Hand, bleibt der Eintrag als „offen“ stehen (`closed` wird nie gesetzt). | Das Ticket-Limit zählt diese Geister-Tickets mit. Nach 3 von Hand gelöschten Tickets kann der Nutzer **nie wieder** ein Support-Ticket öffnen und liest „Du hast bereits zu viele offene Tickets“. | Listener `on_guild_channel_delete` löscht den Eintrag. Beim Start einmal alle Tickets mit den existierenden Kanälen abgleichen (`store.all_tickets()` gibt es schon). |
| 3 | Mittel | `ticket_system/ticket_manager.py:80-121` | Race Condition beim Ticket-Limit: Die Prüfung zählt Zeilen in der DB, die Zeile wird aber erst nach `create_text_channel` geschrieben. | Klickt jemand schnell mehrmals, sieht jeder Klick „0 offene Tickets“, und es entstehen mehr Tickets als erlaubt. Das ist eine Spam-Lücke. | Pro Nutzer ein `asyncio.Lock` um Prüfen, Kanal erstellen und Speichern. |
| 4 | Mittel | `ticket_system/views.py:21-41`, `ticket_system/modals.py:12-34`, `ticket_system/views.py:147` | Schlägt `create_text_channel` fehl (Kategorie voll mit max. 50 Kanälen, fehlende Rechte), wird die Exception nicht abgefangen. Gleiches gilt für `set_permissions` bei „Add User“. | Der Nutzer sieht „Luna denkt nach…“ und dann einen Interaktionsfehler. Er weiß nicht, was los ist, und das Team erfährt es nur aus der Konsole. | `try/except discord.HTTPException`, Fehlermeldung per `interaction.followup.send(..., ephemeral=True)`, dazu `log.exception(...)`. |
| 5 | Mittel | `ticket_system/ticket_manager.py:161-172`, `ticket_system/views.py:172-173`, `ticket_system/commands.py:61-66` | `delete_ticket` bricht still ab, wenn der Log-Kanal fehlt oder das Transcript nicht gesendet werden kann (z. B. Datei größer als das Upload-Limit). `.transcript` fängt nur `Forbidden` ab. | Der Nutzer sieht „🗑️ Ticket wird gelöscht…“, aber nichts passiert. Das Team löscht den Kanal dann von Hand, und es entsteht ein Geister-Ticket (#2). | `delete_ticket` gibt zurück, ob es geklappt hat, und der Button meldet einen Fehler. In `.transcript` auch `discord.HTTPException` abfangen. |
| 6 | Mittel | `ticket_system/transcript.py:91-97` | Das Transcript verlinkt Anhänge nur über ihre Discord-CDN-URL. | Discord-Anhang-Links sind signiert und laufen nach etwa 24 h ab. Nach dem Löschen des Kanals lassen sie sich nicht mehr erneuern. Screenshots in Report-Tickets (Beweise) fehlen im Transcript dann. | Anhänge beim Erstellen herunterladen (`await att.read()`) und als Base64 ins HTML einbetten oder als Dateien mitschicken. Upload-Limit beachten. |
| 7 | Mittel | `server_log/log.py:128-172`, `bot.py:31-35` | `on_message_delete`/`on_message_edit` kommen nur für Nachrichten im Cache des Bots (Standard: die letzten 1000, nach einem Neustart leer). Bulk-Löschungen (Purge) lösen `on_message_delete` gar nicht aus. | Nach jedem Neustart und auf einem aktiven Server schon nach kurzer Zeit landen gelöschte oder bearbeitete ältere Nachrichten nicht im Log. Gepurgte Nachrichten nie. Beim Moderieren fehlt dann der Beweis. | Zusätzlich `on_raw_message_delete`, `on_raw_bulk_message_delete` und `on_raw_message_edit` nutzen („Inhalt nicht im Cache“ + Kanal + ID). Optional `max_messages=5000` im Bot. |
| 8 | Mittel | `server_log/log.py:239-256`, `server_log/log.py:283-319`, `server_log/log.py:330-338` | Bei jedem Kick, Bann und jeder Rollenänderung wartet der Bot 1 s und fragt dann das Audit-Log per API ab. Beim Bann fehlt die Zeitprüfung. | Bei vielen Änderungen auf einmal (Level-Rollen-Abgleich beim Start, ein Bot vergibt Rollen) entstehen hunderte API-Calls. Das Rate-Limit greift und das Log hängt minutenlang hinterher. Kommt der Audit-Eintrag später als nach 1 s, wird ein Kick als „verlassen“ geloggt. Beim Bann kann ein älterer Eintrag den falschen Moderator anzeigen. Ein Bann erscheint zusätzlich als „Mitglied verlassen“. | Auf das Event `on_audit_log_entry_create` umstellen: Discord schickt den Eintrag selbst, ohne Abfragen, ohne `sleep` und mit exakter Zuordnung. |
| 9 | Mittel | `requirements.txt:1`, `server_log/log.py:31-65` | `requirements.txt` erlaubt `discord.py>=2.4`, das Rollen-Log nutzt aber `LayoutView`, `Container` und `TextDisplay`, die es erst ab discord.py 2.6 gibt. | Ist irgendwo eine ältere Version installiert, upgradet `pip install -r requirements.txt` nicht, weil die Bedingung erfüllt ist. Dann wirft jede Rollenänderung einen `AttributeError` und das Rollen-Log fällt still aus. Lokal ist 2.7.1 installiert, hier also kein akutes Problem. | `discord.py>=2.6,<3` eintragen. |
| 10 | Niedrig | `bot.py:73-81` | `on_command_error` behandelt nur fehlende Rechte. Fehlende Argumente (`.adduser` ohne Nutzer), unbekannte Mitglieder oder `guild_only` in DMs landen bei `raise error`. | Der Nutzer bekommt keine Antwort, im Log steht nur ein Traceback. Leveling und Invite-Tracker lösen das mit `cog_command_error` schon richtig. | `MissingRequiredArgument`, `BadArgument` und `NoPrivateMessage` mit kurzer Meldung beantworten. Den Rest mit `log.error(..., exc_info=error)` loggen statt `raise`. |
| 11 | Niedrig | `bot.py:31-35`, `ticket_system/ticket_manager.py:51-56` | Der Bot hat kein globales `allowed_mentions`. | Aktuell kann niemand über den Bot @everyone pingen: Nutzertext landet nur in Embeds, und Embeds pingen nie. Kommt später eine Nachricht mit Nutzertext im `content` dazu, wäre @everyone sofort möglich. | Im Konstruktor `allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True)` setzen und beim Ticket-Öffnen die Staff-Rolle gezielt erlauben. |
| 12 | Niedrig | `invite_tracker/invites.py:458-461` | Nach einem Neustart werden nur die Invites neu geladen. Die Mitglieder werden nicht abgeglichen. | Wer gegangen ist, während der Bot offline war, zählt weiter als „aktiv“. `.invites` und das Invite-Leaderboard zeigen dann zu hohe Zahlen. | In `on_ready` für alle Joins mit `left_at IS NULL` prüfen, ob das Mitglied noch da ist, sonst `mark_left`. |
| 13 | Niedrig | `invite_tracker/invites.py:398-433` | Jeder Beitritt ruft 1–2× alle Invites ab und wartet dabei bis zu 1,5 s, unter einem Lock pro Server. | Bei einem Raid stauen sich die Auswertungen, und Invite-Log und Join-Log kommen stark verzögert. Im Normalbetrieb kein Problem, die Logik ist bewusst so gebaut. | Erst einmal nur beobachten. Falls es stört: Ab X Beitritten pro Minute direkt „unbekannt“ eintragen. |
| 14 | Niedrig | `leveling/leveling.py:157-162` | Jede Nachricht löst einen DB-Schreibversuch aus, auch während der Cooldown noch läuft (das entscheidet erst die DB). | Bei der aktuellen Servergröße kein Problem. Auf sehr aktiven Servern wäre das unnötige DB-Last. | Optional: Den Zeitpunkt der letzten XP pro Nutzer zusätzlich in einem `dict` halten und die DB erst nach Ablauf des Cooldowns ansprechen. |
| 15 | Niedrig | `bot.py:52-59` | Bei jedem Start werden Slash-Commands synchronisiert, obwohl es keine gibt. | Das ist bei jedem Start ein unnötiger, rate-limitierter API-Call. | Den Block entfernen, solange es keine Slash-Commands gibt. |
| 16 | Niedrig | `bot.py:61-63` | `close()` schließt die Ticket-DB vor `super().close()`. | Beim Herunterfahren ist das Gateway noch kurz offen. Ein Button-Klick in diesem Moment trifft auf die geschlossene DB und löst einen `RuntimeError` aus. Das passiert sehr selten. | Erst `await super().close()`, dann `await ticket_store.close()`. |
| 17 | Niedrig | `bot.py:68-71` | In `on_ready` wird zusätzlich zum Logging `print()` benutzt. | Die Ausgabe erscheint doppelt. `print` hat keinen Zeitstempel und landet in keinem Log-Handler. `on_ready` kann nach Reconnects mehrfach kommen. | Die `print`-Zeilen streichen, `log.info` reicht. |
| 18 | Niedrig | `ticket_system/storage.py:22`, `:46`, `:174`, `:191`, `ticket_system/panels.py:58-59` | Toter Code: `TicketData.closed` wird nie auf `True` gesetzt. `bind()`, `next_counter()`, `all_tickets()` und `panels.setup()` werden nirgends aufgerufen. | Toter Code führt in die Irre, z. B. denkt man, es gäbe „geschlossene“ Tickets. | Entfernen oder benutzen (`all_tickets()` für #2). |
| 19 | Niedrig | `ticket_system/embed_builder.py:29-67`, `:92`, `:131`, `:146`, `:164` u. a., `bot.py:32` | Emoji-IDs stehen fest im Code statt in `config.py` (dort gibt es schon `EMOJI_*`). Auch der Prefix `"."` steht direkt in `bot.py`. | Wird ein Emoji gelöscht oder ersetzt, musst du viele Stellen suchen. | Konstanten wie `EMOJI_TITLE`, `EMOJI_BULLET` und `COMMAND_PREFIX` in `config.py` anlegen. |
| 20 | Niedrig | `leveling/formatting.py:15-18` ↔ `invite_tracker/invites.py:49-52`; `leveling/leveling.py:26`, `:129-134` ↔ `invite_tracker/invites.py:35`, `:307-312`; `invite_tracker/invites.py:276` ↔ `server_log/log.py:27`; `ticket_system/embed_builder.py:181-260` | Doppelter Code: `reply`/`NO_PINGS`, `WrongGuild` + `cog_check`, `_is_tracked`, der Verbindungs-Code in drei DB-Klassen und fünf fast gleiche Willkommens-Embeds. | Einen Bugfix musst du dann an mehreren Stellen machen und vergisst dabei leicht eine. | Gemeinsames Paket `core/` (siehe Architektur). Die Willkommens-Embeds über eine Funktion mit Titel-Parameter bauen. |
| 21 | Niedrig | `bot.py:73`, `ticket_system/views.py:193`, `ticket_system/embed_builder.py:143`, `:159`, `ticket_system/storage.py:8` | Uneinheitliche Type Hints: `on_command_error(self, ctx, error)` und `application_panel(ctx)` sind ohne Typen, `Optional[...]` steht neben `X \| None`, und der Name `application_panel_Anforderungen` mischt Groß- und Kleinschreibung. | Das ist kein Fehler, aber dein Editor kann so weniger prüfen und vorschlagen. | Überall `X \| None` schreiben, Parameter typisieren, Namen in `snake_case`. |
| 22 | Niedrig | `leveling/database.py:43`, `ticket_system/storage.py:55-75`, `invite_tracker/database.py:17-44`, `server_log/database.py:14-21` | Es gibt keine Schema-Migrationen: `CREATE TABLE IF NOT EXISTS` fügt später keine neuen Spalten hinzu. Leveling setzt `user_version`, liest den Wert aber nie aus. | Brauchst du später eine neue Spalte, startet der Bot mit der alten DB und stürzt bei der ersten Abfrage ab. | `PRAGMA user_version` auslesen und die Migrationsschritte nacheinander ausführen (Vorlage im Architektur-Teil). |
| 23 | Niedrig (unsicher) | `ticket_system/panels.py:14-55`, `ticket_system/commands.py:17-70` | Das Ticket-System prüft nicht, auf welchem Server es läuft. | Relevant nur, wenn der Bot im Developer Portal als „Public Bot“ eingestellt ist. Dann könnte jeder ihn einladen, Panels posten und Einträge in deine Ticket-DB schreiben. Die Einstellung konnte ich nicht prüfen. | Im Developer Portal „Public Bot“ ausschalten. Optional einen Check auf `GUILD_ID` und den Entbannungsserver einbauen. |

### Erklärungen zu den Findings mit Schwere Hoch und Mittel

**#1 Datenbanken in Git.** Git speichert jede Version jeder eingecheckten Datei für immer, auch alte Stände. Lokal enthält `tickets.sqlite3` 3 Tickets, 2 davon mit Bewerbungsantworten, und `leveling.sqlite3` 74 Nutzer. So behebst du das:

1. Kopiere `data/` als Backup an einen Ort **außerhalb** des Projekts.
2. Ergänze `.gitignore` um `data/*.sqlite3`, `data/*.sqlite3-wal` und `data/*.sqlite3-shm`.
3. Führe `git rm --cached data/tickets.sqlite3 data/leveling.sqlite3` aus. `--cached` nimmt die Dateien nur aus Git, die Dateien auf deiner Platte bleiben.
4. **Achtung:** Auf jedem anderen Rechner (z. B. dem Server, auf dem der Bot läuft), der diesen Commit pullt, löscht Git die Datei oder bricht den Pull ab. Mach dort vorher ein Backup und spiel es danach zurück.
5. Die alten Stände bleiben in der History. Ist das Repo öffentlich, stell es auf privat. Die History zu bereinigen (`git filter-repo`) ist aufwendig und nur nötig, wenn das Repo öffentlich war.

**#2 Geister-Tickets.** Der Bot erfährt nur von Löschungen, die er selbst macht. Wenn ein Teammitglied den Kanal per Rechtsklick löscht, bleibt die Zeile mit `closed = 0` in der DB. `reserve_ticket_slot` zählt sie bei jedem neuen Versuch mit. Lösung in zwei Teilen:

```python
@commands.Cog.listener()
async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
    await ticket_store.delete_ticket(channel.id)  # tut nichts, wenn es kein Ticket war
```

Dazu kommt ein Abgleich beim Start: Für jedes Ticket aus `all_tickets()` prüfen, ob `bot.get_channel(ticket.channel_id)` noch existiert. **Vorsicht:** Nur aufräumen, wenn alle Server verfügbar sind (`not guild.unavailable`), sonst löscht ein kurzer Discord-Ausfall echte Tickets.

**#3 Race Condition.** Eine Race Condition entsteht, wenn zwei Abläufe gleichzeitig laufen und das Ergebnis davon abhängt, wer zuerst fertig ist. Bei jedem `await` darf asyncio etwas anderes dazwischenschieben:

```
Klick 1: Limit prüfen (0 offen) ── Kanal erstellen … (wartet auf Discord) ── speichern
Klick 2:        Limit prüfen (immer noch 0 offen!) ── Kanal erstellen … ── speichern
```

Der Lock in `TicketStore` schützt nur die Prüfung selbst, nicht die Zeit danach, bis gespeichert wird. Ein Lock pro Nutzer um den ganzen Ablauf behebt das:

```python
_user_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

async with _user_locks[member.id]:
    number = await store.reserve_ticket_slot(...)
    channel = await guild.create_text_channel(...)
    await store.save_ticket(...)
```

**#4 Fehler beim Ticket-Erstellen.** `interaction.response.defer(thinking=True)` verspricht Discord: „Ich antworte gleich.“ Kommt danach kein `followup.send`, bleibt die Anzeige hängen. Eine Kategorie fasst höchstens 50 Kanäle. Bei viel Support ist das realistisch, und dann schlägt **jede** Ticket-Erstellung fehl, ohne dass es jemand merkt.

```python
except discord.HTTPException:
    log.exception("Ticket für %s konnte nicht erstellt werden", interaction.user.id)
    await interaction.followup.send(
        "Das Ticket konnte gerade nicht erstellt werden. Bitte melde dich beim Team.", ephemeral=True
    )
    return
```

**#5 Stilles Abbrechen beim Löschen.** `delete_ticket` macht bei einem Fehler nur `return`. Der Button hat vorher aber schon „wird gelöscht…“ angezeigt. Besser ist, dass `delete_ticket` `True` oder `False` zurückgibt und der Button bei `False` per `interaction.followup.send(...)` meldet: „Transcript fehlgeschlagen, Ticket bleibt bestehen.“ So löscht niemand mehr von Hand, und #2 entsteht seltener.

**#6 Ablaufende Anhang-Links.** Discord hängt an Anhang-URLs Parameter wie `?ex=…&is=…&hm=…` an. Das ist eine Signatur mit Ablaufdatum. Solange die Nachricht existiert, erneuert Discord den Link. Ist der Ticket-Kanal gelöscht, geht das nicht mehr. Dein Transcript ist dann nur noch Text ohne Bilder.

**#7 Nachrichten-Cache.** discord.py merkt sich standardmäßig nur die letzten 1000 Nachrichten, und zwar im Arbeitsspeicher. `on_message_delete` liefert dir die alte Nachricht aus diesem Cache. Ist sie nicht drin (älter oder vor dem Neustart geschrieben), wird das Event gar nicht ausgelöst. Die `on_raw_*`-Events kommen **immer**. Sie enthalten nur die IDs, und `payload.cached_message` ist gesetzt, falls die Nachricht doch im Cache war.

**#8 Audit-Log-Polling.** Polling heißt: Du fragst immer wieder nach, ob etwas passiert ist. Das kostet API-Calls, und du musst raten, wie lange du warten sollst (hier 1 s). Mit `on_audit_log_entry_create` schickt Discord dir jeden neuen Audit-Eintrag selbst (Kick, Bann, Rollenänderung, inklusive Moderator und Grund). Voraussetzungen: „Audit-Log anzeigen“ (hat der Bot laut CLAUDE.md) und der Moderation-Intent (ist in `Intents.default()` schon an). `entry.user` kann `None` sein, `entry.user_id` ist immer gesetzt. Das ist der größte Umbau in dieser Liste, deshalb lieber als eigenen Schritt planen.

**#9 Versionsgrenze.** `>=2.4` sagt pip: „Alles ab 2.4 ist okay.“ Ist 2.5 installiert, macht pip nichts. Die Untergrenze sollte immer die älteste Version sein, mit der dein Code wirklich läuft.

### Geprüft und in Ordnung

Diese Punkte aus deinem Auftrag habe ich geprüft und kein Problem gefunden:

- **Token und Secrets:** `.env` steht in `.gitignore` und war nie in Git. In der ganzen History gibt es keinen String, der wie ein Discord-Token aussieht. Die IDs in `config.py` sind keine Geheimnisse.
- **SQL-Injection:** Alle Abfragen nutzen `?`-Platzhalter. Der einzige f-String in SQL (`invite_tracker/database.py:148-152`) fügt nur Platzhalter ein, keine Werte, und ist damit sicher.
- **Blockierende Aufrufe:** Im Bot gibt es kein synchrones `sqlite3` (nur im Offline-Skript `leveling/tools/set_level.py`, das ist okay) und kein `time.sleep`. Pillow läuft über `asyncio.to_thread` (`leveling/display.py:73`, `:100`, `:110`).
- **DB-Verbindungen:** Jedes Modul hat genau eine Verbindung, die im `cog_load`/`connect` geöffnet und im `cog_unload`/`close` geschlossen wird. WAL ist überall an.
- **Mehrere `on_message`:** Nur Leveling hat einen `on_message`-Listener. Das Standard-`on_message` des Bots ruft weiter `process_commands` auf, sie stören sich also nicht. Commands geben keine XP (`ctx.valid`, `leveling/leveling.py:153-155`).
- **Intents:** `members`, `message_content` und `voice_states` werden gebraucht. `invites` und `moderation` sind über `Intents.default()` an, `presences` ist zu Recht aus. `bot.py:27` ist überflüssig, weil `voice_states` schon in `default()` steckt, schadet aber nicht.
- **allowed_mentions:** Die Antwort-Helfer und Logs pingen nicht (`AllowedMentions.none()`), die Levelup-Nachricht pingt nur den Nutzer. Den Rest siehe #11.
- **Leveling:** Der Cooldown wird atomar in der DB geprüft, überlebt also einen Neustart und hat keine Race Condition. Bots, Webhooks und No-XP-Kanäle bekommen nichts. Vor dem Vergeben von Level-Rollen prüft der Code die Rollenhierarchie (`role.is_assignable()`) und „Rollen verwalten“ und warnt im Log. XP-Boosts stehen in der DB und überleben einen Neustart. Die Level-Kurve wird beim Start validiert.
- **Voice-XP (dein Punkt „Stats“):** AFK-Kanal, stummgeschaltete und taube Nutzer sowie Bots sind ausgeschlossen, und es braucht mindestens 2 berechtigte Personen im Kanal. Weil jede Minute neu gezählt wird, geht bei einem Neustart höchstens eine Minute verloren, und es bleibt kein halber Zustand zurück.
- **Persistente Buttons:** Alle Ticket-Panels und -Buttons haben feste `custom_id`s und werden in `setup_hook` registriert. Sie funktionieren also auch nach einem Neustart.
- **Berechtigungen:** `.setup-*` und `.unlog` brauchen Administrator, `.xp`, `.xprise` und `.level-config` brauchen „Server verwalten“, `.transcript` braucht Admin. Für `.adduser`, `.delete` und die Ticket-Buttons prüft der Code das Team des Ticket-Typs, und die Lösch-Bestätigung darf nur der Anfragende drücken.

## 3. Top 5: Was du zuerst fixen solltest

1. **#1 Datenbanken aus Git nehmen.** Es geht um Datenschutz, und jeder weitere Commit oder Pull kann Live-Daten überschreiben. Der Fix dauert rund 10 Minuten, aber mach unbedingt vorher ein Backup.
2. **#2 Geister-Tickets aufräumen.** Das betrifft echte Nutzer dauerhaft, und sie bekommen eine falsche Meldung. Der Fix ist klein (ein Listener plus Abgleich beim Start, `all_tickets()` gibt es schon).
3. **#4 + #5 Fehler beim Erstellen und Löschen melden.** Beide führen dazu, dass Nutzer und Team nicht wissen, was los ist, und #5 erzeugt indirekt neue Geister-Tickets. Es sind jeweils nur ein paar Zeilen `try/except`.
4. **#3 Race beim Ticket-Limit.** Ohne Fix lässt sich das Limit umgehen, mit einem Lock pro Nutzer ist es behoben.
5. **#7 Server-Log mit Raw-Events.** Sonst fehlen nach jedem Neustart und bei jedem Purge genau die Nachrichten, die du beim Moderieren brauchst. **#9** kannst du nebenbei mitnehmen, das ist eine Zeile.

## 4. Architektur-Vorschlag

Die Grundstruktur passt schon: ein Bot, eine Config, ein Paket pro Feature. Ich würde sie nicht umwerfen, sondern in kleinen Schritten ergänzen:

```
luna/
├── bot.py                 # nur Start, Intents, allowed_mentions, lädt alle Extensions
├── config.py              # alle IDs, Emojis, Prefix
├── core/                  # NEU: Code, den mehrere Module brauchen
│   ├── __init__.py
│   ├── database.py        # BaseDatabase: connect/close/conn, WAL, busy_timeout, Migrationen
│   ├── checks.py          # WrongGuild, main_guild_only(), is_main_guild()
│   ├── messages.py        # reply(), NO_PINGS, warn_once()
│   └── errors.py          # gemeinsame Fehlertexte für cog_command_error
├── ticket_system/         # wie die anderen als Extension laden (setup()), kein globales `store`
├── leveling/
├── invite_tracker/
├── server_log/
├── tests/                 # NEU: pytest für reine Logik, braucht kein Discord
│   ├── test_leveling_math.py
│   ├── test_invite_cache.py
│   └── test_duration.py
├── data/                  # nur lokal, komplett in .gitignore
└── requirements.txt
```

**Warum `core/`?** Heute haben drei DB-Klassen fast denselben `connect`/`close`-Code, zwei Cogs dieselbe `WrongGuild`-Prüfung und zwei Module denselben `reply`-Helfer. Liegt das an einer Stelle, behebst du einen Fehler einmal statt dreimal. Eine Basisklasse für die DB könnte so aussehen:

```python
class BaseDatabase:
    SCHEMA: str = ""
    MIGRATIONS: list[str] = []  # MIGRATIONS[0] bringt Version 0 auf 1 usw.

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError(f"{type(self).__name__} ist nicht verbunden.")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(self.SCHEMA)
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self) -> None:
        async with self.conn.execute("PRAGMA user_version") as cur:
            (version,) = await cur.fetchone()
        for step, sql in enumerate(self.MIGRATIONS[version:], start=version + 1):
            await self.conn.executescript(sql)
            await self.conn.execute(f"PRAGMA user_version={step}")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
```

`LevelingDatabase`, `InviteDatabase`, `ServerLogDatabase` und `TicketStore` erben davon und enthalten nur noch ihre eigenen Abfragen.

**Warum Tests?** `leveling_math.py`, `InviteCache` und der `Duration`-Converter sind reine Logik ohne Discord. Genau solche Funktionen lassen sich am leichtesten testen, und ein Test merkt sofort, wenn eine Änderung an der Level-Kurve plötzlich alle Level verschiebt.

**Empfohlene Reihenfolge:** Erst die Top 5 fixen, dann `core/messages.py` und `core/checks.py` (klein, sofort weniger doppelter Code), danach `core/database.py` und zuletzt die Tests.
