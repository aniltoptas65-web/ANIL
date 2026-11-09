"""Gemeinsame Datenbank für SeydaAI (eine SQLite Datei, Volltextsuche mit FTS5)."""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timezone

DB_PFAD = os.environ.get("SEYDA_DB", os.path.join(os.path.dirname(__file__), "seyda.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS seiten (
    url TEXT PRIMARY KEY,
    quelle TEXT NOT NULL,
    titel TEXT,
    abgerufen TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS abschnitte USING fts5(
    text,
    titel UNINDEXED,
    url UNINDEXED,
    quelle UNINDEXED,
    nur_zusammenfassen UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS meldungen (
    zeit TEXT NOT NULL,
    frage TEXT NOT NULL,
    antwort TEXT NOT NULL,
    quellen TEXT NOT NULL,
    notiz TEXT
);
CREATE TABLE IF NOT EXISTS verbrauch (
    tag TEXT NOT NULL,
    modell TEXT NOT NULL,
    eingabe INTEGER NOT NULL,
    ausgabe INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS zugaenge (
    name TEXT PRIMARY KEY,
    salz TEXT NOT NULL,
    pruefwert TEXT NOT NULL,
    tageslimit INTEGER NOT NULL,
    aktiv INTEGER NOT NULL DEFAULT 1,
    angelegt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fragen_pro_person (
    tag TEXT NOT NULL,
    name TEXT NOT NULL,
    anzahl INTEGER NOT NULL,
    PRIMARY KEY (tag, name)
);
"""

# Zeichen für Zugangscodes, ohne leicht verwechselbare wie l, 1, o, 0
CODE_ZEICHEN = "abcdefghjkmnpqrstuvwxyz23456789"
CODE_LAENGE = 14  # gut 69 Bit Zufall, Durchprobieren ist damit aussichtslos
NAME_MUSTER = re.compile(r"^[\w .]{1,40}$")


def verbinden(pfad: str = None) -> sqlite3.Connection:
    con = sqlite3.connect(pfad or DB_PFAD, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _fts_ausdruck(begriffe: list[str]) -> str:
    """Baut eine ODER Suche aus Begriffen. Sonderzeichen werden entfernt, damit FTS5 nicht stolpert."""
    teile = []
    for b in begriffe:
        sauber = re.sub(r'[^\w\s]', " ", b, flags=re.UNICODE).strip()
        if not sauber:
            continue
        # Präfixsuche fängt türkische Endungen ab (abdest, abdestin, abdesti).
        # Mehrere Wörter eines Begriffs müssen alle im Abschnitt vorkommen.
        woerter = [f'"{w}"*' for w in sauber.split()]
        teile.append(woerter[0] if len(woerter) == 1 else "(" + " AND ".join(woerter) + ")")
    return " OR ".join(teile)


def suchen(con: sqlite3.Connection, begriffe: list[str], anzahl: int = 6) -> list[dict]:
    ausdruck = _fts_ausdruck(begriffe)
    if not ausdruck:
        return []
    zeilen = con.execute(
        "SELECT text, titel, url, quelle, nur_zusammenfassen, bm25(abschnitte) AS rang "
        "FROM abschnitte WHERE abschnitte MATCH ? ORDER BY rang LIMIT ?",
        (ausdruck, anzahl),
    ).fetchall()
    return [dict(z) for z in zeilen]


def verbrauch_buchen(con, modell: str, eingabe: int, ausgabe: int) -> None:
    con.execute(
        "INSERT INTO verbrauch VALUES (?, ?, ?, ?)",
        (date.today().isoformat(), modell, eingabe, ausgabe),
    )
    con.commit()


def fragen_heute(con) -> int:
    """Zählt die Fragen von heute, die an ein Sprachmodell gingen (jede startet mit genau einem Haiku Aufruf)."""
    from seyda import SUCH_MODELL  # spätes Import, vermeidet Kreisbezug
    return con.execute(
        "SELECT COUNT(*) FROM verbrauch WHERE tag = ? AND modell = ?",
        (date.today().isoformat(), SUCH_MODELL),
    ).fetchone()[0]


# Zugänge für die Testgruppe: pro Person ein Name, ein zufälliger Code und ein eigenes Tageslimit.
# Gespeichert wird nur ein Prüfwert des Codes, nicht der Code selbst.

def _pruefwert(salz: str, code: str) -> str:
    # Die Codes sind lang und zufällig, deshalb reicht SHA 256 mit Salz; ein langsames Verfahren
    # wäre nur bei selbst gewählten Passwörtern nötig.
    return hashlib.sha256((salz + code).encode("utf-8")).hexdigest()


def name_gueltig(name: str) -> bool:
    return bool(NAME_MUSTER.match(name)) and name.strip() == name and name.lower() != "admin"


def zugang_anlegen(con, name: str, tageslimit: int) -> str:
    """Legt einen Zugang an und gibt den Code zurück. Der Code wird nirgends gespeichert."""
    if not name_gueltig(name):
        raise ValueError("Name: 1 bis 40 Zeichen, nur Buchstaben, Ziffern, Leerzeichen, Punkt und Unterstrich, nicht admin.")
    if tageslimit < 1:
        raise ValueError("Das Tageslimit muss mindestens 1 sein.")
    code = "".join(secrets.choice(CODE_ZEICHEN) for _ in range(CODE_LAENGE))
    salz = secrets.token_hex(16)
    con.execute(
        "INSERT INTO zugaenge VALUES (?, ?, ?, ?, 1, ?)",
        (name, salz, _pruefwert(salz, code), tageslimit,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    con.commit()
    return code


def zugang_pruefen(con, name: str, code: str):
    """Gibt den aktiven Zugang zurück, wenn Name und Code passen, sonst None."""
    zeile = con.execute(
        "SELECT name, salz, pruefwert, tageslimit FROM zugaenge WHERE name = ? AND aktiv = 1", (name,)
    ).fetchone()
    if zeile is None:
        return None
    if not hmac.compare_digest(_pruefwert(zeile["salz"], code), zeile["pruefwert"]):
        return None
    return {"name": zeile["name"], "tageslimit": zeile["tageslimit"]}


def aktive_zugaenge(con) -> int:
    return con.execute("SELECT COUNT(*) FROM zugaenge WHERE aktiv = 1").fetchone()[0]


def fragen_heute_person(con, name: str) -> int:
    zeile = con.execute(
        "SELECT anzahl FROM fragen_pro_person WHERE tag = ? AND name = ?", (date.today().isoformat(), name)
    ).fetchone()
    return zeile[0] if zeile else 0


def frage_zaehlen(con, name: str) -> None:
    heute = date.today().isoformat()
    # Nur der heutige Tag wird für das Limit gebraucht; ältere Zählerstände werden gelöscht,
    # damit kein Verlauf entsteht, wer wann wie viel gefragt hat.
    con.execute("DELETE FROM fragen_pro_person WHERE tag < ?", (heute,))
    con.execute(
        "INSERT INTO fragen_pro_person VALUES (?, ?, 1) "
        "ON CONFLICT(tag, name) DO UPDATE SET anzahl = anzahl + 1",
        (heute, name),
    )
    con.commit()
