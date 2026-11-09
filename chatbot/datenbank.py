"""Gemeinsame Datenbank für SeydaAI (eine SQLite Datei, Volltextsuche mit FTS5)."""

import os
import re
import sqlite3
from datetime import date

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
"""


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
