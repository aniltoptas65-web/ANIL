// SeydaAI als Cloudflare Worker. Die Seite (web/index.html, Logo, Schriften) liefert Cloudflare direkt aus,
// dieser Worker beantwortet nur die Adressen unter /api/.
//
// Anmeldung: Name und Zugangscode (angelegt mit cloud.py zugang neu). Danach hält ein Cookie die Sitzung
// 30 Tage, damit man sich auf dem Handy nicht jedes Mal neu anmelden muss.

import Anthropic from "@anthropic-ai/sdk";
import { antworten, istKrise, krisenAntwort, verlaufPruefen } from "./seyda.js";
import {
  fragenHeute,
  frageZaehlen,
  meldungSpeichern,
  sitzungAnlegen,
  sitzungBeenden,
  sitzungPruefen,
  tagHeute,
  verbrauchBuchen,
  zugangPruefen,
} from "./datenbank.js";

const MAX_FRAGE_ZEICHEN = 1000;
const MAX_KOERPER = 60000; // Frage plus bis zu drei frühere Fragen und Antworten
const COOKIE = "seyda_sitzung";
const NAME_MUSTER = /^[\p{L}\p{N}_ .]{1,40}$/u;

const KOEPFE = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "no-referrer",
  "X-Robots-Tag": "noindex, nofollow",
};

function json(status, daten, extra = {}) {
  return new Response(JSON.stringify(daten), { status, headers: { ...KOEPFE, ...extra } });
}

function cookieLesen(request) {
  const kopf = request.headers.get("Cookie") || "";
  for (const teil of kopf.split(";")) {
    const [name, ...wert] = teil.trim().split("=");
    if (name === COOKIE) return wert.join("=");
  }
  return "";
}

function cookieSetzen(token, sekunden) {
  return `${COOKIE}=${token}; Path=/; Max-Age=${sekunden}; HttpOnly; Secure; SameSite=Strict`;
}

// Schutz davor, dass eine fremde Webseite im Hintergrund Anfragen stellt
function gleicheHerkunft(request) {
  const herkunft = request.headers.get("Origin");
  if (herkunft && herkunft !== new URL(request.url).origin) return false;
  return (request.headers.get("Content-Type") || "").startsWith("application/json");
}

// Liest den Körper stückweise und bricht ab, sobald er zu groß wird. Die Längenangabe ist nicht Pflicht,
// weil sie über HTTP/2 und HTTP/3 fehlen darf.
async function begrenztLesen(request, max) {
  if (!request.body) return "";
  const leser = request.body.getReader();
  const teile = [];
  let laenge = 0;
  for (;;) {
    const { done, value } = await leser.read();
    if (done) break;
    laenge += value.byteLength;
    if (laenge > max) {
      await leser.cancel();
      return null;
    }
    teile.push(value);
  }
  const alles = new Uint8Array(laenge);
  let pos = 0;
  for (const t of teile) {
    alles.set(t, pos);
    pos += t.byteLength;
  }
  return new TextDecoder().decode(alles);
}

async function koerperLesen(request) {
  const laenge = request.headers.get("Content-Length");
  if (laenge !== null && (!/^\d+$/.test(laenge) || Number(laenge) > MAX_KOERPER)) {
    return { fehler: json(413, { fehler: "Anfrage zu groß" }) };
  }
  let text;
  try {
    text = await begrenztLesen(request, MAX_KOERPER);
  } catch {
    return { fehler: json(400, { fehler: "Ungültige Anfrage" }) };
  }
  if (text === null) return { fehler: json(413, { fehler: "Anfrage zu groß" }) };
  try {
    const daten = JSON.parse(text || "{}");
    if (!daten || typeof daten !== "object" || Array.isArray(daten)) throw new Error();
    return { daten };
  } catch {
    return { fehler: json(400, { fehler: "Ungültige Anfrage" }) };
  }
}

function text(wert, max) {
  return typeof wert === "string" ? Array.from(wert).slice(0, max).join("") : "";
}

function client(env) {
  return new Anthropic({
    apiKey: env.ANTHROPIC_API_KEY,
    // Nur für Tests am Rechner (wrangler dev mit nachgebildetem Sprachmodell), in Cloudflare nie gesetzt
    ...(env.ANTHROPIC_BASE_URL ? { baseURL: env.ANTHROPIC_BASE_URL } : {}),
  });
}

async function frageBeantworten(env, wer, daten) {
  const gekuerzt = text(text(daten.frage, MAX_KOERPER).trim(), MAX_FRAGE_ZEICHEN);
  if (!gekuerzt) return json(400, { fehler: "Bitte eine Frage eingeben." });
  // Hilfsnummern immer, auch wenn das Tageslimit erreicht ist
  if (istKrise(gekuerzt)) return json(200, krisenAntwort(gekuerzt));

  const tag = tagHeute();
  const max = Number(env.SEYDA_MAX_FRAGEN || "100");
  const stand = await fragenHeute(env.DB, tag, wer.name);
  if (stand.gesamt >= max) return json(429, { fehler: "Das Tageslimit an Fragen ist erreicht. Morgen geht es weiter." });
  if (stand.person >= wer.tageslimit) {
    return json(429, { fehler: `Für heute ist dein Tageslimit erreicht (${wer.tageslimit} pro Tag). Morgen geht es weiter.` });
  }
  if (!env.ANTHROPIC_API_KEY) {
    return json(502, { fehler: "Der API Schlüssel fehlt. Bitte in Cloudflare als Secret ANTHROPIC_API_KEY hinterlegen." });
  }
  // Gezählt wird beim Absenden, auch wenn das Sprachmodell danach einen Fehler meldet
  await frageZaehlen(env.DB, tag, wer.name);

  const kosten = [];
  try {
    return json(200, await antworten(client(env), env.DB, gekuerzt, verlaufPruefen(daten.verlauf), kosten));
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) {
      return json(502, { fehler: "Der API Schlüssel ist ungültig (Cloudflare Secret ANTHROPIC_API_KEY)." });
    }
    if (e instanceof Anthropic.RateLimitError) {
      return json(503, { fehler: "Gerade zu viele Anfragen. Bitte gleich noch einmal versuchen." });
    }
    if (e instanceof Anthropic.APIConnectionError) {
      return json(503, { fehler: "Keine Verbindung zum Sprachmodell." });
    }
    if (e instanceof Anthropic.APIError) {
      console.error("API Fehler:", e.status, e.message);
      return json(502, { fehler: "Fehler beim Sprachmodell. Bitte später noch einmal versuchen." });
    }
    throw e;
  } finally {
    try {
      await verbrauchBuchen(env.DB, tag, kosten);
    } catch (e) {
      console.error("Verbrauch nicht gespeichert:", e?.message);
    }
  }
}

async function bearbeiten(request, env) {
  const url = new URL(request.url);
  const pfad = url.pathname;

  if (request.method === "GET" && pfad === "/api/status") {
    const wer = await sitzungPruefen(env.DB, cookieLesen(request));
    if (!wer) return json(401, { fehler: "Bitte anmelden.", anmelden: true });
    return json(200, { online: true, name: wer.name, sitzung: true });
  }

  if (request.method !== "POST") return json(404, { fehler: "Nicht gefunden" });
  if (!gleicheHerkunft(request)) return json(403, { fehler: "Anfrage abgelehnt." });
  const { daten, fehler } = await koerperLesen(request);
  if (fehler) return fehler;

  if (pfad === "/api/anmelden") {
    // Manche Handytastaturen schicken ş als s plus Häkchen; NFC macht daraus wieder ein Zeichen wie beim Anlegen
    const name = text(daten.name, 100).normalize("NFC").trim();
    const code = text(daten.code, 200).trim().toLowerCase().replace(/\s+/g, "");
    const wer = NAME_MUSTER.test(name) && code ? await zugangPruefen(env.DB, name, code) : null;
    if (!wer) return json(401, { fehler: "Name oder Zugangscode stimmt nicht.", anmelden: true });
    const { token, sekunden } = await sitzungAnlegen(env.DB, wer.name);
    return json(200, { ok: true, name: wer.name }, { "Set-Cookie": cookieSetzen(token, sekunden) });
  }

  if (pfad === "/api/abmelden") {
    await sitzungBeenden(env.DB, cookieLesen(request));
    return json(200, { ok: true }, { "Set-Cookie": cookieSetzen("", 0) });
  }

  const wer = await sitzungPruefen(env.DB, cookieLesen(request));
  if (!wer) return json(401, { fehler: "Bitte erneut anmelden.", anmelden: true });

  if (pfad === "/api/frage") return await frageBeantworten(env, wer, daten);

  if (pfad === "/api/melden") {
    // Nur auf ausdrücklichen Knopfdruck wird eine Frage samt Antwort gespeichert
    await meldungSpeichern(
      env.DB,
      new Date().toISOString().slice(0, 19) + "+00:00",
      text(daten.frage, MAX_FRAGE_ZEICHEN),
      text(daten.antwort, 10000),
      text(JSON.stringify(Array.isArray(daten.quellen) ? daten.quellen : []), 5000),
      text(daten.notiz, 2000),
    );
    return json(200, { ok: true });
  }

  return json(404, { fehler: "Nicht gefunden" });
}

export default {
  async fetch(request, env) {
    const pfad = new URL(request.url).pathname;
    if (!pfad.startsWith("/api/")) return json(404, { fehler: "Nicht gefunden" });
    try {
      return await bearbeiten(request, env);
    } catch (e) {
      // Keine Fragen ins Protokoll, nur die Art des Fehlers
      console.error("Interner Fehler:", e?.name, e?.message);
      return json(500, { fehler: "Interner Fehler. Bitte später noch einmal versuchen." });
    }
  },
};
