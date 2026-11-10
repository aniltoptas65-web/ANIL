// Gemeinsame Hilfen für die Tests: D1 nachgebildet mit node:sqlite und ein nachgebildetes Sprachmodell.

import { DatabaseSync } from "node:sqlite";

// Verhält sich für die genutzten Aufrufe wie die D1 Bindung von Cloudflare. Wie D1 erlaubt sie
// höchstens 5 Teile je UNION ALL, damit ein Verstoß schon hier auffällt.
export function d1(pfad) {
  const db = new DatabaseSync(pfad);
  const pruefen = (sql) => {
    // Teile je Ebene zählen: Klammern trennen die Ebenen
    const ebenen = [0];
    let tiefe = 0;
    for (let i = 0; i < sql.length; i++) {
      if (sql[i] === "(") ebenen[++tiefe] = 0;
      else if (sql[i] === ")") tiefe--;
      else if (sql.startsWith(" UNION ALL ", i) && ++ebenen[tiefe] > 4) {
        throw new Error("D1_ERROR: too many terms in compound SELECT");
      }
    }
  };
  const anweisung = (sql, werte = []) => ({
    bind: (...w) => anweisung(sql, w),
    async all() {
      pruefen(sql);
      return { results: db.prepare(sql).all(...werte).map((z) => ({ ...z })) };
    },
    async first() {
      pruefen(sql);
      const z = db.prepare(sql).get(...werte);
      return z ? { ...z } : null;
    },
    async run() {
      const r = db.prepare(sql).run(...werte);
      return { meta: { changes: Number(r.changes) } };
    },
  });
  return {
    prepare: (sql) => anweisung(sql),
    async batch(liste) {
      const ergebnisse = [];
      for (const a of liste) ergebnisse.push(await a.run());
      return ergebnisse;
    },
    roh: db,
  };
}

function antwort(roh) {
  return {
    usage: { input_tokens: 10, output_tokens: 5 },
    model: null,
    stop_reason: "end_turn",
    ...roh,
    content: (roh.content || []).map((b) => ({
      ...b,
      citations: b.citations ? b.citations.map((c) => ({ type: "search_result_location", ...c })) : null,
    })),
  };
}

// Nachgebildeter Claude Client: liefert die im Fall hinterlegten Antworten und merkt sich die Anfragen.
export function nachbildung(fall, anfragen) {
  return {
    messages: {
      create: async (kw) => {
        anfragen.push(kw);
        return antwort(kw.system.startsWith("Du bereitest") ? fall.verstehen : fall.auswahl);
      },
    },
    beta: {
      messages: {
        create: async (kw) => {
          anfragen.push(kw);
          return antwort(fall.sonnet);
        },
      },
    },
  };
}

// Kleiner Zufallsgenerator mit Startwert, damit jeder Testlauf dieselben Fälle erzeugt
export function zufall(startwert) {
  let a = startwert >>> 0;
  const r = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  r.zahl = (n) => Math.floor(r() * n);
  r.wahl = (liste) => liste[r.zahl(liste.length)];
  r.einige = (liste, n) => Array.from({ length: n }, () => r.wahl(liste));
  return r;
}

// Legt eine Testdatenbank im Aufbau von datenbank.py an
export function testdatenbank(pfad, seiten) {
  const db = new DatabaseSync(pfad);
  db.exec(`
    CREATE TABLE seiten (url TEXT PRIMARY KEY, quelle TEXT NOT NULL, titel TEXT, abgerufen TEXT NOT NULL, regel TEXT);
    CREATE VIRTUAL TABLE abschnitte USING fts5(text, titel, url UNINDEXED, quelle UNINDEXED, nur_zusammenfassen UNINDEXED,
      tokenize = 'unicode61 remove_diacritics 2');`);
  const s = db.prepare("INSERT INTO seiten VALUES (?, ?, ?, '2026-11-10T00:00:00+00:00', 'r')");
  const a = db.prepare("INSERT INTO abschnitte (text, titel, url, quelle, nur_zusammenfassen) VALUES (?, ?, ?, ?, ?)");
  for (const seite of seiten) {
    s.run(seite.url, seite.quelle, seite.titel);
    for (const text of seite.texte) a.run(text, seite.titel, seite.url, seite.quelle, seite.nz ? 1 : 0);
  }
  db.close();
}
