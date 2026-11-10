"""Liest öffentliche Seiten der Quellen ein und speichert sie in seyda.db.

Aufruf:  python einlesen.py              (alle Quellen aus quellen.json)
         python einlesen.py diyanet      (nur eine Quelle, Kurzname aus quellen.json)
         python einlesen.py --neu        (auch schon gespeicherte Seiten neu abrufen)

Seiten, die in den letzten NEU_NACH_TAGEN Tagen nach denselben Regeln gespeichert wurden, ruft das Skript
nicht noch einmal ab. Ein abgebrochener Lauf lässt sich so einfach fortsetzen. Ändern sich die Regeln einer
Quelle in quellen.json (folgen, speichern, links_aus, max_tiefe), wird sie neu eingelesen.

Das Skript fragt langsam ab (Pause zwischen den Seiten), hält sich an robots.txt
und bleibt innerhalb der in quellen.json erlaubten Adressen.
"""

import hashlib
import html
import json
import re
import sys
import time
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

from datenbank import fremde_quellen_entfernen, quellen_laden, verbinden

PAUSE_SEKUNDEN = 2.0
NEU_NACH_TAGEN = 30
ABSCHNITT_ZEICHEN = 1500
KENNUNG = "SeydaAI Prototyp (Reyhani Europa e.V., interner Test)"

UNWICHTIG = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg"]


def text_holen(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """Gibt Titel und Absätze des Hauptinhalts zurück. Verändert soup (entfernt Menüs usw.)."""
    titel = (soup.title.string or "").strip() if soup.title else ""
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        titel = h1.get_text(" ", strip=True)
    for tag in soup(UNWICHTIG):
        tag.decompose()
    haupt = soup.find("article") or soup.find("main") or soup.body or soup
    absaetze = []
    for el in haupt.find_all(["p", "li", "h2", "h3", "h4", "blockquote", "td"]):
        t = el.get_text(" ", strip=True)
        if len(t) >= 40 and t not in absaetze:
            absaetze.append(t)
    return titel, absaetze


def zerlegen(absaetze: list[str]) -> list[str]:
    """Fasst Absätze zu Abschnitten von etwa ABSCHNITT_ZEICHEN Zeichen zusammen."""
    abschnitte, aktuell = [], ""
    for a in absaetze:
        if aktuell and len(aktuell) + len(a) > ABSCHNITT_ZEICHEN:
            abschnitte.append(aktuell)
            aktuell = ""
        aktuell = (aktuell + "\n" + a).strip()
    if aktuell:
        abschnitte.append(aktuell)
    return abschnitte


def erlaubt(url: str, praefixe: list[str]) -> bool:
    return any(url.startswith(p) for p in praefixe)


def robots_fuer(url: str, cache: dict):
    """robots.txt der Domain. Ist sie gesperrt (401, 403), gilt alles als verboten."""
    basis = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if basis not in cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            antwort = requests.get(basis + "/robots.txt", timeout=20, headers={"User-Agent": KENNUNG})
            if antwort.status_code in (401, 403):
                rp.parse(["User-agent: *", "Disallow: /"])
            elif antwort.status_code == 200:
                rp.parse(antwort.text.splitlines())
            else:
                rp.parse([])
        except requests.RequestException:
            rp.parse([])
        cache[basis] = rp
    return cache[basis]


def _muster(liste) -> list:
    return [re.compile(m) for m in (liste or [])]


def regel_von(quelle: dict) -> str:
    """Kurzer Fingerabdruck der Einleseregeln. Startadressen und max_seiten zählen nicht dazu,
    damit neue Startadressen oder ein höheres Limit nicht alles neu laden."""
    teile = {k: quelle.get(k) for k in ("folgen", "erlaubt", "speichern", "links_aus", "max_tiefe", "nur_zusammenfassen")}
    return hashlib.sha256(json.dumps(teile, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _im_menue(a) -> bool:
    """Links in Kopf, Fußzeile und Menüs führen meist zu Firmen und Kontaktseiten, nicht zu Inhalten.
    Ausnahme: ein nav Bereich zum Blättern (pagination, sayfalama)."""
    if a.find_parent(["header", "footer"]):
        return True
    nav = a.find_parent("nav")
    if not nav:
        return False
    # Kennzeichen des Blätterns am Link selbst oder an einem Element zwischen Link und nav
    kennung = ""
    for el in [a] + list(a.parents):
        kennung += " " + " ".join([el.get("id") or "", el.get("aria-label") or "", " ".join(el.get("class") or []), el.get("rel") and " ".join(el.get("rel")) or ""])
        if el is nav:
            break
    return not any(w in kennung.lower() for w in ("pag", "sayfa", "next", "prev", "sonraki", "önceki"))


def sitemap_adressen(sitzung, adresse: str, robots: dict, tiefe: int = 0) -> list[str]:
    """Liest Adressen aus einer Sitemap (auch Sitemap Index, höchstens zwei Ebenen). Fehler werden übergangen."""
    if tiefe > 1 or not robots_fuer(adresse, robots).can_fetch(KENNUNG, adresse):
        return []
    try:
        antwort = sitzung.get(adresse, timeout=30)
    except requests.RequestException:
        return []
    finally:
        time.sleep(PAUSE_SEKUNDEN)
    if antwort.status_code != 200:
        return []
    orte = []
    for o in re.findall(r"<loc>(.*?)</loc>", antwort.text, re.DOTALL):
        o = o.strip()
        if o.startswith("<![CDATA[") and o.endswith("]]>"):
            o = o[9:-3].strip()
        orte.append(html.unescape(o))
    if "<sitemapindex" in antwort.text:
        unter = []
        for o in orte[:20]:
            unter += sitemap_adressen(sitzung, o, robots, tiefe + 1)
        return unter
    return orte


def quelle_einlesen(con, quelle: dict, neu: bool = False) -> int:
    """Liest eine Quelle ein.

    Felder in quellen.json:
      start       Startadressen
      folgen      Adressanfänge, denen das Skript folgen darf (ältere Dateien: erlaubt)
      speichern   Muster (regulärer Ausdruck); nur passende Seiten kommen in die Datenbank, die anderen dienen nur als Wegweiser
      links_aus   Muster; Links werden nur aus passenden Seiten gesammelt (sonst aus allen)
      max_tiefe   wie viele Klicks weit von den Startadressen aus gegangen wird (ohne Angabe unbegrenzt)
      sitemaps    Sitemaps, deren Adressen zusätzlich abgerufen werden
      max_seiten  höchstens so viele gespeicherte Seiten
    """
    folgen = quelle.get("folgen") or quelle.get("erlaubt") or []
    speichern = _muster(quelle.get("speichern"))
    links_aus = _muster(quelle.get("links_aus"))
    max_tiefe = quelle.get("max_tiefe")
    regel = regel_von(quelle)

    def soll_speichern(url: str) -> bool:
        return not speichern or any(m.search(url) for m in speichern)

    def ist_wegweiser(url: str) -> bool:
        """Seiten, aus denen Links gesammelt werden (ohne links_aus: alle)."""
        return not links_aus or any(m.search(url) for m in links_aus)

    # Alte Seiten dieser Quelle entfernen: nach anderen Regeln eingelesen (zum Beispiel Menü und Firmenseiten
    # aus einem früheren Lauf) oder nicht mehr passend zum Muster
    alte = [(z[0], z[1]) for z in con.execute("SELECT url, regel FROM seiten WHERE quelle = ?", (quelle["name"],))]
    weg = [u for u, r in alte if not quelle["start"] or r != regel or not soll_speichern(u)]
    for u in weg:
        con.execute("DELETE FROM abschnitte WHERE url = ?", (u,))
        con.execute("DELETE FROM seiten WHERE url = ?", (u,))
    con.commit()
    if weg:
        print(f"  {len(weg)} alte Seiten entfernt (früherer Lauf mit anderen Regeln oder ohne passenden Inhalt)")

    if not quelle["start"]:
        print(f"[{quelle['kurz']}] keine Startadresse eingetragen, übersprungen")
        return 0

    # Schon vorhandene, frische Seiten nicht noch einmal abrufen (Fortsetzen nach Abbruch)
    grenze = (datetime.now(timezone.utc) - timedelta(days=NEU_NACH_TAGEN)).isoformat(timespec="seconds")
    frisch = set() if neu else {
        z[0] for z in con.execute(
            "SELECT url FROM seiten WHERE quelle = ? AND regel = ? AND abgerufen >= ?", (quelle["name"], regel, grenze)
        )
    }

    sitzung = requests.Session()
    sitzung.headers["User-Agent"] = KENNUNG
    robots = {}
    warteschlange = [(urldefrag(u)[0], 0) for u in quelle["start"]]
    for karte in quelle.get("sitemaps", []):
        gefunden = [urldefrag(u)[0] for u in sitemap_adressen(sitzung, karte, robots)]
        gefunden = [u for u in gefunden if erlaubt(u, folgen)]
        print(f"  Sitemap {karte}: {len(gefunden)} passende Adressen")
        warteschlange += [(u, 0) for u in gefunden]
    vorgemerkt = {u for u, _ in warteschlange}
    gesehen, gespeichert, abrufe, uebersprungen = set(), 0, 0, 0
    max_abrufe = quelle["max_seiten"] * 5  # Obergrenze gegen endlose Adressräume (Kalender, Seitenzahlen)

    while warteschlange and gespeichert < quelle["max_seiten"] and abrufe < max_abrufe:
        url, tiefe = warteschlange.pop(0)
        if url in gesehen or not erlaubt(url, folgen):
            continue
        gesehen.add(url)
        # Frische Seiten überspringen, außer sie sind Wegweiser zu weiteren Seiten
        if url in frisch and not ist_wegweiser(url):
            gespeichert += 1
            uebersprungen += 1
            continue
        regeln = robots_fuer(url, robots)
        if not regeln.can_fetch(KENNUNG, url):
            print(f"  robots.txt verbietet {url}")
            continue
        abrufe += 1
        try:
            antwort = sitzung.get(url, timeout=30)
        except requests.RequestException as e:
            print(f"  Fehler bei {url}: {e}")
            continue
        finally:
            time.sleep(max(PAUSE_SEKUNDEN, float(regeln.crawl_delay(KENNUNG) or 0)))
        if antwort.status_code != 200 or "text/html" not in antwort.headers.get("Content-Type", ""):
            continue

        # Nach einer Weiterleitung zählt die tatsächliche Adresse
        ziel_url = urldefrag(antwort.url)[0]
        if ziel_url != url:
            if not erlaubt(ziel_url, folgen) or ziel_url in gesehen:
                continue
            if not robots_fuer(ziel_url, robots).can_fetch(KENNUNG, ziel_url):
                continue
            gesehen.add(ziel_url)
            url = ziel_url

        # Bytes übergeben, damit BeautifulSoup die Zeichenkodierung selbst erkennt
        soup = BeautifulSoup(antwort.content, "html.parser")
        darf_weiter = max_tiefe is None or tiefe < max_tiefe
        if darf_weiter and ist_wegweiser(url):
            for a in soup.find_all("a", href=True):
                if _im_menue(a):
                    continue
                ziel = urldefrag(urljoin(url, a["href"]))[0]
                if erlaubt(ziel, folgen) and ziel not in gesehen and ziel not in vorgemerkt:
                    vorgemerkt.add(ziel)
                    warteschlange.append((ziel, tiefe + 1))

        if not soll_speichern(url):
            continue
        titel, absaetze = text_holen(soup)
        abschnitte = zerlegen(absaetze)
        if not abschnitte:
            continue
        jetzt = datetime.now(timezone.utc).isoformat(timespec="seconds")
        con.execute("DELETE FROM abschnitte WHERE url = ?", (url,))
        con.execute(
            "INSERT OR REPLACE INTO seiten (url, quelle, titel, abgerufen, regel) VALUES (?, ?, ?, ?, ?)",
            (url, quelle["name"], titel, jetzt, regel),
        )
        for text in abschnitte:
            con.execute(
                "INSERT INTO abschnitte (text, titel, url, quelle, nur_zusammenfassen) VALUES (?, ?, ?, ?, ?)",
                (text, titel, url, quelle["name"], int(quelle["nur_zusammenfassen"])),
            )
        con.commit()
        gespeichert += 1
        print(f"  [{gespeichert}] {titel[:70]}  ({url})")
    if uebersprungen:
        print(f"  {uebersprungen} Seiten waren schon da und wurden nicht neu abgerufen")
    return gespeichert


def main():
    argumente = sys.argv[1:]
    neu = "--neu" in argumente
    namen = [a for a in argumente if not a.startswith("--")]
    nur = namen[0] if namen else None
    quellen = quellen_laden()
    if nur and nur not in [q["kurz"] for q in quellen]:
        raise SystemExit(f"Unbekannte Quelle: {nur}. Möglich: {', '.join(q['kurz'] for q in quellen)}")
    con = verbinden()
    entfernt = fremde_quellen_entfernen(con)
    if entfernt:
        print(f"{entfernt} Seiten von Quellen entfernt, die nicht mehr in quellen.json stehen\n")
    for q in quellen:
        if nur and q["kurz"] != nur:
            continue
        print(f"Quelle: {q['name']}")
        anzahl = quelle_einlesen(con, q, neu)
        print(f"Fertig: {anzahl} {'Seite' if anzahl == 1 else 'Seiten'} von {q['name']}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEinlesen abgebrochen. Die bisher eingelesenen Seiten bleiben gespeichert.")
        sys.exit(1)
