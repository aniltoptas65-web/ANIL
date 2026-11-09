"""Prüfset: stellt 20 Grundfragen und eine Rückfrage und schreibt die Antworten in einen Bericht.

Aufruf:  python pruefset.py
Braucht ANTHROPIC_API_KEY und eingelesene Quellen. Kostet geschätzt 20 bis 60 US Cent pro Lauf.
Der Bericht landet als pruefbericht_JJJJ-MM-TT_HHMM.md im Ordner von SeydaAI. So lässt sich vorher
und nachher vergleichen, ob eine Änderung die Antworten besser macht.
Die Fragen zählen zum Tageslimit (SEYDA_MAX_FRAGEN), weil sie wie echte Fragen an Claude gehen.
"""

import os
import sys
from datetime import datetime

import anthropic

from datenbank import fragen_heute, verbinden
from seyda import antworten, verlauf_pruefen

FRAGEN = [
    "Was sind die Säulen des Islams?",
    "İslam'ın şartları nelerdir?",
    "Was sind die Glaubensgrundsätze im Islam?",
    "İmanın şartları nelerdir?",
    "Was macht das Abdest ungültig?",
    "Abdesti bozan durumlar nelerdir?",
    "Welche Pflichtteile hat das Gebet?",
    "Namazın farzları nelerdir?",
    "Was bricht das Fasten?",
    "Orucu bozan şeyler nelerdir?",
    "Wer muss Zekat geben?",
    "Zekât kimlere verilir?",
    "Wer muss die Hac machen?",
    "Kurban kimlere vaciptir?",
    "Was bedeutet mekruh?",
    "Teyemmüm nasıl yapılır?",
    "Wann ist Gusül Pflicht?",
    "Cuma namazı kimlere farzdır?",
    "Was ist Tasavvuf?",
    "Rabıta nedir?",
]
RUECKFRAGE = "Das habe ich nicht verstanden, bitte einfacher erklären."

# US Dollar pro Million Tokens laut Anthropic (Stand 9. November 2026), Eingabe und Ausgabe
PREISE = {"claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}


def eintrag(nr: str, frage: str, ergebnis: dict) -> str:
    zeilen = [f"## {nr}. {frage}", "", f"Ergebnis: {ergebnis.get('art', 'fehler')}", ""]
    zeilen.append(ergebnis.get("antwort", ""))
    if ergebnis.get("quellen"):
        zeilen += ["", "Quellen:"]
        zeilen += [f"- {q['quelle']}: {q['titel']} ({q['url']})" for q in ergebnis["quellen"]]
    return "\n".join(zeilen) + "\n"


def main() -> int:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("Bitte zuerst den API Schlüssel setzen: ANTHROPIC_API_KEY")
        return 1
    con = verbinden()
    if not con.execute("SELECT COUNT(*) FROM seiten").fetchone()[0]:
        print("Es sind noch keine Quellen eingelesen. Bitte zuerst einlesen.")
        return 1
    limit = int(os.environ.get("SEYDA_MAX_FRAGEN", "50"))
    if fragen_heute(con) + len(FRAGEN) + 1 > limit:
        print(f"Das Prüfset braucht {len(FRAGEN) + 1} Fragen, heute sind aber nur noch {max(limit - fragen_heute(con), 0)} "
              f"von {limit} frei. Bitte morgen laufen lassen oder SEYDA_MAX_FRAGEN erhöhen.")
        return 1
    client = anthropic.Anthropic()
    beginn = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM verbrauch").fetchone()[0]
    teile, zaehler = [], {}

    def fragen(nr, frage, verlauf=None):
        print(f"[{nr}/{len(FRAGEN) + 1}] {frage}")
        try:
            ergebnis = antworten(client, con, frage, verlauf)
        except anthropic.AnthropicError as e:
            ergebnis = {"art": "fehler", "antwort": f"Fehler: {type(e).__name__}"}
        zaehler[ergebnis.get("art", "fehler")] = zaehler.get(ergebnis.get("art", "fehler"), 0) + 1
        teile.append(eintrag(str(nr), frage, ergebnis))
        return ergebnis

    erste = None
    for i, frage in enumerate(FRAGEN, 1):
        ergebnis = fragen(i, frage)
        if i == 1:
            erste = ergebnis
    # Rückfrage zur ersten Antwort, so wie der Browser den Verlauf schickt
    verlauf = verlauf_pruefen([{
        "frage": FRAGEN[0], "antwort": erste.get("antwort", ""), "quellen": [q["url"] for q in erste.get("quellen", [])],
        "abschnitte": erste.get("abschnitte", []),
    }])
    if erste.get("art") in ("antwort", "kein_treffer") and verlauf:
        fragen(len(FRAGEN) + 1, RUECKFRAGE, verlauf)

    kosten, ohne_preis = 0.0, []
    for modell, ein, aus in con.execute(
        "SELECT modell, SUM(eingabe), SUM(ausgabe) FROM verbrauch WHERE rowid > ? GROUP BY modell", (beginn,)
    ):
        preis = next((p for name, p in PREISE.items() if modell.startswith(name)), None)
        if preis:
            kosten += ein / 1e6 * preis[0] + aus / 1e6 * preis[1]
        else:
            ohne_preis.append(modell)  # zum Beispiel ein Ausweichmodell nach einer Ablehnung

    jetzt = datetime.now()
    kopf = [
        f"# SeydaAI Prüfbericht vom {jetzt:%d.%m.%Y %H:%M}",
        "",
        "Eingelesene Seiten: " + ", ".join(
            f"{q} {n}" for q, n in con.execute("SELECT quelle, COUNT(*) FROM seiten GROUP BY quelle ORDER BY quelle")
        ),
        "Ergebnisse: " + ", ".join(f"{art} {n}" for art, n in sorted(zaehler.items())),
        f"Kosten laut Tokenzählung: etwa {kosten:.2f} US Dollar".replace(".", ",", 1)
        + (f" (ohne {', '.join(ohne_preis)}, dafür ist kein Preis hinterlegt)" if ohne_preis else ""),
        "",
    ]
    datei = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"pruefbericht_{jetzt:%Y-%m-%d_%H%M}.md")
    with open(datei, "w", encoding="utf-8") as f:
        f.write("\n".join(kopf) + "\n" + "\n".join(teile))
    print()
    print("\n".join(kopf[2:5]))
    print(f"Bericht: {datei}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
