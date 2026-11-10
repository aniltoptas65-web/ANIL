// Nachgebildete Claude API für Tests mit "wrangler dev": antwortet wie die echte API, aber ohne Kosten.
// Start: node test/modell_nachbildung.mjs 8799
// In .dev.vars: ANTHROPIC_API_KEY=sk-ant-test-schluessel und ANTHROPIC_BASE_URL=http://127.0.0.1:8799
// Sonderfälle über die Frage: "FEHLER401" (Schlüssel ungültig), "FEHLER429" (zu viele Anfragen), "LANGSAM" (8 s Pause)
import { createServer } from "node:http";

const port = Number(process.argv[2] || 8799);
const protokoll = [];

function antwort(text, extra = {}) {
  return {
    id: "msg_test", type: "message", role: "assistant", model: extra.model || "claude-haiku-5-5",
    content: extra.content || [{ type: "text", text }], stop_reason: "end_turn", stop_sequence: null,
    usage: { input_tokens: 100, output_tokens: 20 },
  };
}

createServer(async (req, res) => {
  let roh = "";
  for await (const teil of req) roh += teil;
  if (req.url === "/protokoll") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify(protokoll));
  }
  const body = roh ? JSON.parse(roh) : {};
  // Die SDKs schicken den Schlüssel als "Authorization: Bearer", ältere als x-api-key
  const schluessel = req.headers["x-api-key"] || (req.headers.authorization || "").replace(/^Bearer /, "") || null;
  protokoll.push({ pfad: req.url, schluessel, beta: req.headers["anthropic-beta"] || null, version: req.headers["anthropic-version"], body });
  const senden = (status, daten) => { res.writeHead(status, { "content-type": "application/json", "request-id": "req_test" }); res.end(JSON.stringify(daten)); };
  const nachricht = JSON.stringify(body.messages || "");
  if (nachricht.includes("FEHLER401") || schluessel !== "sk-ant-test-schluessel") {
    return senden(401, { type: "error", error: { type: "authentication_error", message: "invalid x-api-key" } });
  }
  // Schlüsselprüfung von startpruefung.py
  if (req.method === "GET" && req.url.startsWith("/v1/models")) {
    return senden(200, { data: [{ type: "model", id: "claude-haiku-5-5", display_name: "Haiku", created_at: "2026-01-01T00:00:00Z" }], has_more: false, first_id: "claude-haiku-5-5", last_id: "claude-haiku-5-5" });
  }
  if (!req.url.startsWith("/v1/messages")) return senden(404, { type: "error", error: { type: "not_found_error", message: "nicht da" } });
  if (nachricht.includes("FEHLER429")) return senden(429, { type: "error", error: { type: "rate_limit_error", message: "zu viele" } });
  if (nachricht.includes("LANGSAM")) await new Promise((r) => setTimeout(r, 8000));

  if (body.system.startsWith("Du bereitest")) {
    const neu = body.messages[0].content.split("Neue Nachricht: ").pop();
    const tr = /[şğı]|nelerdir|nedir/.test(neu);
    return senden(200, antwort(JSON.stringify({ frage: neu, rueckfrage: /verstanden|einfacher/.test(neu), sprache: tr ? "tr" : "de", begriffe: ["namaz", "farz", "abdest", "oruç", "kıble"] })));
  }
  if (body.system.startsWith("Du bekommst eine Frage")) {
    const anzahl = (body.messages[0].content.match(/^\[\d+\]/gm) || []).length;
    return senden(200, antwort(JSON.stringify({ nummern: [...Array(Math.min(anzahl, 4)).keys()] })));
  }
  // Sonnet: aus den Suchergebnissen eine gegliederte Antwort mit Belegen bauen
  const letzte = body.messages[body.messages.length - 1].content;
  const ergebnisse = letzte.filter((b) => b.type === "search_result");
  const beleg = (i) => [{ type: "search_result_location", source: ergebnisse[i].source, title: ergebnisse[i].title, cited_text: ergebnisse[i].content[0].text.slice(0, 80), search_result_index: i, start_block_index: 0, end_block_index: 1 }];
  const content = [
    { type: "thinking", thinking: "kurz", signature: "x" },
    { type: "text", text: "Das Gebet hat feste Pflichtteile.", citations: beleg(0) },
    { type: "text", text: "\n\n1. " },
    { type: "text", text: "**Namaz** (Gebet): ", citations: null },
    { type: "text", text: "fünfmal am Tag", citations: beleg(Math.min(1, ergebnisse.length - 1)) },
    { type: "text", text: "\n2. **Abdest** (Waschung): " },
    { type: "text", text: "vor dem Gebet", citations: beleg(0) },
    { type: "text", text: "\n\nDas ist ganz sicher so." },
  ];
  return senden(200, antwort(null, { model: "claude-sonnet-5-5", content }));
}).listen(port, "127.0.0.1", () => console.log(`Nachgebildete Claude API auf http://127.0.0.1:${port}`));
