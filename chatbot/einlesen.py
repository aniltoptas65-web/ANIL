"""Liest öffentliche Seiten der Quellen ein und speichert sie in seyda.db.

Aufruf:  python einlesen.py            (alle Quellen aus quellen.json)
         python einlesen.py diyanet    (nur eine Quelle, Kurzname aus quellen.json)

Das Skript fragt langsam ab (Pause zwischen den Seiten), hält sich an robots.txt
und bleibt innerhalb der in quellen.json erlaubten Adressen.
"""

import json
import os
import sys
import time
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

from datenbank import verbinden

PAUSE_SEKUNDEN = 2.0
ABSCHNITT_ZEICHEN = 1500
KENNUNG = "SeydaAI Prototyp (Reyhani Europa e.V., interner Test)"

UNWICHTIG = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg"]


def quellen_laden() -> list[dict]:
    with open(os.path.join(os.path.dirname(__file__), "quellen.json"), encoding="utf-8") as f:
        return json.load(f)["quellen"]


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


def quelle_einlesen(con, quelle: dict) -> int:
    if not quelle["start"]:
        print(f"[{quelle['kurz']}] keine Startadresse eingetragen, übersprungen")
        return 0
    warteschlange = [urldefrag(u)[0] for u in quelle["start"]]
    vorgemerkt = set(warteschlange)
    gesehen, gespeichert, abrufe, robots = set(), 0, 0, {}
    max_abrufe = quelle["max_seiten"] * 5  # Obergrenze gegen endlose Adressräume (Kalender, Seitenzahlen)
    sitzung = requests.Session()
    sitzung.headers["User-Agent"] = KENNUNG

    while warteschlange and gespeichert < quelle["max_seiten"] and abrufe < max_abrufe:
        url = warteschlange.pop(0)
        if url in gesehen or not erlaubt(url, quelle["erlaubt"]):
            continue
        gesehen.add(url)
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
            if not erlaubt(ziel_url, quelle["erlaubt"]) or ziel_url in gesehen:
                continue
            if not robots_fuer(ziel_url, robots).can_fetch(KENNUNG, ziel_url):
                continue
            gesehen.add(ziel_url)
            url = ziel_url

        # Bytes übergeben, damit BeautifulSoup die Zeichenkodierung selbst erkennt
        soup = BeautifulSoup(antwort.content, "html.parser")
        for a in soup.find_all("a", href=True):
            ziel = urldefrag(urljoin(url, a["href"]))[0]
            if erlaubt(ziel, quelle["erlaubt"]) and ziel not in gesehen and ziel not in vorgemerkt:
                vorgemerkt.add(ziel)
                warteschlange.append(ziel)

        titel, absaetze = text_holen(soup)
        abschnitte = zerlegen(absaetze)
        if not abschnitte:
            continue
        jetzt = datetime.now(timezone.utc).isoformat(timespec="seconds")
        con.execute("DELETE FROM abschnitte WHERE url = ?", (url,))
        con.execute(
            "INSERT OR REPLACE INTO seiten VALUES (?, ?, ?, ?)", (url, quelle["name"], titel, jetzt)
        )
        for text in abschnitte:
            con.execute(
                "INSERT INTO abschnitte (text, titel, url, quelle, nur_zusammenfassen) VALUES (?, ?, ?, ?, ?)",
                (text, titel, url, quelle["name"], int(quelle["nur_zusammenfassen"])),
            )
        con.commit()
        gespeichert += 1
        print(f"  [{gespeichert}] {titel[:70]}  ({url})")
    return gespeichert


def main():
    nur = sys.argv[1] if len(sys.argv) > 1 else None
    con = verbinden()
    for q in quellen_laden():
        if nur and q["kurz"] != nur:
            continue
        print(f"Quelle: {q['name']}")
        anzahl = quelle_einlesen(con, q)
        print(f"Fertig: {anzahl} {'Seite' if anzahl == 1 else 'Seiten'} von {q['name']}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nEinlesen abgebrochen. Die bisher eingelesenen Seiten bleiben gespeichert.")
        sys.exit(1)
