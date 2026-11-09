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
    abgerufen TEXT NOT NULL,
    regel TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS abschnitte USING fts5(
    text,
    titel,
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
    ausgabe INTEGER NOT NULL,
    schritt TEXT
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


def _titel_durchsuchbar_machen(con) -> None:
    """Ältere Datenbanken hatten den Titel nicht in der Suche. Dann die Tabelle einmal umbauen, Inhalte bleiben."""
    zeile = con.execute("SELECT sql FROM sqlite_master WHERE name = 'abschnitte'").fetchone()
    if not zeile or "titel UNINDEXED" not in zeile[0]:
        return
    # In einer Transaktion: bricht der Umbau ab, bleibt die alte Tabelle unverändert
    con.executescript("""
        BEGIN;
        ALTER TABLE abschnitte RENAME TO abschnitte_alt;
        CREATE VIRTUAL TABLE abschnitte USING fts5(
            text, titel, url UNINDEXED, quelle UNINDEXED, nur_zusammenfassen UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        INSERT INTO abschnitte (text, titel, url, quelle, nur_zusammenfassen)
            SELECT text, titel, url, quelle, nur_zusammenfassen FROM abschnitte_alt;
        DROP TABLE abschnitte_alt;
        COMMIT;
    """)


def verbinden(pfad: str = None) -> sqlite3.Connection:
    con = sqlite3.connect(pfad or DB_PFAD, check_same_thread=False)
    con.row_factory = sqlite3.Row
    _titel_durchsuchbar_machen(con)
    con.executescript(SCHEMA)
    # Ältere Datenbanken kannten den Schritt (verstehen, auswählen, antworten) und die Einleseregel noch nicht
    for tabelle, spalte in (("verbrauch", "schritt"), ("seiten", "regel")):
        if spalte not in [z[1] for z in con.execute(f"PRAGMA table_info({tabelle})")]:
            con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} TEXT")
            con.commit()
    return con


def _wort(w: str) -> str:
    """Ein Suchwort als Präfixsuche. Großgeschriebene Titel wie HAYIZ landen in der Suche als "hayiz",
    im Text steht "hayız". Darum bei ı zusätzlich die Form mit i suchen."""
    w = w.lower()
    if "ı" in w:
        return f'("{w}"* OR "{w.replace("ı", "i")}"*)'
    return f'"{w}"*'


def _fts_ausdruck(begriffe: list[str]) -> str:
    """Baut eine ODER Suche aus Begriffen. Sonderzeichen werden entfernt, damit FTS5 nicht stolpert."""
    teile = []
    for b in begriffe:
        sauber = re.sub(r'[^\w\s]', " ", b, flags=re.UNICODE).strip()
        if not sauber:
            continue
        # Präfixsuche fängt türkische Endungen ab (abdest, abdestin, abdesti).
        # Mehrere Wörter eines Begriffs müssen alle im Abschnitt vorkommen.
        woerter = [_wort(w) for w in sauber.split()]
        teile.append(woerter[0] if len(woerter) == 1 else "(" + " AND ".join(woerter) + ")")
    return " OR ".join(teile)


def suchen(con: sqlite3.Connection, begriffe: list[str], anzahl: int = 6) -> list[dict]:
    ausdruck = _fts_ausdruck(begriffe)
    if not ausdruck:
        return []
    # Treffer im Titel zählen dreimal so viel wie im Text (bm25 Gewichte in Spaltenreihenfolge)
    zeilen = con.execute(
        "SELECT rowid AS nr, text, titel, url, quelle, nur_zusammenfassen, bm25(abschnitte, 1.0, 3.0) AS rang "
        "FROM abschnitte WHERE abschnitte MATCH ? ORDER BY rang LIMIT ?",
        (ausdruck, anzahl),
    ).fetchall()
    return [dict(z) for z in zeilen]


def abschnitte_nach_nr(con, nummern: list[int]) -> list[dict]:
    """Bestimmte Abschnitte, zum Beispiel die in der vorigen Antwort zitierten (in dieser Reihenfolge)."""
    ergebnis = []
    for nr in nummern:
        z = con.execute(
            "SELECT rowid AS nr, text, titel, url, quelle, nur_zusammenfassen FROM abschnitte WHERE rowid = ?", (nr,)
        ).fetchone()
        if z:
            ergebnis.append(dict(z))
    return ergebnis


def abschnitte_von(con, urls: list[str], je_seite: int = 2) -> list[dict]:
    """Die ersten Abschnitte bestimmter Seiten, falls die zitierten Abschnitte nicht bekannt sind."""
    ergebnis = []
    for url in urls:
        ergebnis += [dict(z) for z in con.execute(
            "SELECT rowid AS nr, text, titel, url, quelle, nur_zusammenfassen FROM abschnitte WHERE url = ? ORDER BY rowid LIMIT ?",
            (url, je_seite),
        )]
    return ergebnis


def verbrauch_buchen(con, modell: str, eingabe: int, ausgabe: int, schritt: str = None) -> None:
    con.execute(
        "INSERT INTO verbrauch (tag, modell, eingabe, ausgabe, schritt) VALUES (?, ?, ?, ?, ?)",
        (date.today().isoformat(), modell, eingabe, ausgabe, schritt),
    )
    con.commit()


def fragen_heute(con) -> int:
    """Zählt die Fragen von heute, die an ein Sprachmodell gingen (jede startet mit genau einem Schritt "verstehen").

    Zeilen aus älteren Versionen ohne Schritt zählen über das Suchmodell, damit der Tageszähler beim Umstieg stimmt.
    """
    from seyda import SUCH_MODELL  # spätes Import, vermeidet Kreisbezug
    return con.execute(
        "SELECT COUNT(*) FROM verbrauch WHERE tag = ? AND (schritt = 'verstehen' OR (schritt IS NULL AND modell = ?))",
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
        raise ValueError("Name: 1 bis 40 Zeichen, nur Buchstaben, Ziffern, Leerzeichen, Punkt und Unterstrich, ohne Leerzeichen am Anfang oder Ende, nicht admin.")
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


def alte_zaehler_loeschen(con) -> None:
    """Nur der heutige Tag wird für das Limit gebraucht; ältere Zählerstände werden gelöscht,
    damit kein Verlauf entsteht, wer wann wie viel gefragt hat."""
    con.execute("DELETE FROM fragen_pro_person WHERE tag < ?", (date.today().isoformat(),))
    con.commit()


def frage_zaehlen(con, name: str) -> None:
    heute = date.today().isoformat()
    con.execute("DELETE FROM fragen_pro_person WHERE tag < ?", (heute,))
    con.execute(
        "INSERT INTO fragen_pro_person VALUES (?, ?, 1) "
        "ON CONFLICT(tag, name) DO UPDATE SET anzahl = anzahl + 1",
        (heute, name),
    )
    con.commit()
