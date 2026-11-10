"""SeydaAI auf Cloudflare verwalten. Wird von einrichten.ps1 aufgerufen, geht aber auch direkt:

  python cloud.py datenbank                 legt die Datenbank in der EU an (falls noch nicht da),
                                            trägt sie in wrangler.jsonc ein und richtet die Tabellen ein
  python cloud.py hochladen                 lädt die eingelesenen Texte aus seyda.db nach Cloudflare
  python cloud.py stand                     zeigt, wann zuletzt hochgeladen wurde und wie viele Abschnitte
  python cloud.py zugang neu "Ayse K" 10    legt einen Zugang mit 10 Fragen pro Tag an und zeigt den Code einmal an
  python cloud.py zugang liste              zeigt alle Zugänge und die Fragen von heute
  python cloud.py zugang sperren "Ayse K"   sperrt den Zugang und meldet die Person überall ab
  python cloud.py zugang loeschen "Ayse K"  löscht den Zugang
  python cloud.py meldungen                 zeigt die über "Antwort melden" gespeicherten Antworten
  python cloud.py meldungen loeschen ZEIT   löscht alle Meldungen bis zu diesem Zeitpunkt (UTC, wie angezeigt)

Alles läuft über wrangler mit deiner eigenen Cloudflare Anmeldung (npx wrangler login).
Mit --lokal statt --remote wirkt alles auf die Testdatenbank von "wrangler dev" auf diesem Rechner.
"""

import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
from datenbank import CODE_LAENGE, CODE_ZEICHEN, DB_PFAD, _pruefwert, name_gueltig, quellen_laden  # noqa: E402

KONFIG = HIER / "wrangler.jsonc"
PLATZHALTER = "noch-nicht-angelegt"
DB_NAME = "seyda"
ORDNER = HIER / "hochladen"
MAX_ANWEISUNG = 90_000      # D1 erlaubt höchstens 100 KB je SQL Anweisung
MAX_DATEI = 2_000_000       # kleine Teile, weil sehr große Dateien beim Hochladen abbrechen können
STANDARD_LIMIT = 10

SPALTEN_FTS = """CREATE VIRTUAL TABLE abschnitte USING fts5(
    text, titel, url UNINDEXED, quelle UNINDEXED, nur_zusammenfassen UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);"""


class Fehler(Exception):
    pass


def wrangler(argumente: list[str], erfassen: bool = True, ci: bool = False) -> subprocess.CompletedProcess:
    """Ruft wrangler direkt mit node auf (nicht über npx.cmd), damit Windows nichts an den Argumenten verändert."""
    befehl = os.environ.get("SEYDA_WRANGLER")  # nur für Tests: ein anderes Programm statt wrangler
    if befehl:
        aufruf = [sys.executable, befehl]
    else:
        node = shutil.which("node")
        skript = HIER / "node_modules" / "wrangler" / "bin" / "wrangler.js"
        if not node:
            raise Fehler("Node.js fehlt. Bitte zuerst Cloudflare_einrichten.bat ausführen.")
        if not skript.is_file():
            raise Fehler("wrangler fehlt. Bitte zuerst Cloudflare_einrichten.bat ausführen (installiert es).")
        aufruf = [node, str(skript)]
    umgebung = {**os.environ, "WRANGLER_SEND_METRICS": "false", "NO_COLOR": "1", "FORCE_COLOR": "0"}
    if ci:
        umgebung["CI"] = "1"  # Rückfragen von wrangler automatisch mit Ja beantworten
    return subprocess.run(
        aufruf + argumente, cwd=HIER, env=umgebung, capture_output=erfassen,
        text=True, encoding="utf-8", errors="replace",
    )


def json_aus(ausgabe: str):
    """wrangler schreibt manchmal Hinweise vor das JSON. Nimmt das JSON ab der ersten Klammer."""
    for i, z in enumerate(ausgabe):
        if z in "[{":
            try:
                return json.loads(ausgabe[i:])
            except json.JSONDecodeError:
                continue
    raise Fehler("Die Antwort von wrangler war nicht lesbar:\n" + ausgabe[-1500:])


def ausfuehren(sql: str, ziel: str) -> list:
    """Eine oder mehrere SQL Anweisungen (getrennt mit ;) über die Abfrageschnittstelle, Ergebnis als Liste."""
    r = wrangler(["d1", "execute", DB_NAME, ziel, "--json", "--command", sql])
    if r.returncode != 0:
        raise Fehler((r.stdout + r.stderr).strip()[-2000:] or "wrangler meldet einen Fehler.")
    daten = json_aus(r.stdout)
    return daten if isinstance(daten, list) else [daten]


def zeilen(ergebnis: list, nummer: int = 0) -> list[dict]:
    try:
        return ergebnis[nummer].get("results") or []
    except (IndexError, AttributeError):
        return []


def sql_text(wert) -> str:
    if wert is None:
        return "NULL"
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return str(int(wert))
    return "'" + str(wert).replace("\x00", "").replace("'", "''") + "'"


def konfig_lesen() -> str:
    return KONFIG.read_text(encoding="utf-8")


# ---------- Datenbank anlegen ----------

def datenbank(ziel: str) -> int:
    if ziel == "--remote":
        text = konfig_lesen()
        if PLATZHALTER in text:
            kennung = datenbank_finden()
            if not kennung:
                print("Lege die Datenbank an (Standort EU) ...")
                r = wrangler(["d1", "create", DB_NAME, "--jurisdiction=eu"])
                if r.returncode != 0:
                    print((r.stdout + r.stderr).strip()[-2000:])
                    raise Fehler("Die Datenbank ließ sich nicht anlegen.")
                kennung = datenbank_finden()
            if not kennung:
                raise Fehler("Die neue Datenbank wurde nicht gefunden. Bitte noch einmal starten.")
            # Ohne BOM schreiben, sonst liest wrangler die Datei nicht
            KONFIG.write_bytes(text.replace(PLATZHALTER, kennung).encode("utf-8"))
            print(f"Datenbank {DB_NAME} eingetragen ({kennung}).")
        else:
            print(f"Datenbank {DB_NAME} ist schon eingetragen.")
    print("Richte die Tabellen ein ...")
    r = wrangler(["d1", "migrations", "apply", "DB", ziel], erfassen=False, ci=True)
    if r.returncode != 0:
        raise Fehler("Die Tabellen ließen sich nicht einrichten.")
    return 0


def datenbank_finden():
    r = wrangler(["d1", "list", "--json"])
    if r.returncode != 0:
        print((r.stdout + r.stderr).strip()[-2000:])
        raise Fehler("Die Liste der Datenbanken ließ sich nicht abrufen. Bist du mit npx wrangler login angemeldet?")
    for eintrag in json_aus(r.stdout):
        if isinstance(eintrag, dict) and eintrag.get("name") == DB_NAME:
            kennung = str(eintrag.get("uuid") or "")
            if re.fullmatch(r"[0-9a-fA-F-]{32,40}", kennung):
                return kennung
    return None


# ---------- Texte hochladen ----------

def dateien_schreiben(pfad: str) -> tuple[list[Path], dict]:
    """Schreibt die Abschnitte aus seyda.db als SQL Dateien in den Ordner hochladen. Gibt Dateien und Zählung zurück."""
    if not os.path.isfile(pfad):
        raise Fehler(f"{pfad} fehlt. Bitte zuerst mit SeydaAI_starten.bat die Quellen einlesen.")
    namen = [q["name"] for q in quellen_laden()]
    con = sqlite3.connect(f"file:{Path(pfad).as_posix()}?mode=ro", uri=True)
    platz = ",".join("?" * len(namen))
    zeilen_db = con.execute(
        f"SELECT rowid, text, titel, url, quelle, nur_zusammenfassen FROM abschnitte "
        f"WHERE quelle IN ({platz}) ORDER BY rowid", namen,
    )
    if ORDNER.exists():
        shutil.rmtree(ORDNER)
    ORDNER.mkdir()
    dateien, zaehlung = [], {}
    # Teil 0: Suchtabelle neu anlegen. Löschen und neu anlegen schreibt viel weniger Zeilen als DELETE.
    erste = ORDNER / "teil_000.sql"
    # Den alten Stand gleich löschen, damit "stand" nach einem Abbruch keinen vollständigen Upload vortäuscht
    erste.write_text("DELETE FROM stand WHERE schluessel IN ('hochgeladen', 'abschnitte');\n"
                     "DROP TABLE IF EXISTS abschnitte;\n" + SPALTEN_FTS + "\n", encoding="utf-8")
    dateien.append(erste)

    kopf = "INSERT INTO abschnitte (rowid, text, titel, url, quelle, nur_zusammenfassen) VALUES\n"
    teil, anweisung, werte = [], [], 0
    groesse_teil = 0

    def anweisung_fertig():
        nonlocal anweisung, groesse_teil
        if anweisung:
            s = kopf + ",\n".join(anweisung) + ";\n"
            teil.append(s)
            groesse_teil += len(s.encode("utf-8"))
            anweisung = []

    def teil_fertig():
        nonlocal teil, groesse_teil
        anweisung_fertig()
        if teil:
            datei = ORDNER / f"teil_{len(dateien):03d}.sql"
            datei.write_text("".join(teil), encoding="utf-8")
            dateien.append(datei)
            teil, groesse_teil = [], 0

    groesse_anweisung = len(kopf)
    for rowid, text, titel, url, quelle, nz in zeilen_db:
        zeile = "(" + ", ".join(sql_text(w) for w in (rowid, text, titel, url, quelle, int(bool(nz)))) + ")"
        laenge = len(zeile.encode("utf-8")) + 2
        if laenge + len(kopf) > MAX_ANWEISUNG:
            print(f"  Abschnitt {rowid} ist zu lang für Cloudflare und wird übersprungen.")
            continue
        if groesse_anweisung + laenge > MAX_ANWEISUNG:
            anweisung_fertig()
            groesse_anweisung = len(kopf)
            if groesse_teil > MAX_DATEI:
                teil_fertig()
        anweisung.append(zeile)
        groesse_anweisung += laenge
        werte += 1
        zaehlung[quelle] = zaehlung.get(quelle, 0) + 1
    teil_fertig()
    con.close()

    # Letzter Teil: Suchindex zusammenfassen (schnellere Suche) und den Stand vermerken
    jetzt = datetime.now(timezone.utc).isoformat(timespec="seconds")
    letzte = ORDNER / f"teil_{len(dateien):03d}.sql"
    letzte.write_text(
        "INSERT INTO abschnitte (abschnitte) VALUES ('optimize');\n"
        f"INSERT OR REPLACE INTO stand (schluessel, wert) VALUES ('hochgeladen', {sql_text(jetzt)});\n"
        f"INSERT OR REPLACE INTO stand (schluessel, wert) VALUES ('abschnitte', "
        f"{sql_text(json.dumps(zaehlung, ensure_ascii=False))});\n",
        encoding="utf-8",
    )
    dateien.append(letzte)
    return dateien, zaehlung


def hochladen(ziel: str) -> int:
    pfad = os.environ.get("SEYDA_DB", DB_PFAD)
    dateien, zaehlung = dateien_schreiben(pfad)
    if not zaehlung:
        raise Fehler("In seyda.db sind noch keine Abschnitte der Quellen. Bitte zuerst einlesen.")
    for quelle, anzahl in zaehlung.items():
        print(f"  {quelle}: {anzahl} Abschnitte")
    print(f"Lade in {len(dateien)} Teilen hoch. Bis es fertig ist, findet SeydaAI nur einen Teil der Texte; "
          "bricht es ab, einfach noch einmal hochladen.")
    geschrieben = 0
    for i, datei in enumerate(dateien, 1):
        print(f"  Teil {i} von {len(dateien)} ...", flush=True)
        for versuch in (1, 2):
            r = wrangler(["d1", "execute", DB_NAME, ziel, "--yes", f"--file={datei}"])
            if r.returncode == 0:
                break
            if versuch == 2:
                print((r.stdout + r.stderr).strip()[-2000:])
                raise Fehler(f"Teil {i} ließ sich nicht hochladen. Einfach noch einmal starten, es beginnt dann von vorn.")
        # Ohne Terminal schreibt wrangler das Ergebnis als JSON ("Rows written": 123), sonst als Satz (123 rows written)
        treffer = re.search(r'"Rows written":\s*(\d+)|([\d,.]+) rows written', r.stdout)
        if treffer:
            geschrieben += int(re.sub(r"\D", "", treffer.group(1) or treffer.group(2)))
    shutil.rmtree(ORDNER, ignore_errors=True)
    print(f"Fertig: {sum(zaehlung.values())} Abschnitte hochgeladen.")
    if geschrieben:
        print(f"Cloudflare hat dabei {geschrieben} Zeilen geschrieben (kostenlos sind 100.000 am Tag).")
    return 0


def stand(ziel: str) -> int:
    ergebnis = ausfuehren("SELECT schluessel, wert FROM stand ORDER BY schluessel", ziel)
    werte = {z["schluessel"]: z["wert"] for z in zeilen(ergebnis)}
    if "hochgeladen" not in werte:
        print("Es wurde noch nichts hochgeladen.")
        return 0
    zeit = datetime.fromisoformat(werte["hochgeladen"]).astimezone()
    print(f"Zuletzt hochgeladen am {zeit.day}.{zeit.month}.{zeit.year} um {zeit:%H:%M} Uhr")
    for quelle, anzahl in json.loads(werte.get("abschnitte", "{}")).items():
        print(f"  {quelle}: {anzahl} Abschnitte")
    return 0


# ---------- Zugänge ----------

def zugang(argumente: list[str], ziel: str) -> int:
    if not argumente or argumente[0] not in ("neu", "liste", "sperren", "loeschen"):
        print(__doc__)
        return 1
    befehl, rest = argumente[0], argumente[1:]

    if befehl == "liste":
        heute = sql_text(date.today().isoformat())
        ergebnis = ausfuehren(
            "SELECT name, tageslimit, aktiv, angelegt, "
            f"(SELECT anzahl FROM fragen_pro_person f WHERE f.name = z.name AND f.tag = {heute}) AS heute "
            "FROM zugaenge z ORDER BY name", ziel,
        )
        liste = zeilen(ergebnis)
        if not liste:
            print("Noch keine Zugänge angelegt.")
        for z in liste:
            zustand = "aktiv" if z.get("aktiv") else "gesperrt"
            tag = datetime.fromisoformat(z["angelegt"]).astimezone()
            print(f"{z['name']}: {zustand}, heute {z.get('heute') or 0} von {z['tageslimit']} Fragen, "
                  f"angelegt am {tag.day}.{tag.month}.{tag.year}")
        return 0

    if not rest:
        print("Bitte einen Namen angeben, zum Beispiel: python cloud.py zugang", befehl, '"Ayse K"')
        return 1
    # Gleiche Schreibweise wie im Worker (zusammengesetzte Zeichen wie ş als ein Zeichen)
    name = unicodedata.normalize("NFC", rest[0])

    if befehl == "neu":
        if len(rest) > 2:
            print('Zu viele Angaben. Namen mit Leerzeichen bitte in Anführungszeichen setzen, zum Beispiel "Ayse K".')
            return 1
        try:
            limit = int(rest[1]) if len(rest) > 1 else STANDARD_LIMIT
        except ValueError:
            print("Nicht angelegt: Das Tageslimit muss eine ganze Zahl sein, zum Beispiel 10.")
            return 1
        if not name_gueltig(name):
            print("Nicht angelegt: Name mit 1 bis 40 Zeichen, nur Buchstaben, Ziffern, Leerzeichen, Punkt und "
                  "Unterstrich, ohne Leerzeichen am Anfang oder Ende, nicht admin.")
            return 1
        if limit < 1:
            print("Nicht angelegt: Das Tageslimit muss mindestens 1 sein.")
            return 1
        aehnlich = zeilen(ausfuehren(f"SELECT name FROM zugaenge WHERE name = {sql_text(name)} COLLATE NOCASE", ziel))
        if aehnlich:
            print(f"Nicht angelegt: Es gibt schon {aehnlich[0]['name']}. Beim Anmelden zählt Groß und Kleinschreibung "
                  "nicht, deshalb bitte einen anderen Namen wählen oder den alten erst loeschen.")
            return 1
        code = "".join(secrets.choice(CODE_ZEICHEN) for _ in range(CODE_LAENGE))
        salz = secrets.token_hex(16)
        jetzt = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            ausfuehren(
                "INSERT INTO zugaenge (name, salz, pruefwert, tageslimit, aktiv, angelegt) VALUES "
                f"({sql_text(name)}, {sql_text(salz)}, {sql_text(_pruefwert(salz, code))}, {limit}, 1, {sql_text(jetzt)})",
                ziel,
            )
        except Fehler as e:
            if "UNIQUE" in str(e):
                print(f"Nicht angelegt: {name} gibt es schon. Für einen neuen Code erst loeschen, dann neu.")
                return 1
            raise
        print(f"Zugang für {name} angelegt, Tageslimit {limit}.")
        print(f"Name: {name}")
        print(f"Code: {code}")
        print("Der Code wird nur jetzt angezeigt und nicht gespeichert. Gib ihn der Person persönlich weiter.")
        return 0

    n = sql_text(name)
    # Erst nachsehen, ob es den Zugang gibt: Die Zahl geänderter Zeilen meldet wrangler nicht in jedem Fall mit
    vorhanden = zeilen(ausfuehren(f"SELECT COUNT(*) AS anzahl FROM zugaenge WHERE name = {n} COLLATE NOCASE", ziel))
    if not vorhanden or not vorhanden[0].get("anzahl"):
        print(f"Keinen Zugang mit dem Namen {name} gefunden. Die genaue Schreibweise zeigt: zugang liste")
        return 1
    if befehl == "sperren":
        ausfuehren(f"UPDATE zugaenge SET aktiv = 0 WHERE name = {n} COLLATE NOCASE; "
                   f"DELETE FROM sitzungen WHERE name = {n} COLLATE NOCASE", ziel)
    else:
        ausfuehren(
            f"DELETE FROM zugaenge WHERE name = {n} COLLATE NOCASE; "
            f"DELETE FROM fragen_pro_person WHERE name = {n} COLLATE NOCASE; "
            f"DELETE FROM sitzungen WHERE name = {n} COLLATE NOCASE", ziel,
        )
    print(f"{name}: {'gesperrt' if befehl == 'sperren' else 'gelöscht'}, überall abgemeldet.")
    return 0


# ---------- Gemeldete Antworten ----------

def meldungen(argumente: list[str], ziel: str) -> int:
    if argumente and argumente[0] == "loeschen":
        if len(argumente) != 2 or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", argumente[1]):
            print("Bitte den Zeitpunkt angeben, bis zu dem gelöscht wird, zum Beispiel 2026-11-10T18:00:00+00:00")
            return 1
        ausfuehren(f"DELETE FROM meldungen WHERE zeit <= {sql_text(argumente[1])}", ziel)
        print("Gelöscht.")
        return 0
    merken = None  # --merken DATEI: späteste angezeigte Zeit dorthin schreiben (für das Löschen danach)
    if len(argumente) == 2 and argumente[0] == "--merken":
        merken = Path(argumente[1])
    liste = zeilen(ausfuehren("SELECT zeit, frage, antwort, quellen, notiz FROM meldungen ORDER BY zeit", ziel))
    if not liste:
        print("Keine gemeldeten Antworten.")
        return 2  # für einrichten.ps1: nichts zum Löschen
    for nr, m in enumerate(liste, 1):
        try:
            zeit = datetime.fromisoformat(m["zeit"]).astimezone()
            wann = f"{zeit.day}.{zeit.month}.{zeit.year} um {zeit:%H:%M} Uhr"
        except (TypeError, ValueError):
            wann = str(m.get("zeit"))
        print(f"\n{nr}. Meldung vom {wann}")
        print(f"Frage: {m.get('frage') or ''}")
        if m.get("notiz"):
            print(f"Notiz: {m['notiz']}")
        antwort = (m.get("antwort") or "").strip()
        print("Antwort: " + (antwort[:800] + " [gekürzt]" if len(antwort) > 800 else antwort))
        try:
            for q in json.loads(m.get("quellen") or "[]"):
                if isinstance(q, dict) and q.get("url"):
                    print(f"  Quelle: {q.get('titel') or ''} {q['url']}")
        except (TypeError, ValueError):
            pass
    print(f"\n{len(liste)} gemeldete Antworten.")
    if merken:
        merken.write_text(str(liste[-1]["zeit"]), encoding="utf-8")
    return 0


def main(argumente: list[str]) -> int:
    ziel = "--local" if "--lokal" in argumente else "--remote"
    argumente = [a for a in argumente if a != "--lokal"]
    if not argumente:
        print(__doc__)
        return 1
    befehl, rest = argumente[0], argumente[1:]
    try:
        if befehl == "datenbank":
            return datenbank(ziel)
        if befehl == "hochladen":
            return hochladen(ziel)
        if befehl == "stand":
            return stand(ziel)
        if befehl == "zugang":
            return zugang(rest, ziel)
        if befehl == "meldungen":
            return meldungen(rest, ziel)
    except Fehler as e:
        print(e)
        return 1
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
