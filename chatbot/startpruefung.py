"""Kleine Prüfungen für das Windows Startskript starten.ps1.

  python startpruefung.py quellen      zeigt, wie viele Seiten je Quelle eingelesen sind (keine Ausgabe, wenn leer)
  python startpruefung.py schluessel   prüft den API Schlüssel aus ANTHROPIC_API_KEY mit einer kostenlosen Abfrage
                                       Rückgabe: 0 gültig, 2 ungültig, 1 unklar (zum Beispiel keine Verbindung oder 403)
"""

import sys


def quellen() -> int:
    from datenbank import verbinden

    con = verbinden()
    for quelle, anzahl in con.execute("SELECT quelle, COUNT(*) FROM seiten GROUP BY quelle ORDER BY quelle"):
        print(f"{quelle}: {anzahl} {'Seite' if anzahl == 1 else 'Seiten'}")
    alt = con.execute("SELECT COUNT(*) FROM seiten WHERE regel IS NULL").fetchone()[0]
    if alt:
        print(f"Achtung: {alt} Seiten stammen aus dem alten Einlesen (auch Menü und Firmenseiten). Bitte a wählen, dann werden sie ersetzt.")
    return 0


def schluessel() -> int:
    import anthropic

    try:
        # Die Liste der Modelle abzurufen kostet nichts und zeigt, ob der Schlüssel angenommen wird
        anthropic.Anthropic(max_retries=1, timeout=20).models.list(limit=1)
    except anthropic.AuthenticationError:
        return 2
    except anthropic.PermissionDeniedError:
        # 403 kann auch an Netz oder Region liegen, deshalb nicht als falscher Schlüssel werten
        print("Claude meldet keinen Zugriff (403). Das kann am Netzwerk oder an der Region liegen, nicht unbedingt am Schlüssel.")
        return 1
    except Exception as e:  # Netz, Zeitüberschreitung und Ähnliches: nicht entscheidbar
        print(f"Der Schlüssel ließ sich gerade nicht prüfen ({type(e).__name__}).")
        return 1
    return 0


if __name__ == "__main__":
    befehl = sys.argv[1] if len(sys.argv) > 1 else ""
    if befehl == "quellen":
        sys.exit(quellen())
    if befehl == "schluessel":
        sys.exit(schluessel())
    print(__doc__)
    sys.exit(1)
