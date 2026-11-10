"""Hilfsprogramm für test/vergleich.test.js: führt seyda.antworten (Python Fassung) mit nachgebildeten
Antworten der Sprachmodelle aus. Eingabe und Ausgabe als JSON über stdin und stdout."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import seyda  # noqa: E402
from datenbank import verbinden  # noqa: E402


def objekt(wert):
    if isinstance(wert, dict):
        return SimpleNamespace(**{k: objekt(v) for k, v in wert.items()})
    if isinstance(wert, list):
        return [objekt(v) for v in wert]
    return wert


class Nachbildung:
    def __init__(self, fall, anfragen):
        self.fall, self.anfragen = fall, anfragen
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._beta))

    def _antwort(self, roh):
        roh = dict(roh)
        roh.setdefault("usage", {"input_tokens": 10, "output_tokens": 5})
        roh.setdefault("model", None)
        roh.setdefault("stop_reason", "end_turn")
        roh["content"] = [{"citations": None, **b} for b in roh.get("content", [])]
        for b in roh["content"]:
            if b["citations"] is not None:
                b["citations"] = [{"type": "search_result_location", **c} for c in b["citations"]]
        return objekt(roh)

    def _create(self, **kw):
        self.anfragen.append(kw)
        schritt = "verstehen" if kw["system"].startswith("Du bereitest") else "auswahl"
        return self._antwort(self.fall[schritt])

    def _beta(self, **kw):
        self.anfragen.append(kw)
        return self._antwort(self.fall["sonnet"])


def main():
    faelle = json.load(sys.stdin)
    aus = []
    for fall in faelle:
        con = verbinden(fall["db"])
        anfragen = []
        try:
            ergebnis = seyda.antworten(Nachbildung(fall, anfragen), con, fall["frage"], seyda.verlauf_pruefen(fall.get("verlauf")))
        except Exception as e:  # noqa: BLE001
            ergebnis = {"fehler": type(e).__name__}
        aus.append({"ergebnis": ergebnis, "anfragen": anfragen})
        con.close()
    json.dump(aus, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
