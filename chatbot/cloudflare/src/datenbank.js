// Datenbank von SeydaAI auf Cloudflare D1 (SQLite mit Volltextsuche FTS5).
// Wegen der Grenze von 50 Abfragen je Aufruf im kostenlosen Tarif fasst dieses Modul mehrere Suchen
// in eine Abfrage zusammen (UNION ALL), statt wie datenbank.py jede einzeln zu stellen.

const SPALTEN = "rowid AS nr, text, titel, url, quelle, nur_zusammenfassen";
const SITZUNG_TAGE = 30;

// Heutiges Datum in deutscher Zeit (Tageslimits wechseln um Mitternacht in Deutschland, nicht in UTC)
export function tagHeute(jetzt = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Berlin",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(jetzt);
}

// D1 erlaubt höchstens 5 Teile in einem UNION ALL. Darum je 5 Teile in eine Unterabfrage packen (auch mehrstufig).
export function vereinen(teile) {
  if (teile.length <= 5) return teile.join(" UNION ALL ");
  const gruppen = [];
  for (let i = 0; i < teile.length; i += 5) gruppen.push(`SELECT * FROM (${vereinen(teile.slice(i, i + 5))})`);
  return vereinen(gruppen);
}

function gruppieren(zeilen, anzahl) {
  const gruppen = Array.from({ length: anzahl }, () => []);
  for (const z of zeilen) {
    const { g, ...rest } = z;
    gruppen[g].push(rest);
  }
  return gruppen;
}

// Mehrere Volltextsuchen in einer Abfrage. anfragen: [{ausdruck, anzahl}]. Ergebnis: je Anfrage eine Liste,
// sortiert wie in datenbank.py (bm25, Treffer im Titel zählen dreimal so viel wie im Text).
// "ORDER BY rank" statt "ORDER BY bm25(...)": Dann sortiert FTS5 selbst und D1 zählt nur die gelieferten
// Zeilen als gelesen. Mit bm25(...) zählte jede passende Zeile (im Test 70.000 bis 120.000 je Frage bei
// 10.600 Abschnitten, kostenlos sind 5 Millionen am Tag).
export async function suchenGruppen(db, anfragen) {
  const sql = anfragen
    .map(
      (a, i) =>
        `SELECT * FROM (SELECT ${i} AS g, ${SPALTEN} FROM abschnitte ` +
        `WHERE abschnitte MATCH ? AND rank MATCH 'bm25(1.0, 3.0)' ORDER BY rank LIMIT ${Number(a.anzahl) | 0})`,
    );
  const { results } = await db.prepare(vereinen(sql)).bind(...anfragen.map((a) => a.ausdruck)).all();
  return gruppieren(results, anfragen.length);
}

// Bestimmte Abschnitte, zum Beispiel die in der vorigen Antwort zitierten (in dieser Reihenfolge).
export async function abschnitteNachNr(db, nummern) {
  const sql = nummern
    .map((_, i) => `SELECT ${i} AS g, ${SPALTEN} FROM abschnitte WHERE rowid = ?`);
  const { results } = await db.prepare(vereinen(sql)).bind(...nummern).all();
  return gruppieren(results, nummern.length).flat();
}

// Die ersten Abschnitte bestimmter Seiten, falls die zitierten Abschnitte nicht bekannt sind.
export async function abschnitteVon(db, urls, jeSeite = 2) {
  const eindeutig = [...new Set(urls)];
  const platz = eindeutig.map(() => "?").join(",");
  const { results } = await db
    .prepare(`SELECT ${SPALTEN} FROM abschnitte WHERE url IN (${platz}) ORDER BY rowid`)
    .bind(...eindeutig)
    .all();
  const ergebnis = [];
  for (const url of urls) ergebnis.push(...results.filter((z) => z.url === url).slice(0, jeSeite));
  return ergebnis;
}

// Je Treffer der nächste Abschnitt derselben Seite (nächsthöhere Nummer, höchstens drei dahinter).
// Ergebnis: Map von der Nummer des Treffers auf seinen Folgeabschnitt.
export async function folgeabschnitte(db, treffer) {
  const sql = treffer
    .map(
      (_, i) =>
        `SELECT * FROM (SELECT ${i} AS g, ${SPALTEN} FROM abschnitte ` +
        `WHERE rowid > ? AND rowid <= ? AND url = ? ORDER BY rowid LIMIT 1)`,
    );
  const werte = treffer.flatMap((t) => [t.nr, t.nr + 3, t.url]);
  const { results } = await db.prepare(vereinen(sql)).bind(...werte).all();
  const folgen = new Map();
  gruppieren(results, treffer.length).forEach((liste, i) => {
    if (liste.length) folgen.set(treffer[i].nr, liste[0]);
  });
  return folgen;
}

// ---------- Zugänge und Anmeldung ----------

async function sha256Hex(text) {
  const daten = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(daten)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function gleich(a, b) {
  // Vergleich in fester Zeit, damit die Antwortzeit nichts über den Prüfwert verrät
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let unterschied = 0;
  for (let i = 0; i < a.length; i++) unterschied |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return unterschied === 0;
}

function zufallsToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  let text = "";
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// Gibt den aktiven Zugang zurück, wenn Name und Code passen, sonst null.
// Gleiches Verfahren wie datenbank.py: SHA 256 über Salz plus Code. Beim Namen zählt Groß und Kleinschreibung
// nicht (Handytastaturen schreiben gern groß); cloud.py lässt deshalb keine zwei Namen zu, die sich nur darin
// unterscheiden. NOCASE gilt nur für A bis Z, nicht für türkische Buchstaben wie ş und Ş.
export async function zugangPruefen(db, name, code) {
  const z = await db
    .prepare("SELECT name, salz, pruefwert, tageslimit FROM zugaenge WHERE name = ? COLLATE NOCASE AND aktiv = 1")
    .bind(name)
    .first();
  const pruefwert = await sha256Hex((z ? z.salz : "kein Zugang") + code);
  if (!z || !gleich(pruefwert, z.pruefwert)) return null;
  return { name: z.name, tageslimit: z.tageslimit };
}

// Legt eine Sitzung an und gibt das Token für das Cookie zurück. Gespeichert wird nur sein Prüfwert.
export async function sitzungAnlegen(db, name, jetzt = new Date()) {
  const token = zufallsToken();
  const ablauf = new Date(jetzt.getTime() + SITZUNG_TAGE * 86400000).toISOString();
  await db.batch([
    db.prepare("DELETE FROM sitzungen WHERE ablauf < ?").bind(jetzt.toISOString()),
    db.prepare("INSERT INTO sitzungen (pruefwert, name, ablauf) VALUES (?, ?, ?)").bind(await sha256Hex(token), name, ablauf),
  ]);
  return { token, sekunden: SITZUNG_TAGE * 86400 };
}

// Gültige Sitzung eines aktiven Zugangs: {name, tageslimit}, sonst null.
export async function sitzungPruefen(db, token, jetzt = new Date()) {
  if (!token || token.length > 100) return null;
  return await db
    .prepare(
      "SELECT z.name AS name, z.tageslimit AS tageslimit FROM sitzungen s JOIN zugaenge z ON z.name = s.name " +
        "WHERE s.pruefwert = ? AND s.ablauf > ? AND z.aktiv = 1",
    )
    .bind(await sha256Hex(token), jetzt.toISOString())
    .first();
}

export async function sitzungBeenden(db, token) {
  if (!token || token.length > 100) return;
  await db.prepare("DELETE FROM sitzungen WHERE pruefwert = ?").bind(await sha256Hex(token)).run();
}

// ---------- Tageslimits und Verbrauch ----------

// Fragen von heute insgesamt (jede Frage an ein Sprachmodell beginnt mit genau einem Schritt "verstehen")
// und Fragen dieser Person, in einer Abfrage.
export async function fragenHeute(db, tag, name) {
  const z = await db
    .prepare(
      "SELECT (SELECT COUNT(*) FROM verbrauch WHERE tag = ?1 AND schritt = 'verstehen') AS gesamt, " +
        "(SELECT anzahl FROM fragen_pro_person WHERE tag = ?1 AND name = ?2) AS person",
    )
    .bind(tag, name)
    .first();
  return { gesamt: z?.gesamt ?? 0, person: z?.person ?? 0 };
}

// Nur der heutige Tag wird für das Limit gebraucht; ältere Zählerstände fallen weg, damit kein Verlauf entsteht,
// wer wann wie viel gefragt hat.
export async function frageZaehlen(db, tag, name) {
  await db.batch([
    db.prepare("DELETE FROM fragen_pro_person WHERE tag < ?").bind(tag),
    db
      .prepare(
        "INSERT INTO fragen_pro_person (tag, name, anzahl) VALUES (?, ?, 1) " +
          "ON CONFLICT(tag, name) DO UPDATE SET anzahl = anzahl + 1",
      )
      .bind(tag, name),
  ]);
}

export async function verbrauchBuchen(db, tag, kosten) {
  if (!kosten.length) return;
  const platz = kosten.map(() => "(?, ?, ?, ?, ?)").join(", ");
  const werte = kosten.flatMap((k) => [tag, k.modell, k.eingabe, k.ausgabe, k.schritt]);
  await db.prepare(`INSERT INTO verbrauch (tag, modell, eingabe, ausgabe, schritt) VALUES ${platz}`).bind(...werte).run();
}

export async function meldungSpeichern(db, zeit, frage, antwort, quellen, notiz) {
  await db
    .prepare("INSERT INTO meldungen (zeit, frage, antwort, quellen, notiz) VALUES (?, ?, ?, ?, ?)")
    .bind(zeit, frage, antwort, quellen, notiz)
    .run();
}
