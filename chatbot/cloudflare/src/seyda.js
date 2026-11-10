// Kern von SeydaAI für Cloudflare: Frage verstehen, in den Quellen suchen, Antwort mit Beleg erzeugen.
// Gleiche Logik wie seyda.py (lokale Fassung). Wer hier etwas ändert, ändert es dort auch;
// test/vergleich.test.js prüft, dass beide Fassungen dasselbe Ergebnis liefern.

import {
  abschnitteNachNr,
  abschnitteVon,
  folgeabschnitte,
  suchenGruppen,
} from "./datenbank.js";

export const SUCH_MODELL = "claude-haiku-5-5";
export const ANTWORT_MODELL = "claude-sonnet-5-5";
const KANDIDATEN = 30; // so viele Abschnitte holt die Volltextsuche
const MAX_JE_SEITE = 3; // damit ein langer Artikel nicht alle Plätze belegt
const MAX_AUSWAHL = 8; // so viele wählt Haiku für die Antwort aus
const MIT_FOLGEABSCHNITT = 3; // bei den besten so vielen kommt der nächste Abschnitt derselben Seite dazu
export const MAX_ABSCHNITTE = 10; // so viele Abschnitte bekommt Sonnet höchstens
const VORSCHAU_ZEICHEN = 700; // so viel Text je Kandidat sieht Haiku beim Auswählen
const MAX_VERLAUF = 3; // so viele frühere Fragen und Antworten gehen mit
const ANTWORT_GRUENDLICHKEIT = "medium";
const MAX_WOERTER_OHNE_BELEG = 2;

export const KEIN_TREFFER = {
  de: "Dazu habe ich in den Quellen nichts gefunden. Bitte frag den Imam deiner Moschee oder die Fetva Stelle von Diyanet.",
  tr: "Bu konuda kaynaklarda bir şey bulamadım. Lütfen camiinizin imamına veya Diyanet'in fetva hattına danışın.",
};

// Bei diesen Wortanfängen antwortet der Bot ohne Sprachmodell sofort mit Hilfsnummern.
const KRISE_WOERTER = [
  "suizid", "selbstmord", "umbringen", "bringe mich um", "bring mich um", "nicht mehr leben",
  "will sterben", "sterben will", "möchte sterben", "tot sein", "mich töten",
  "ritze mich", "mich ritzen", "mich verletzen", "selbstverletz",
  "gewalt", "vergewalt", "missbraucht", "sexuell belästigt", "schlägt mich", "schlaegt mich", "schlägt uns", "schlägt meine", "hat mich geschlagen",
  "werde geschlagen", "wurde geschlagen", "wurde verprügelt", "geschlagen worden", "bedroht mich",
  "intihar", "kendimi öldür", "kendimi as", "ölmek istiyorum", "ölmek ister", "yaşamak istemiyorum", "canıma kıy",
  "kendime zarar", "şiddet", "dövüyor", "beni dövü", "taciz", "tecavüz", "istismar",
];

// Nummern am 9. November 2026 auf telefonseelsorge.de, nummergegenkummer.de und hilfetelefon.de nachgelesen.
const KRISE_ANTWORT = {
  de:
    "Es tut mir leid, dass es dir gerade so geht. Bitte sprich sofort mit einem Menschen, der helfen kann:\n" +
    "Notruf: 112\n" +
    "TelefonSeelsorge: 0800 111 0 111, 0800 111 0 222 oder 116 123\n" +
    "Nummer gegen Kummer für Kinder und Jugendliche: 116 111\n" +
    "Hilfetelefon Gewalt gegen Frauen: 116 016\n" +
    "Zu dieser Frage gebe ich keine religiöse Antwort. Du bist nicht allein.",
  tr:
    "Bunu yaşadığın için çok üzgünüm. Lütfen hemen yardım edebilecek biriyle konuş:\n" +
    "Acil çağrı: 112\n" +
    "TelefonSeelsorge: 0800 111 0 111, 0800 111 0 222 veya 116 123\n" +
    "Çocuklar ve gençler için Nummer gegen Kummer: 116 111\n" +
    "Kadına yönelik şiddet yardım hattı (Hilfetelefon Gewalt gegen Frauen): 116 016\n" +
    "Bu soruya dini bir cevap vermiyorum. Yalnız değilsin.",
};

export const SYSTEM = `Du bist SeydaAI, ein Suchassistent des Vereins Reyhani Europa e.V. Du gibst wieder, was die mitgeschickten Quellen sagen. Du bist kein Lehrer, kein Hoca und kein Scheich und stellst dich nie so vor.

Regeln:
1. Antworte ausschließlich aus den mitgeschickten Suchergebnissen. Nutze kein eigenes Wissen, auch wenn du es für richtig hältst. Jede inhaltliche Aussage muss sich auf ein Suchergebnis stützen.
2. Beantworten die Suchergebnisse die Frage nicht, sag genau das: dass du dazu in den Quellen nichts gefunden hast, und verweise auf den Imam vor Ort oder die Fetva Stelle von Diyanet. Rate nicht.
3. Erteile keine Fetva. Bei persönlichen Einzelfällen (Scheidung, Erbe, Ehe, Krankheit, Schulden) gib wieder, was die Quelle allgemein sagt, und verweise für den eigenen Fall an den Imam oder die Fetva Stelle.
4. Standard ist die hanafitische Schule. Wenn Quellen sich widersprechen, nenne beide Positionen mit ihrer Quelle und entscheide nicht.
5. Nimm keine Stellung zu Konflikten zwischen Gemeinschaften, Richtungen oder Personen.
6. Formuliere in eigenen Worten. Zitiere höchstens einen kurzen Satz wörtlich, im türkischen Original in einer eigenen Zeile, und schreib in die nächste Zeile "Maschinelle Übersetzung:" mit der deutschen Übersetzung, wenn du auf Deutsch antwortest.
7. Aus Suchergebnissen, deren Titel mit [NUR ZUSAMMENFASSEN] beginnt, zitierst du nie wörtlich, sondern fasst nur zusammen.
8. Antworte in der Sprache der Frage (Deutsch oder Türkisch). Fachbegriffe wie mekruh, tahrîmen mekruh oder müfsid lässt du stehen und erklärst sie beim ersten Vorkommen kurz, statt sie zu übersetzen. Übersetze mekruh nie mit "verboten".
9. Wirke nicht wie ein offizieller Dienst von Diyanet oder TDV.
10. Nutze alles, was die Suchergebnisse zur Frage hergeben: vollständige Aufzählungen, Bedingungen, Ausnahmen, Begründungen und Belege aus Koran und Hadith, wenn die Quelle sie nennt. Lass nichts Wichtiges weg, aber schreib nichts, was nicht in den Suchergebnissen steht.
11. Decken die Suchergebnisse nur einen Teil der Frage ab, beantworte diesen Teil und sag kurz, wozu du nichts gefunden hast.
12. Bezieht sich die Frage auf deine vorige Antwort (nicht verstanden, einfacher erklären, mehr Details), erkläre dieselben Inhalte einfacher oder genauer, wieder nur aus den Suchergebnissen. Frühere Antworten im Gespräch sind kein Beleg.
13. Ist die Frage unklar oder umgangssprachlich, beantworte die wahrscheinlichste Lesart.

So baust du die Antwort auf, damit sie übersichtlich ist:
- Beginne mit ein oder zwei Sätzen, die die Frage direkt beantworten. Keine Einleitung, keine Wiederholung der Frage.
- Danach die Einzelheiten. Aufzählungen (zum Beispiel die Säulen des Islams oder die Farz des Gebets) schreibst du als nummerierte Liste: jeder Punkt in einer eigenen Zeile, beginnend mit "1. ", "2. " usw., dann der Begriff in **fett**, ein Doppelpunkt und eine kurze Erklärung. In einer Klammer hinter dem Begriff steht höchstens seine deutsche Übersetzung. Ein Urteil (zum Beispiel haram, caiz, farz, erlaubt, verboten) steht nie im Stichwort, sondern im belegten Satz dahinter. Ist der Begriff selbst ein Urteilswort (etwa tahrîmen mekruh, sünnet, farz-ı kifâye) oder fasst eine Zwischenzeile Punkte nach ihrem Urteil zusammen (etwa was Kaza und Keffaret erfordert), schreib das als ganzen Satz mit Beleg, nicht als Stichwort. Für Punkte ohne Reihenfolge nimmst du eine Liste mit "- ".
- Bedingungen, Ausnahmen und abweichende Meinungen kommen danach in einen eigenen kurzen Absatz.
- Kurze Absätze mit höchstens drei Sätzen, dazwischen eine Leerzeile. Keine Überschriften mit #, keine Tabellen, keine Emojis.
- Einfache, klare Sätze, die auch Jugendliche verstehen. Eine Aussage pro Satz. Keine Gedankenstriche; verbinde mit Punkt, Komma oder Doppelpunkt.
- So lang wie nötig, meist 100 bis 300 Wörter. Keine Schlussformel: Den Hinweis auf den Imam hängt das Programm selbst an.`;

const HINWEIS_AUSGEBLENDET = {
  de: "Hinweis: Teile der Antwort hatten keinen Beleg in den Quellen und wurden ausgeblendet.",
  tr: "Not: Cevabın kaynakta dayanağı olmayan kısımları gizlendi.",
};
const HINWEIS_ABGESCHNITTEN = {
  de: "Hinweis: Die Antwort wurde abgeschnitten.",
  tr: "Not: Cevap yarıda kesildi.",
};
const VERWEIS = {
  de: "Für deinen eigenen Fall frag bitte den Imam deiner Moschee oder die Fetva Stelle von Diyanet.",
  tr: "Kendi durumun için lütfen camiinin imamına veya Diyanet'in fetva hattına danış.",
};

// ---------- Hilfen, die sich wie Python verhalten ----------
// Python \w (Unicode) entspricht Buchstaben, Ziffern und Unterstrich. JavaScript \w und \b kennen nur ASCII,
// darum hier eigene Klassen und Wortgrenzen.
const W = "[\\p{L}\\p{N}_]";
const HAT_WORTZEICHEN = new RegExp(W, "u");
const VOR_WORT = `(?<!${W})`;
const NACH_WORT = `(?!${W})`;

function woerterZaehlen(text) {
  // wie len(text.split()) in Python
  return text.split(/\s+/u).filter(Boolean).length;
}
function zeichenKuerzen(text, n) {
  // wie text[:n] in Python (zählt Zeichen, nicht UTF 16 Einheiten)
  const zeichen = Array.from(text);
  return zeichen.length <= n ? text : zeichen.slice(0, n).join("");
}
function laenge(text) {
  return Array.from(text).length;
}
function regexEscape(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function istUebersetzung(text) {
  const t = text.trim().toLowerCase();
  return t.startsWith("maschinelle übersetzung") || t.startsWith("makine çevirisi");
}

// Für Wortvergleiche: klein, ohne Akzente und Sonderzeichen (â wird a, ş wird s, ü wird u, ı und İ werden i).
export function falten(text) {
  return text.replace(/ı/g, "i").replace(/İ/g, "I").normalize("NFKD").replace(/\p{Mn}/gu, "").toLowerCase();
}

export function woerter(text) {
  // Apostrophe verbinden, damit "bid'at" ein Wort bleibt und "İslâm'ın" als "islamin" zählt
  return falten(text).replace(/['’`]/g, "").match(new RegExp(`${W}+`, "gu")) || [];
}

const menge = (liste) => new Set(liste.map(falten));
const liste = (werte) => werte.map(falten);

// Wörter, die ein Urteil oder eine Aussage tragen (gleiche Listen wie seyda.py).
const URTEILSWOERTER = menge([
  "ist", "sind", "war", "wird", "werden", "macht", "machen", "muss", "müssen", "darf", "dürfen", "kann", "können",
  "soll", "sollen", "gilt", "gelten", "nicht", "nie", "niemals", "ja", "nein", "genau", "stimmt", "natürlich",
  "selbstverständlich", "sicher", "klar", "durchaus", "absolut", "ok", "okay", "tabu",
  "musst", "müsste", "müssten", "kannst", "könnte", "könnten", "darfst", "dürfte", "dürften", "sollst", "sollte",
  "sollten", "solltest", "besser", "gewiss", "sicherlich", "eindeutig", "definitiv", "bestimmt", "ordnung",
  "var", "yok", "olur", "evet", "hayır", "tabii", "elbette", "kesinlikle", "aynen", "evla", "evladır", "doğrudur",
  "möglich", "unmöglich", "nachholen", "nachzuholen", "nachgeholt", "unrein",
  "muhakkak", "edilir", "yapılır", "kılınır", "olunur", "tutulur", "verilir", "sayılır",
]);
const URTEILSANFAENGE = liste([
  "kein", "sünd", "gebot", "brech", "bricht", "gebroch", "statthaft", "strafbar", "legitim", "ratsam", "gültig",
  "ungültig", "nötig", "unnötig", "gestatt", "abzurat", "abgerat", "lobenswert", "tadel", "verdienstvoll",
  "zweifelhaft", "unzweifelhaft", "zweifellos", "şüpheli", "şüphesiz",
  "sunna", "şirk", "küfr", "küfür", "batıl", "yanlış", "gerek", "lazım", "değil", "boz", "olmaz", "olmama",
  "kabul", "makbul", "efdal", "tavsiye", "zarar", "kaçın", "sakın", "terk", "mümkün", "muteber", "geçer",
]);
const URTEILSTEILE = liste([
  "erlaub", "verbot", "verbiet", "untersag", "zuläss", "pflicht", "empfehl", "empfohl", "verwerf",
  "verpön", "erwünscht", "notwendig", "obligat", "bedenk", "problem", "richtig", "falsch",
  "korrekt", "schäd", "schad", "geduldet", "toleriert", "ablehn", "abzulehn", "abgelehnt", "akzeptab", "akzeptiert",
  "harmlos", "unterlass", "meid", "vorzuzieh", "wirksam", "verwehr",
  "haram", "helal", "halal", "caiz", "mekruh", "makruh", "mubah", "günah", "yasak", "farz", "fard", "vacip", "vacib",
  "wajib", "sünnet", "müstehap", "müstehab", "mustahab", "mendup", "mendub", "bidat", "sahih", "fasit", "fasid",
  "geçersiz", "geçerli", "zorunlu", "mecburi", "serbest", "sakınca", "uygun", "sevap", "sevab", "nafile",
  "keffaret", "kefaret",
]);
const KEIN_URTEIL = menge([
  "Pflichtabgabe", "Pflichtabgaben", "Pflichtgebet", "Pflichtgebete", "Pflichtgebets", "Pflichtalmosen", "Pflichten",
  "Pflichtteil", "Pflichtteile", "Grundpflicht", "Grundpflichten", "namaz", "temeli", "kemali", "cemali", "ameli",
]);
const KEIN_URTEIL_ANFANG = liste(["Unreinheit", "Gültigkeit", "Gerekçe"]);
const PASSIV = menge(["edilir", "yapılır", "kılınır", "olunur", "tutulur", "verilir", "sayılır"]);
const FRAGEWOERTER = menge([
  "nasıl", "kime", "kimlere", "kimler", "neler", "nelerdir", "ne", "nerede", "ne zaman",
  "hangi", "niçin", "neden", "wie", "wem", "wann", "wo", "warum", "wozu",
]);
const URTEILSENDUNGEN = [
  "maz", "mez", "mali", "meli", "malidir", "melidir", "abilir", "ebilir",
  "abilirsin", "ebilirsin", "abilirler", "ebilirler",
];

function istUrteilswort(w) {
  if (KEIN_URTEIL.has(w) || KEIN_URTEIL_ANFANG.some((a) => w.startsWith(a))) return false;
  if (URTEILSWOERTER.has(w) || URTEILSANFAENGE.some((a) => w.startsWith(a)) || URTEILSTEILE.some((t) => w.includes(t))) {
    return true;
  }
  // Türkische Endungen mit Urteil: olmaz, edilmez, kılınmalı, içilmemeli, okuyabilir
  return laenge(w) > 4 && URTEILSENDUNGEN.some((e) => w.endsWith(e));
}

function hatUrteil(text) {
  const ws = woerter(text);
  const frage = ws.some((w) => FRAGEWOERTER.has(w));
  for (let i = 0; i < ws.length; i++) {
    const w = ws[i];
    if (frage && PASSIV.has(w)) continue;
    if (w === "besser" && ws[i + 1] === "gesagt") continue;
    if (istUrteilswort(w)) return true;
  }
  return false;
}

// Leerraum oder kurze Überleitung ohne Satzende und ohne Urteilswort, also keine eigene Aussage.
export function istUeberleitung(text) {
  const t = text.trim();
  if (!t) return true;
  return woerterZaehlen(t) <= MAX_WOERTER_OHNE_BELEG && !/[.!?]/.test(t) && !hatUrteil(t);
}

const LISTENZEICHEN = /^\s*(?:\p{Nd}{1,2}[.)]|[-*•])\s+/u;
// Stichwort einer Liste: "**Namaz** (Gebet):" oder "**Kurz gesagt:**" oder "Bedingungen:", immer mit Doppelpunkt am Ende
const STICHWORT_FETT = /^\*\*([^*]+?):?\*\*\s*(?:\(([^()]*)\))?\s*:?$/u;
const STICHWORT = /^([^*():]+?)\s*(?:\(([^()]*)\))?\s*:$/u;

// Reine Gliederung ohne eigene Aussage: Leerraum, Satzzeichen, Listennummern und Stichwörter mit Doppelpunkt.
export function istGliederung(text) {
  for (const zeile of text.split("\n")) {
    const rest = zeile.replace(LISTENZEICHEN, "").trim();
    if (!HAT_WORTZEICHEN.test(rest)) continue; // nur Leerraum, Satzzeichen oder Listenzeichen
    if (!rest.endsWith(":") && !rest.endsWith(":**")) return false;
    let m = rest.match(STICHWORT_FETT);
    let grenze = 5;
    if (!m) {
      m = rest.match(STICHWORT);
      grenze = 2;
    }
    if (!m) return false;
    const wort = m[1];
    const klammer = m[2] || "";
    if (woerterZaehlen(wort) > grenze || woerterZaehlen(klammer) > 4) return false;
    if (/[.!?]/.test(wort + klammer) || hatUrteil(wort + " " + klammer)) return false;
  }
  return true;
}

// Was von einem ausgeblendeten Stück stehen bleibt: Zeilenumbrüche, reine Gliederungszeilen und das
// Listenzeichen der letzten Zeile.
export function geruest(text) {
  const zeilen = text.split("\n");
  return zeilen
    .map((zeile, i) => {
      if (HAT_WORTZEICHEN.test(zeile) && istGliederung(zeile)) return zeile;
      if (i === zeilen.length - 1) {
        const m = zeile.match(LISTENZEICHEN);
        if (m) return m[0];
      }
      return "";
    })
    .join("\n");
}

// Python $ trifft am Ende oder vor einem letzten Zeilenumbruch, darum (?=\n?$)
const LEERER_PUNKT_MUSTER = "(?:^|(?<=\\n))[ \\t]*(?:\\p{Nd}{1,2}[.)]|[-*•])[ \\t]+(?=\\n?$)";
const LEERER_PUNKT = new RegExp(LEERER_PUNKT_MUSTER, "u");
const LEERER_PUNKT_ALLE = new RegExp(LEERER_PUNKT_MUSTER, "gu");

// Ein Listenzeichen ohne belegten Text dahinter in derselben Zeile wäre ein leerer Punkt; es fällt weg.
export function leerePunkteEntfernen(teile) {
  for (let i = 0; i < teile.length; i++) {
    const t = teile[i];
    if (t.belege.length || !LEERER_PUNKT.test(t.text)) continue;
    const folgt = i + 1 < teile.length ? teile[i + 1].text : "";
    if (!folgt.trim() || folgt.replace(/^[ \t]+/, "").startsWith("\n")) {
      t.text = t.text.replace(LEERER_PUNKT_ALLE, "");
    }
  }
}

// Kleinschreibung, die auch türkisches İ und I richtig behandelt.
export function normalisieren(text) {
  return text.toLowerCase().replace(/̇/g, "").replace(/ı/g, "i");
}

const KRISE_MUSTER = KRISE_WOERTER.map((w) => new RegExp(VOR_WORT + regexEscape(normalisieren(w)), "u"));

export function istKrise(frage) {
  const f = normalisieren(frage);
  return KRISE_MUSTER.some((m) => m.test(f));
}

const DE = new RegExp(
  `${VOR_WORT}(?:der|die|das|den|dem|ist|sind|was|wie|warum|wann|ich|du|und|oder|darf|dürfen|macht|kann|muss|soll|ein|eine|mein|meine|bei|beim|nach|wenn|für)${NACH_WORT}`,
  "gu",
);
const TR = new RegExp(
  `${VOR_WORT}(?:ne|neden|nasıl|nedir|niçin|mi|mı|mu|mü|midir|mıdır|mudur|müdür|ve|ile|bir|bu|şu|ben|sen|için|olur|olmaz|gerekir|var|yok|kime|kimler|hangi|kaç|nerede|niye|nelerdir|verilir|yapılır|edilir|caiz mi)${NACH_WORT}`,
  "gu",
);

export function sprache(frage) {
  const klein = frage.toLowerCase();
  const de = (klein.match(DE) || []).length;
  const tr = (klein.match(TR) || []).length + (frage.match(/[şğıİ]/g) || []).length;
  return tr > de ? "tr" : "de";
}

export function krisenAntwort(frage) {
  const lang = sprache(frage);
  return { antwort: KRISE_ANTWORT[lang], quellen: [], teile: [], art: "krise", sprache: lang };
}

const VERSTEHEN_SYSTEM = `Du bereitest eine Volltextsuche in türkischen islamischen Texten vor (Fetvas und Beschlüsse des Din İşleri Yüksek Kurulu von Diyanet, Artikel der TDV İslâm Ansiklopedisi). Du bekommst die neue Nachricht und, falls vorhanden, die letzten Fragen und Antworten des Gesprächs.

frage: Die neue Nachricht als vollständige, eigenständige Frage in ihrer Sprache. Bezieht sie sich auf das Gespräch (zum Beispiel "nicht verstanden", "erklär einfacher", "und beim Fasten?", "bu cevap anlaşılmadı"), setze das Thema aus dem Gespräch ein.
rueckfrage: true, wenn die Nachricht sich auf die vorige Antwort bezieht und ohne sie nicht verständlich wäre, sonst false.
sprache: "tr", wenn die neue Nachricht türkisch ist (auch ohne türkische Sonderzeichen geschrieben), sonst "de".
Die Nachricht kann Tippfehler, Umgangssprache, fehlende Sonderzeichen oder gemischtes Deutsch und Türkisch enthalten. Erkenne, was gemeint ist, und arbeite damit.
begriffe: 4 bis 10 türkische Suchbegriffe in korrekter türkischer Schreibweise mit ı, ş, ğ, ç, ö, ü, als Wortstamm oder Grundform ohne Endungen. Nimm Fachbegriffe und die Wendungen, unter denen die Quellen das Thema behandeln, auch Synonyme. Die Suche findet alle Wörter, die mit dem Begriff beginnen, darum lieber kurz: "şart" findet auch "şartı" und "şartları". Beispiel für "Was sind die Säulen des Islams?": İslâm şart, beş şart, kelime-i şehâdet, namaz, oruç, zekât, hac. Deutsche Begriffe übersetzt du in die türkischen Fachwörter, zum Beispiel Gebet = namaz, Gebetswaschung = abdest, Ganzkörperwaschung = gusül, Fasten = oruç, Pilgerfahrt = hac, Opfer = kurban, Glaubensgrundsätze = iman esasları, Bittgebet = dua, Gottesgedenken = zikir, Sufismus = tasavvuf. Keine Füllwörter.`;

const VERSTEHEN_SCHEMA = {
  type: "object",
  properties: {
    frage: { type: "string" },
    rueckfrage: { type: "boolean" },
    sprache: { type: "string", enum: ["de", "tr"] },
    begriffe: { type: "array", items: { type: "string" } },
  },
  required: ["frage", "rueckfrage", "sprache", "begriffe"],
  additionalProperties: false,
};

const AUSWAHL_SYSTEM = `Du bekommst eine Frage und nummerierte Textabschnitte aus islamischen Quellen. Wähle die Abschnitte aus, mit denen sich die Frage gründlich beantworten lässt, die besten zuerst, höchstens 8.
Wähle einen Abschnitt, wenn er die Frage oder einen wesentlichen Teil davon direkt behandelt, auch wenn er nur ergänzt: Bedingungen, Ausnahmen, Begründungen, Belege oder die Erklärung eines Begriffs aus der Frage. Abschnitte, die das Thema nur nebenbei erwähnen, wählst du nicht. Hilft kein Abschnitt, gib eine leere Liste zurück.`;

const AUSWAHL_SCHEMA = {
  type: "object",
  properties: { nummern: { type: "array", items: { type: "integer" } } },
  required: ["nummern"],
  additionalProperties: false,
};

const istGanzzahl = (n) => typeof n === "number" && Number.isInteger(n);

// Nimmt nur gültige, gekürzte Einträge aus dem vom Gerät geschickten Verlauf (höchstens MAX_VERLAUF).
export function verlaufPruefen(roh) {
  if (!Array.isArray(roh)) return [];
  const sauber = [];
  for (const e of roh.slice(-10)) {
    if (!e || typeof e !== "object" || Array.isArray(e)) continue;
    const frage = zeichenKuerzen(typeof e.frage === "string" ? e.frage.trim() : "", 1000);
    const antwort = zeichenKuerzen(typeof e.antwort === "string" ? e.antwort.trim() : "", 4000);
    const urls = Array.isArray(e.quellen)
      ? e.quellen.filter((u) => typeof u === "string" && u.startsWith("https://")).map((u) => zeichenKuerzen(u, 500)).slice(0, 6)
      : [];
    const nummern = Array.isArray(e.abschnitte)
      ? e.abschnitte.filter((n) => istGanzzahl(n) && n > 0 && n < 2 ** 62).slice(0, MAX_ABSCHNITTE)
      : [];
    if (frage && antwort) sauber.push({ frage, antwort, quellen: urls, abschnitte: nummern });
  }
  return sauber.slice(-MAX_VERLAUF);
}

function jsonAus(antwort) {
  if (antwort.stop_reason === "refusal" || antwort.stop_reason === "max_tokens") return null;
  const text = antwort.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
  try {
    const daten = JSON.parse(text);
    return daten && typeof daten === "object" && !Array.isArray(daten) ? daten : null;
  } catch {
    return null;
  }
}

function buchen(kosten, modell, antwort, schritt) {
  kosten.push({ modell, eingabe: antwort.usage?.input_tokens ?? 0, ausgabe: antwort.usage?.output_tokens ?? 0, schritt });
}

// Haiku macht aus der Nachricht (mit Gesprächsverlauf) eine eigenständige Frage und türkische Suchbegriffe.
async function verstehen(client, kosten, frage, verlauf) {
  const gespraech = verlauf
    .map((e) => `Frühere Frage: ${e.frage}\nFrühere Antwort: ${zeichenKuerzen(e.antwort, 1500)}\n\n`)
    .join("");
  const antwort = await client.messages.create({
    model: SUCH_MODELL,
    max_tokens: 4000,
    output_config: { effort: "low", format: { type: "json_schema", schema: VERSTEHEN_SCHEMA } },
    system: VERSTEHEN_SYSTEM,
    messages: [{ role: "user", content: gespraech + "Neue Nachricht: " + frage }],
  });
  buchen(kosten, SUCH_MODELL, antwort, "verstehen");
  const daten = jsonAus(antwort) || {};
  let begriffe = Array.isArray(daten.begriffe) ? daten.begriffe : [];
  begriffe = begriffe.filter((b) => typeof b === "string" && b.trim()).map((b) => b.trim()).slice(0, 12);
  const eigenstaendig = typeof daten.frage === "string" && daten.frage.trim() ? daten.frage : frage;
  return {
    frage: zeichenKuerzen(eigenstaendig.trim(), 1500),
    // Nur wenn Haiku nichts liefert, dienen die Wörter der Frage selbst als Suchbegriffe
    begriffe: begriffe.length ? begriffe : frage.match(new RegExp(`${W}{4,}`, "gu")) || [],
    rueckfrage: Boolean(daten.rueckfrage) && verlauf.length > 0,
    sprache: daten.sprache === "de" || daten.sprache === "tr" ? daten.sprache : sprache(frage),
  };
}

// Ein Suchwort als Präfixsuche. Bei ı zusätzlich die Form mit i suchen (Titel wie HAYIZ landen als "hayiz").
function suchwort(w) {
  w = w.toLowerCase();
  if (w.includes("ı")) return `("${w}"* OR "${w.replace(/ı/g, "i")}"*)`;
  return `"${w}"*`;
}

// Baut eine ODER Suche aus Begriffen. Sonderzeichen werden entfernt, damit FTS5 nicht stolpert.
export function ftsAusdruck(begriffe) {
  const teile = [];
  for (const b of begriffe) {
    const sauber = b.replace(/[^\p{L}\p{N}_\s]/gu, " ").trim();
    if (!sauber) continue;
    const ws = sauber.split(/\s+/u).map(suchwort);
    teile.push(ws.length === 1 ? ws[0] : "(" + ws.join(" AND ") + ")");
  }
  return teile.join(" OR ");
}

// Bis zu KANDIDATEN Abschnitte: erst die vorab gesetzten (bei Rückfragen), dann die Gesamtsuche,
// dann die besten Treffer je Begriff, damit kein Begriff untergeht. Alles in einer Datenbankabfrage.
async function kandidatenSuchen(db, begriffe, vorab = []) {
  const gesamt = ftsAusdruck(begriffe);
  const anfragen = [];
  if (gesamt) anfragen.push({ ausdruck: gesamt, anzahl: 40 });
  const jeBegriff = begriffe.map((b) => ftsAusdruck([b]));
  for (const a of new Set(jeBegriff.filter(Boolean))) anfragen.push({ ausdruck: a, anzahl: 4 });
  const ergebnisse = anfragen.length ? await suchenGruppen(db, anfragen) : [];
  const liste = (ausdruck, anzahl) => {
    const i = anfragen.findIndex((a) => a.ausdruck === ausdruck && a.anzahl === anzahl);
    return i < 0 ? [] : ergebnisse[i];
  };

  const gewaehlt = new Map();
  const jeSeite = new Map();
  const dazu = (t, frei = false) => {
    if (gewaehlt.has(t.nr) || gewaehlt.size >= KANDIDATEN) return;
    if (!frei && (jeSeite.get(t.url) || 0) >= MAX_JE_SEITE) return;
    gewaehlt.set(t.nr, t);
    jeSeite.set(t.url, (jeSeite.get(t.url) || 0) + 1);
  };
  for (const t of vorab) dazu(t, true);
  for (const t of gesamt ? liste(gesamt, 40) : []) {
    if (gewaehlt.size >= KANDIDATEN - 2 * Math.min(begriffe.length, 6)) break;
    dazu(t);
  }
  for (const a of jeBegriff) {
    for (const t of a ? liste(a, 4) : []) dazu(t);
  }
  return [...gewaehlt.values()];
}

// Haiku liest kurze Vorschauen aller Kandidaten und wählt die passenden aus.
async function auswaehlen(client, kosten, frage, kandidaten) {
  const liste = kandidaten
    .map((t, i) => `[${i}] ${t.quelle}: ${t.titel}\n${zeichenKuerzen(t.text, VORSCHAU_ZEICHEN)}`)
    .join("\n\n");
  const antwort = await client.messages.create({
    model: SUCH_MODELL,
    max_tokens: 4000,
    output_config: { effort: "low", format: { type: "json_schema", schema: AUSWAHL_SCHEMA } },
    system: AUSWAHL_SYSTEM,
    messages: [{ role: "user", content: `Frage: ${frage}\n\nAbschnitte:\n\n${liste}` }],
  });
  buchen(kosten, SUCH_MODELL, antwort, "auswaehlen");
  const daten = jsonAus(antwort);
  // Auswahl gescheitert: dann die ersten Treffer der Volltextsuche nehmen
  if (daten === null) return kandidaten.slice(0, MAX_AUSWAHL);
  const nummern = [];
  for (const n of Array.isArray(daten.nummern) ? daten.nummern : []) {
    if (istGanzzahl(n) && n >= 0 && n < kandidaten.length && !nummern.includes(n)) nummern.push(n);
  }
  return nummern.slice(0, MAX_AUSWAHL).map((n) => kandidaten[n]);
}

// Hängt an die besten Treffer den direkt folgenden Abschnitt derselben Seite an, weil Aufzählungen
// oft über die Grenze zweier Abschnitte gehen. Höchstens MAX_ABSCHNITTE insgesamt.
async function mitFolgeabschnitten(db, treffer) {
  const ergebnis = [...treffer];
  const schon = new Set(treffer.map((t) => t.nr));
  const beste = treffer.slice(0, MIT_FOLGEABSCHNITT);
  const folgen = beste.length ? await folgeabschnitte(db, beste) : new Map();
  for (const t of beste) {
    if (ergebnis.length >= MAX_ABSCHNITTE) break;
    const folge = folgen.get(t.nr);
    if (folge && !schon.has(folge.nr)) {
      ergebnis.splice(ergebnis.indexOf(t) + 1, 0, folge);
      schon.add(folge.nr);
    }
  }
  return ergebnis.slice(0, MAX_ABSCHNITTE);
}

// Ergebnis: {antwort, quellen: [{titel, url, quelle}], teile: [{text, belege}], art, sprache, ...}.
// art ist "antwort", "kein_treffer", "krise" oder "abgelehnt". kosten sammelt den Verbrauch je Schritt.
export async function antworten(client, db, frage, verlauf = [], kosten = []) {
  if (istKrise(frage)) return krisenAntwort(frage);

  const verstanden = await verstehen(client, kosten, frage, verlauf);
  const lang = verstanden.sprache;
  const leer = { antwort: KEIN_TREFFER[lang], quellen: [], teile: [], art: "kein_treffer", sprache: lang };

  // Bei einer Rückfrage gehören die zitierten Abschnitte der vorigen Antwort zu den Kandidaten
  let vorab = [];
  if (verstanden.rueckfrage) {
    const vorher = verlauf[verlauf.length - 1];
    vorab = vorher.abschnitte.length ? await abschnitteNachNr(db, vorher.abschnitte) : [];
    if (!vorab.length) vorab = vorher.quellen.length ? await abschnitteVon(db, vorher.quellen) : [];
  }
  const kandidaten = await kandidatenSuchen(db, verstanden.begriffe, vorab);
  if (!kandidaten.length) return leer;
  let treffer = await auswaehlen(client, kosten, verstanden.frage, kandidaten);
  if (!treffer.length) return leer;
  treffer = await mitFolgeabschnitten(db, treffer);

  const ergebnisse = treffer.map((t) => {
    let titel = `${t.quelle}: ${t.titel}`;
    if (t.nur_zusammenfassen) titel = "[NUR ZUSAMMENFASSEN] " + titel;
    return {
      type: "search_result",
      source: t.url,
      title: titel,
      content: [{ type: "text", text: t.text }],
      citations: { enabled: true },
    };
  });

  // Frühere Fragen und Antworten als normales Gespräch, die Suchergebnisse nur in der neuen Frage
  const nachrichten = [];
  for (const e of verlauf) {
    nachrichten.push({ role: "user", content: e.frage });
    nachrichten.push({ role: "assistant", content: e.antwort });
  }
  let frageText = "Frage: " + frage;
  if (verstanden.frage !== frage) frageText += "\n(Gemeint ist: " + verstanden.frage + ")";
  nachrichten.push({ role: "user", content: [...ergebnisse, { type: "text", text: frageText }] });

  const nachricht = await client.beta.messages.create({
    model: ANTWORT_MODELL,
    max_tokens: 16000,
    output_config: { effort: ANTWORT_GRUENDLICHKEIT },
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    system: SYSTEM,
    messages: nachrichten,
  });
  buchen(kosten, nachricht.model || ANTWORT_MODELL, nachricht, "antworten");

  if (nachricht.stop_reason === "refusal") return { ...leer, art: "abgelehnt" };
  return aufbereiten(nachricht, treffer, lang, leer);
}

// Baut aus der Antwort von Sonnet die belegten Teile, die Quellenliste und die Hinweise.
export function aufbereiten(nachricht, treffer, lang, leer) {
  const quellen = [];
  const indexVonUrl = new Map();
  const teile = [];
  const zitiert = [];
  let ausgeblendet = false;
  let vorherBelegt = false;
  for (const block of nachricht.content) {
    if (block.type !== "text") continue;
    const belege = [];
    for (const c of block.citations || []) {
      if (!c || c.type !== "search_result_location") continue;
      const i = c.search_result_index;
      if (!istGanzzahl(i) || i < 0 || i >= treffer.length) continue;
      const t = treffer[i];
      if (!zitiert.includes(t.nr)) zitiert.push(t.nr);
      if (!indexVonUrl.has(t.url)) {
        indexVonUrl.set(t.url, quellen.length);
        quellen.push({ titel: t.titel || t.url, url: t.url, quelle: t.quelle });
      }
      if (!belege.includes(indexVonUrl.get(t.url))) belege.push(indexVonUrl.get(t.url));
    }
    if (belege.length) {
      teile.push({ text: block.text, belege });
      vorherBelegt = true;
    } else if (istUebersetzung(block.text) && vorherBelegt) {
      // Gekennzeichnete Übersetzung des unmittelbar davor belegten Zitats, nur ihre eigene Zeile
      const vorne = block.text.match(/^\s*/u)[0];
      const ohne = block.text.slice(vorne.length);
      const umbruch = ohne.indexOf("\n");
      const zeile = umbruch < 0 ? ohne : ohne.slice(0, umbruch);
      const rest = umbruch < 0 ? "" : ohne.slice(umbruch + 1);
      teile.push({ text: vorne + zeile + "\n", belege: [] });
      // Was in diesem Stück noch folgt, gilt wie jedes andere Stück ohne Beleg
      if (!rest.trim() || istGliederung(rest)) {
        if (rest) teile.push({ text: rest, belege: [] });
      } else {
        ausgeblendet = true;
        vorherBelegt = false;
        const g = geruest(rest);
        if (g) teile.push({ text: g, belege: [] });
      }
    } else if (istUeberleitung(block.text) || istGliederung(block.text)) {
      teile.push({ text: block.text, belege: [] });
    } else {
      ausgeblendet = true;
      vorherBelegt = false;
      // Zeilenumbrüche und Listenzeichen bleiben, sonst eine Lücke, damit die übrigen Teile nicht aneinanderkleben
      const gerippe = geruest(block.text);
      if (gerippe) {
        teile.push({ text: gerippe, belege: [] });
      } else if (teile.length && !/[ \n]$/.test(teile[teile.length - 1].text)) {
        teile.push({ text: " ", belege: [] });
      }
    }
  }
  leerePunkteEntfernen(teile);

  // Ohne einen einzigen Beleg zeigen wir keine Antwort (Regel: nur aus Quellen)
  if (!quellen.length) return leer;

  let antwortText = teile.map((t) => t.text).join("").trim();
  const hinweise = [];
  if (ausgeblendet) hinweise.push(HINWEIS_AUSGEBLENDET[lang]);
  if (nachricht.stop_reason === "max_tokens") hinweise.push(HINWEIS_ABGESCHNITTEN[lang]);
  // Der Verweis an Imam oder Fetva Stelle hängt immer an, unabhängig vom Modell
  antwortText += "\n\n" + VERWEIS[lang];
  if (hinweise.length) antwortText += "\n\n" + hinweise.join("\n");
  return {
    antwort: antwortText,
    quellen,
    teile,
    hinweise,
    verweis: VERWEIS[lang],
    art: "antwort",
    sprache: lang,
    abschnitte: zitiert,
  };
}
