"""Kleiner Webserver für den internen Test von SeydaAI.

Start:  python server.py
Dann im Browser http://127.0.0.1:8000 öffnen. Benutzername beliebig, Passwort aus SEYDA_PASSWORT.
"""

import base64
import hmac
import json
import os
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic

from datenbank import fragen_heute, verbinden
from seyda import antworten, ist_krise, krisen_antwort

PORT = int(os.environ.get("SEYDA_PORT", "8000"))
PASSWORT = os.environ.get("SEYDA_PASSWORT", "")
MAX_FRAGEN_PRO_TAG = int(os.environ.get("SEYDA_MAX_FRAGEN", "50"))
MAX_FRAGE_ZEICHEN = 1000
MAX_KOERPER = 20000
WEB = os.path.join(os.path.dirname(__file__), "web")

con = verbinden()
sperre = threading.Lock()  # eine Anfrage nach der anderen, die SQLite Verbindung wird geteilt
_client = None


def client() -> anthropic.Anthropic:
    """Legt den Client erst bei der ersten Frage an, damit ein fehlender Schlüssel eine klare Meldung ergibt."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # liest ANTHROPIC_API_KEY aus der Umgebung
    return _client


class Handler(BaseHTTPRequestHandler):
    def _angemeldet(self) -> bool:
        kopf = self.headers.get("Authorization", "")
        if not kopf.startswith("Basic ") or not PASSWORT:
            return False
        try:
            _, _, pw = base64.b64decode(kopf[6:]).decode("utf-8").partition(":")
        except Exception:
            return False
        return hmac.compare_digest(pw.encode("utf-8"), PASSWORT.encode("utf-8"))

    def _gleiche_herkunft(self) -> bool:
        """Schutz davor, dass eine fremde Webseite im Hintergrund Fragen stellt."""
        herkunft = self.headers.get("Origin")
        if herkunft and herkunft not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return False
        return self.headers.get("Content-Type", "").startswith("application/json")

    def _senden(self, code: int, inhalt: bytes, typ: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(inhalt)

    def _json(self, code: int, daten: dict) -> None:
        self._senden(code, json.dumps(daten, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _sperre(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="SeydaAI", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._angemeldet():
            return self._sperre()
        if self.path in ("/", "/index.html"):
            with open(os.path.join(WEB, "index.html"), "rb") as f:
                return self._senden(200, f.read(), "text/html; charset=utf-8")
        self._senden(404, b"Nicht gefunden", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._angemeldet():
            return self._sperre()
        if not self._gleiche_herkunft():
            return self._json(403, {"fehler": "Anfrage abgelehnt."})
        try:
            laenge = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._json(400, {"fehler": "Ungültige Anfrage"})
        if not 0 <= laenge <= MAX_KOERPER:
            return self._json(413, {"fehler": "Anfrage zu groß"})
        try:
            daten = json.loads(self.rfile.read(laenge) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json(400, {"fehler": "Ungültige Anfrage"})
        if not isinstance(daten, dict):
            return self._json(400, {"fehler": "Ungültige Anfrage"})
        with sperre:
            try:
                self._post(daten)
            except Exception:
                traceback.print_exc()
                self._json(500, {"fehler": "Interner Fehler. Details stehen im Terminal."})

    def _post(self, daten: dict):
        if self.path == "/api/frage":
            frage = str(daten.get("frage", "")).strip()[:MAX_FRAGE_ZEICHEN]
            if not frage:
                return self._json(400, {"fehler": "Bitte eine Frage eingeben."})
            # Hilfsnummern immer, auch wenn das Tageslimit erreicht ist
            if ist_krise(frage):
                return self._json(200, krisen_antwort(frage))
            if fragen_heute(con) >= MAX_FRAGEN_PRO_TAG:
                return self._json(429, {"fehler": "Das Tageslimit an Fragen ist erreicht. Morgen geht es weiter."})
            try:
                return self._json(200, antworten(client(), con, frage))
            except anthropic.AuthenticationError:
                return self._json(502, {"fehler": "Der API Schlüssel fehlt oder ist ungültig (ANTHROPIC_API_KEY)."})
            except anthropic.RateLimitError:
                return self._json(503, {"fehler": "Gerade zu viele Anfragen. Bitte gleich noch einmal versuchen."})
            except anthropic.APIConnectionError:
                return self._json(503, {"fehler": "Keine Verbindung zum Sprachmodell."})
            except anthropic.APIStatusError as e:
                print("API Fehler:", e.status_code, e.message)
                return self._json(502, {"fehler": "Fehler beim Sprachmodell. Details stehen im Terminal."})
            except anthropic.AnthropicError as e:
                print("Fehler:", e)
                return self._json(502, {"fehler": "Der API Schlüssel fehlt (ANTHROPIC_API_KEY) oder das Sprachmodell meldet einen Fehler."})

        if self.path == "/api/melden":
            # Nur auf ausdrücklichen Knopfdruck wird eine Frage samt Antwort gespeichert
            con.execute(
                "INSERT INTO meldungen VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    str(daten.get("frage", ""))[:MAX_FRAGE_ZEICHEN],
                    str(daten.get("antwort", ""))[:10000],
                    json.dumps(daten.get("quellen", []), ensure_ascii=False)[:5000],
                    str(daten.get("notiz", ""))[:2000],
                ),
            )
            con.commit()
            return self._json(200, {"ok": True})

        self._json(404, {"fehler": "Nicht gefunden"})

    def log_message(self, fmt, *args):
        # Keine Fragen ins Protokoll schreiben, nur Methode, Pfad und Status
        print(f"{self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}")


if __name__ == "__main__":
    if not PASSWORT:
        raise SystemExit("Bitte zuerst ein Passwort setzen: SEYDA_PASSWORT")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit("Bitte zuerst den API Schlüssel setzen: ANTHROPIC_API_KEY")
    print(f"SeydaAI läuft auf http://127.0.0.1:{PORT}  (beenden mit Strg+C)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
