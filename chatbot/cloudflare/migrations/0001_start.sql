-- SeydaAI auf Cloudflare D1: Grundgerüst der Datenbank.
-- Die Texte der Quellen lädt cloud.py hochladen hinein (aus seyda.db auf dem Rechner).
-- Achtung: D1 kann Datenbanken mit Volltextsuche (FTS5) nicht exportieren; "wrangler d1 export" nie benutzen.

CREATE VIRTUAL TABLE IF NOT EXISTS abschnitte USING fts5(
    text,
    titel,
    url UNINDEXED,
    quelle UNINDEXED,
    nur_zusammenfassen UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS zugaenge (
    name TEXT PRIMARY KEY,
    salz TEXT NOT NULL,
    pruefwert TEXT NOT NULL,
    tageslimit INTEGER NOT NULL,
    aktiv INTEGER NOT NULL DEFAULT 1,
    angelegt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sitzungen (
    pruefwert TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ablauf TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sitzungen_ablauf ON sitzungen (ablauf);
CREATE INDEX IF NOT EXISTS sitzungen_name ON sitzungen (name);

CREATE TABLE IF NOT EXISTS fragen_pro_person (
    tag TEXT NOT NULL,
    name TEXT NOT NULL,
    anzahl INTEGER NOT NULL,
    PRIMARY KEY (tag, name)
);

CREATE TABLE IF NOT EXISTS verbrauch (
    tag TEXT NOT NULL,
    modell TEXT NOT NULL,
    eingabe INTEGER NOT NULL,
    ausgabe INTEGER NOT NULL,
    schritt TEXT
);
CREATE INDEX IF NOT EXISTS verbrauch_tag ON verbrauch (tag, schritt);

CREATE TABLE IF NOT EXISTS meldungen (
    zeit TEXT NOT NULL,
    frage TEXT NOT NULL,
    antwort TEXT NOT NULL,
    quellen TEXT NOT NULL,
    notiz TEXT
);

-- Stand des letzten Hochladens (Zeit, Zahl der Abschnitte je Quelle), nur zur Anzeige
CREATE TABLE IF NOT EXISTS stand (
    schluessel TEXT PRIMARY KEY,
    wert TEXT NOT NULL
);
