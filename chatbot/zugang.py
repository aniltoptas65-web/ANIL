"""Zugänge für die Testgruppe verwalten.

  python zugang.py neu "Ayse K" 10   legt einen Zugang mit 10 Fragen pro Tag an und zeigt den Code einmal an
  python zugang.py liste             zeigt alle Zugänge und die Fragen von heute
  python zugang.py sperren "Ayse K"  sperrt den Zugang (Code gilt nicht mehr)
  python zugang.py loeschen "Ayse K" löscht den Zugang und seine Zählerstände

Einen neuen Code für dieselbe Person gibt es mit loeschen und danach neu.
"""

import sqlite3
import sys
from datetime import datetime

from datenbank import fragen_heute_person, verbinden, zugang_anlegen

STANDARD_LIMIT = 10


def main(argumente: list[str]) -> int:
    if not argumente or argumente[0] not in ("neu", "liste", "sperren", "loeschen"):
        print(__doc__)
        return 1
    befehl, rest = argumente[0], argumente[1:]
    con = verbinden()

    if befehl == "liste":
        zeilen = con.execute("SELECT name, tageslimit, aktiv, angelegt FROM zugaenge ORDER BY name").fetchall()
        if not zeilen:
            print("Noch keine Zugänge angelegt.")
        for z in zeilen:
            zustand = "aktiv" if z["aktiv"] else "gesperrt"
            tag = datetime.fromisoformat(z["angelegt"]).astimezone()  # gespeichert in UTC, angezeigt in Ortszeit
            print(f"{z['name']}: {zustand}, heute {fragen_heute_person(con, z['name'])} von {z['tageslimit']} Fragen, "
                  f"angelegt am {tag.day}.{tag.month}.{tag.year}")
        return 0

    if not rest:
        print("Bitte einen Namen angeben, zum Beispiel: python zugang.py", befehl, '"Ayse K"')
        return 1
    name = rest[0]

    if befehl == "neu":
        if len(rest) > 2:
            print("Zu viele Angaben. Namen mit Leerzeichen bitte in Anführungszeichen setzen, zum Beispiel \"Ayse K\".")
            return 1
        try:
            limit = int(rest[1]) if len(rest) > 1 else STANDARD_LIMIT
        except ValueError:
            print("Nicht angelegt: Das Tageslimit muss eine ganze Zahl sein, zum Beispiel 10.")
            return 1
        try:
            code = zugang_anlegen(con, name, limit)
        except ValueError as e:
            print("Nicht angelegt:", e)
            return 1
        except sqlite3.IntegrityError:
            print(f"Nicht angelegt: {name} gibt es schon. Für einen neuen Code erst loeschen, dann neu.")
            return 1
        print(f"Zugang für {name} angelegt, Tageslimit {limit}.")
        print(f"Benutzername: {name}")
        print(f"Code:         {code}")
        print("Der Code wird nur jetzt angezeigt und nicht gespeichert. Gib ihn der Person persönlich weiter.")
        return 0

    if befehl == "sperren":
        geaendert = con.execute("UPDATE zugaenge SET aktiv = 0 WHERE name = ?", (name,)).rowcount
    else:
        geaendert = con.execute("DELETE FROM zugaenge WHERE name = ?", (name,)).rowcount
        con.execute("DELETE FROM fragen_pro_person WHERE name = ?", (name,))
    con.commit()
    if not geaendert:
        print(f"Keinen Zugang mit dem Namen {name} gefunden.")
        return 1
    print(f"{name}: {'gesperrt' if befehl == 'sperren' else 'gelöscht'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
