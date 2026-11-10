// Vergleicht die JavaScript Fassung (src/seyda.js) mit der Python Fassung (seyda.py):
// Für viele zufällige Fälle mit nachgebildeten Antworten der Sprachmodelle müssen Ergebnis und
// Anfragen an die Sprachmodelle gleich sein. Aufruf: npm test (braucht python3 mit den Paketen aus requirements.txt).

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { antworten, verlaufPruefen, istGliederung, istUeberleitung, geruest, istKrise, sprache } from "../src/seyda.js";
import { d1, nachbildung, testdatenbank, zufall } from "./hilfen.js";

const HIER = dirname(fileURLToPath(import.meta.url));
const PYTHON = process.env.PYTHON || "python3";

const FACH = ("namaz oruç zekât hac abdest gusül teyemmüm kurban iman islâm şart farz vâcib sünnet mekruh haram helâl " +
  "caiz müfsid kaza keffâret nafile vitir teravih cuma bayram cenaze nikâh talâk iddet mehir miras faiz sadaka fitre " +
  "kıble ezan kamet secde rükû kıyam kıraat tekbir selâm niyet tahâret necâset hayız nifas cünüp mest mesh dua zikir " +
  "tasavvuf rabıta tevhid şirk bid'at akaid fıkıh hadis âyet sûre İslâm HAYIZ Kelime-i şehâdet").split(" ");
const DOLGU = ("ve bir bu için ile olan olarak daha çok gibi kadar sonra önce her ancak ise de da ki ne olup göre " +
  "karşı arasında üzere şekilde hâlinde hakkında ayrıca nitekim çünkü yani hem veya").split(" ");

function seitenErzeugen(r, anzahl) {
  const seiten = [];
  for (let s = 0; s < anzahl; s++) {
    const tdv = s % 3 === 0;
    const texte = [];
    for (let a = 0, n = r.wahl([1, 1, 2, 3, 5]); a < n; a++) {
      let text = "";
      while (text.length < 200 + r.zahl(600)) {
        const w = Array.from({ length: 6 + r.zahl(10) }, () => (r() < 0.35 ? r.wahl(FACH) : r.wahl(DOLGU)));
        text += w.join(" ") + ". ";
      }
      texte.push(text.trim());
    }
    seiten.push({
      url: tdv ? `https://islamansiklopedisi.org.tr/madde-${s}` : `https://kurul.diyanet.gov.tr/tr/fetva/${s}`,
      quelle: tdv ? "TDV İslâm Ansiklopedisi" : "Din İşleri Yüksek Kurulu",
      titel: r.einige(FACH, 1 + r.zahl(3)).join(" ").toUpperCase(),
      nz: tdv,
      texte,
    });
  }
  return seiten;
}

// Bausteine für die Antwort von Sonnet: belegte Sätze, Gliederung, Urteile, Übersetzungen, Leerraum
const BELEGT = [
  "Das Gebet ist für jeden Muslim Pflicht.", "Namaz beş vakittir.", "Die fünf Säulen sind diese:", "1. **Namaz** (Gebet): das tägliche Gebet",
  "Oruç bozulur.", " Zekât wird an Bedürftige gegeben.", "Abdest bozan şeyler şunlardır:\n", "Er muss nachgeholt werden.",
];
const OHNE = [
  "\n\n", "\n", " ", "1. ", "2. ", "\n3. ", "- ", "\n- ", "**Namaz** (Gebet): ", "2. **Oruç (Fasten):** ", "Kurz gesagt:", "**Kurz gesagt:**",
  "Bedingungen:", "\n5. **Hac** (Pilgerfahrt): ", "Das ist haram.", "Es ist erlaubt", "**Farz**: ", "Zekât kimlere verilir:", "Okuyabilir",
  "unproblematisch", " und ", "Maschinelle Übersetzung: Das Gebet wird verrichtet.", "Maschinelle Übersetzung: Fasten.\n- **Ausnahmen**: ",
  "Maschinelle Übersetzung: x\nDas ist so.", "Makine çevirisi: y", "besser gesagt:", "Pflichtabgabe:", "**İslâm'ın şartları**:", "\n6) ",
  "• ", "Das Gebet ist Pflicht", "**Hac**", "(Gebet):", "Nicht nötig.", ".", "?", "a", "Ja", "kaza edilir", "Wie wird es verrichtet:",
  "1. **Kelime-i Şehâdet**: ", "Sünnet:", "**Mekruh (verpönt)**:", "**Die richtige Reihenfolge:**", "\n\n2. **Zekât**: ", "Ölmek",
  "2. \n", "\n- \n", "3) \t", "Kein Problem:", "**Keine Pflicht**:", "**Unreinheit (Necâset)**:", "**Gerekçesi**:", "Gültigkeit:", "Gidebilirler:", "**Emez**:", "Yapabilirsin", "kılınmalıdır",
];

function sonnetErzeugen(r, anzahlTreffer) {
  const content = [];
  if (r() < 0.1) content.push({ type: "thinking", thinking: "..." });
  for (let i = 0, n = 1 + r.zahl(14); i < n; i++) {
    if (r() < 0.45) {
      const citations = Array.from({ length: 1 + r.zahl(2) }, () => ({ search_result_index: r.zahl(anzahlTreffer + 2) - (r() < 0.05 ? 3 : 0) }));
      content.push({ type: "text", text: r.wahl(BELEGT), citations });
    } else {
      let text = r.wahl(OHNE);
      if (r() < 0.3) text += r.wahl(OHNE);
      content.push({ type: "text", text });
    }
  }
  return { content, stop_reason: r() < 0.05 ? "refusal" : r() < 0.1 ? "max_tokens" : "end_turn", model: r() < 0.5 ? "claude-sonnet-5-5" : null };
}

function verstehenErzeugen(r) {
  const art = r.zahl(10);
  if (art === 0) return { content: [{ type: "text", text: "kein JSON" }] };
  if (art === 1) return { content: [{ type: "text", text: "{}" }], stop_reason: "max_tokens" };
  const daten = {
    frage: r() < 0.9 ? r.wahl(["Was sind die Säulen?", "Orucu bozan şeyler nelerdir?", "  ", "Nagellack beim Gebet?"]) : 5,
    rueckfrage: r() < 0.4,
    sprache: r.wahl(["de", "tr", "en"]),
    begriffe: r() < 0.1 ? [] : [...r.einige(FACH, 1 + r.zahl(9)), ...(r() < 0.2 ? ["   ", 3, "kelime-i şehâdet", "\"*(x)", "rükû secde"] : [])],
  };
  if (r() < 0.1) delete daten.begriffe;
  return { content: [{ type: "text", text: JSON.stringify(daten) }] };
}

function auswahlErzeugen(r) {
  if (r() < 0.1) return { content: [{ type: "text", text: "nichts" }] };
  const nummern = Array.from({ length: r.zahl(11) }, () => r.wahl([r.zahl(35), r.zahl(35), r.zahl(5), -1, true, 0]));
  return { content: [{ type: "text", text: JSON.stringify({ nummern }) }] };
}

function verlaufErzeugen(r, maxNr) {
  if (r() < 0.4) return [];
  return Array.from({ length: 1 + r.zahl(5) }, () => ({
    frage: r.wahl(["Was ist Namaz?", "  ", "Orucu ne bozar?", "nicht verstanden"]),
    antwort: r.wahl(["Namaz ist das Gebet.", "", "Oruç bozulur. ".repeat(r.zahl(500))]),
    quellen: r() < 0.7 ? [r.wahl(["https://kurul.diyanet.gov.tr/tr/fetva/1", "https://kurul.diyanet.gov.tr/tr/fetva/2", "http://x", "https://islamansiklopedisi.org.tr/madde-3"]), 7] : "x",
    abschnitte: r() < 0.6 ? Array.from({ length: r.zahl(4) }, () => r.wahl([1 + r.zahl(maxNr), 0, -5, true, 1 + r.zahl(maxNr)])) : [],
  }));
}

function pythonAusfuehren(faelle) {
  const r = spawnSync(PYTHON, [join(HIER, "vergleich_py.py")], {
    input: JSON.stringify(faelle),
    encoding: "utf-8",
    maxBuffer: 1 << 28,
    env: { ...process.env, PYTHONUTF8: "1" },
  });
  if (r.status !== 0) throw new Error("Python Fehler:\n" + r.stderr);
  return JSON.parse(r.stdout);
}

const sortiert = (wert) => JSON.parse(JSON.stringify(wert, (k, v) => (v && typeof v === "object" && !Array.isArray(v) ? Object.fromEntries(Object.entries(v).sort()) : v)));

test("JavaScript und Python liefern dieselben Antworten", async () => {
  const ordner = mkdtempSync(join(tmpdir(), "seyda-vergleich-"));
  const r = zufall(20261110);
  const pfad = join(ordner, "test.db");
  testdatenbank(pfad, seitenErzeugen(r, 220));
  const db = d1(pfad);
  const maxNr = Number(db.roh.prepare("SELECT MAX(rowid) AS m FROM abschnitte").get().m);

  const faelle = [];
  for (let i = 0; i < 400; i++) {
    faelle.push({
      db: pfad,
      frage: r.wahl(["Was sind die Säulen des Islams?", "Orucu bozan şeyler nelerdir?", "erklär einfacher", "Darf man mit Nagellack beten?", "kaza namazı nasıl kılınır"]),
      verlauf: verlaufErzeugen(r, maxNr),
      verstehen: verstehenErzeugen(r),
      auswahl: auswahlErzeugen(r),
      sonnet: sonnetErzeugen(r, 10),
    });
  }
  const python = pythonAusfuehren(faelle);
  let antworten_ = 0;
  for (let i = 0; i < faelle.length; i++) {
    const anfragen = [];
    let ergebnis;
    try {
      ergebnis = await antworten(nachbildung(faelle[i], anfragen), db, faelle[i].frage, verlaufPruefen(faelle[i].verlauf));
    } catch (e) {
      ergebnis = { fehler: e.name, text: e.message };
    }
    if (ergebnis.art === "antwort") antworten_++;
    assert.deepEqual(sortiert(ergebnis), sortiert(python[i].ergebnis), `Fall ${i}: Ergebnis weicht ab`);
    assert.deepEqual(sortiert(anfragen), sortiert(python[i].anfragen), `Fall ${i}: Anfragen weichen ab`);
  }
  // Sicherstellen, dass die Fälle wirklich bis zur Antwort durchlaufen und nicht alle früh enden
  assert.ok(antworten_ > 100, `nur ${antworten_} Fälle mit Antwort`);
});

// Alle Wörter aus den Urteilslisten von seyda.py, damit jede Liste im Vergleich vorkommt
function pythonWoerter() {
  const py = spawnSync(PYTHON, ["-c", `
import json, sys
sys.path.insert(0, ${JSON.stringify(join(HIER, "..", ".."))})
import seyda
listen = [seyda._URTEILSWOERTER, seyda._URTEILSANFAENGE, seyda._URTEILSTEILE, seyda._KEIN_URTEIL, seyda._KEIN_URTEIL_ANFANG,
          seyda._PASSIV, seyda._FRAGEWOERTER, seyda.KRISE_WOERTER]
json.dump(sorted({w for l in listen for w in l}), sys.stdout)
`], { encoding: "utf-8", env: { ...process.env, PYTHONUTF8: "1" } });
  if (py.status !== 0) throw new Error(py.stderr);
  return JSON.parse(py.stdout);
}

test("Filter und Spracherkennung wie in Python", () => {
  const r = zufall(7);
  const woerter = pythonWoerter();
  const abwandeln = (w) => r.wahl([w, w[0].toUpperCase() + w.slice(1), w + "dır", w + "en", "un" + w, w.toUpperCase(), "x" + w]);
  const stichwort = () => r.wahl(["**", ""]) + abwandeln(r.wahl(woerter)) + r.wahl(["", " ", " (Gebet)", " " + abwandeln(r.wahl(woerter))]) + r.wahl([":", "**:", ":**", ""]);
  const teile = [...OHNE, ...BELEGT, "**", "(", ")", ":", "İ", "ı", "Ü", "\t", "  ", "e\u0301", "²", "_", "x", "ne zaman", "edilir", "nasıl"];
  for (let i = 0; i < 400; i++) teile.push(stichwort(), abwandeln(r.wahl(woerter)));
  const texte = Array.from({ length: 6000 }, () => Array.from({ length: 1 + r.zahl(4) }, () => r.wahl(teile)).join(r.wahl(["", " ", "\n"])));
  texte.push("Ich will nicht mehr leben", "kendime zarar veriyorum", "Gewaltig", "İntihar", "selbstverletzung", "Beni dövüyorlar");
  const py = spawnSync(PYTHON, ["-c", `
import json, sys
sys.path.insert(0, ${JSON.stringify(join(HIER, "..", ".."))})
import seyda
texte = json.load(sys.stdin)
json.dump([[seyda.ist_gliederung(t), seyda.ist_ueberleitung(t), seyda.geruest(t), seyda.ist_krise(t), seyda.sprache(t)] for t in texte], sys.stdout)
`], { input: JSON.stringify(texte), encoding: "utf-8", env: { ...process.env, PYTHONUTF8: "1" } });
  if (py.status !== 0) throw new Error(py.stderr);
  const erwartet = JSON.parse(py.stdout);
  texte.forEach((t, i) => {
    assert.deepEqual([istGliederung(t), istUeberleitung(t), geruest(t), istKrise(t), sprache(t)], erwartet[i], `Text ${JSON.stringify(t)}`);
  });
});
