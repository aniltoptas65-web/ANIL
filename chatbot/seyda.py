"""Kern von SeydaAI: Frage verstehen, in den Quellen suchen, Antwort mit Beleg erzeugen."""

import json
import re

import anthropic

from datenbank import suchen, verbrauch_buchen

SUCH_MODELL = "claude-haiku-5-5"
ANTWORT_MODELL = "claude-sonnet-5-5"
MIN_TREFFER = 1
# Unbelegte Textstücke bleiben nur stehen, wenn sie keine Aussage sein können (höchstens so viele Wörter, kein Satzende)
MAX_WOERTER_OHNE_BELEG = 2

KEIN_TREFFER = {
    "de": "Dazu habe ich in den Quellen nichts gefunden. Bitte frag den Imam deiner Moschee oder die Fetva Stelle von Diyanet.",
    "tr": "Bu konuda kaynaklarda bir şey bulamadım. Lütfen camiinizin imamına veya Diyanet'in fetva hattına danışın.",
}

# Bei diesen Wortanfängen antwortet der Bot ohne Sprachmodell sofort mit Hilfsnummern.
# Verglichen wird nach normalisieren(), also klein, ohne türkischen Punkt über dem i, ı als i.
KRISE_WOERTER = [
    "suizid", "selbstmord", "umbringen", "bringe mich um", "bring mich um", "nicht mehr leben",
    "will sterben", "sterben will", "möchte sterben", "tot sein", "mich töten",
    "ritze mich", "mich ritzen", "mich verletzen", "selbstverletz",
    "gewalt", "vergewalt", "missbraucht", "sexuell belästigt", "schlägt mich", "schlaegt mich", "schlägt uns", "schlägt meine", "hat mich geschlagen",
    "werde geschlagen", "geschlagen worden", "bedroht mich",
    "intihar", "kendimi öldür", "kendimi as", "ölmek istiyorum", "ölmek ister", "yaşamak istemiyorum", "canıma kıy",
    "kendime zarar", "şiddet", "dövüyor", "beni dövü", "taciz", "tecavüz", "istismar",
]

# Nummern am 9. November 2026 auf telefonseelsorge.de, nummergegenkummer.de und hilfetelefon.de nachgelesen.
KRISE_ANTWORT = {
    "de": (
        "Es tut mir leid, dass es dir gerade so geht. Bitte sprich sofort mit einem Menschen, der helfen kann:\n"
        "Notruf: 112\n"
        "TelefonSeelsorge: 0800 111 0 111, 0800 111 0 222 oder 116 123\n"
        "Nummer gegen Kummer für Kinder und Jugendliche: 116 111\n"
        "Hilfetelefon Gewalt gegen Frauen: 116 016\n"
        "Zu dieser Frage gebe ich keine religiöse Antwort. Du bist nicht allein."
    ),
    "tr": (
        "Bunu yaşadığın için çok üzgünüm. Lütfen hemen yardım edebilecek biriyle konuş:\n"
        "Acil çağrı: 112\n"
        "TelefonSeelsorge: 0800 111 0 111, 0800 111 0 222 veya 116 123\n"
        "Çocuklar ve gençler için Nummer gegen Kummer: 116 111\n"
        "Kadına yönelik şiddet yardım hattı (Hilfetelefon Gewalt gegen Frauen): 116 016\n"
        "Bu soruya dini bir cevap vermiyorum. Yalnız değilsin."
    ),
}

SYSTEM = """Du bist SeydaAI, ein Suchassistent des Vereins Reyhani Europa e.V. Du gibst wieder, was die mitgeschickten Quellen sagen. Du bist kein Lehrer, kein Hoca und kein Scheich und stellst dich nie so vor.

Regeln:
1. Antworte ausschließlich aus den mitgeschickten Suchergebnissen. Nutze kein eigenes Wissen, auch wenn du es für richtig hältst. Jede inhaltliche Aussage muss sich auf ein Suchergebnis stützen.
2. Beantworten die Suchergebnisse die Frage nicht, sag genau das: dass du dazu in den Quellen nichts gefunden hast, und verweise auf den Imam vor Ort oder die Fetva Stelle von Diyanet. Rate nicht.
3. Erteile keine Fetva. Bei persönlichen Einzelfällen (Scheidung, Erbe, Ehe, Krankheit, Schulden) gib wieder, was die Quelle allgemein sagt, und verweise für den eigenen Fall an den Imam oder die Fetva Stelle.
4. Standard ist die hanafitische Schule. Wenn Quellen sich widersprechen, nenne beide Positionen mit ihrer Quelle und entscheide nicht.
5. Behandle Semerkand und Serhendi gleich. Nimm keine Stellung zu Konflikten zwischen Gemeinschaften oder Personen.
6. Formuliere in eigenen Worten. Zitiere höchstens einen kurzen Satz wörtlich, im türkischen Original, und schreib darunter "Maschinelle Übersetzung:" mit der deutschen Übersetzung, wenn du auf Deutsch antwortest.
7. Aus Suchergebnissen, deren Titel mit [NUR ZUSAMMENFASSEN] beginnt, zitierst du nie wörtlich, sondern fasst nur zusammen.
8. Antworte in der Sprache der Frage (Deutsch oder Türkisch). Fachbegriffe wie mekruh, tahrîmen mekruh oder müfsid lässt du stehen und erklärst sie kurz, statt sie zu übersetzen. Übersetze mekruh nie mit "verboten".
9. Wirke nicht wie ein offizieller Dienst von Diyanet, TDV, Semerkand oder Serhendi.
10. Halte die Antwort kurz: wenige Absätze, keine Einleitungsfloskeln."""

HINWEIS_AUSGEBLENDET = {
    "de": "Hinweis: Teile der Antwort hatten keinen Beleg in den Quellen und wurden ausgeblendet.",
    "tr": "Not: Cevabın kaynakta dayanağı olmayan kısımları gizlendi.",
}
HINWEIS_ABGESCHNITTEN = {
    "de": "Hinweis: Die Antwort wurde abgeschnitten.",
    "tr": "Not: Cevap yarıda kesildi.",
}


VERWEIS = {
    "de": "Für deinen eigenen Fall frag bitte den Imam deiner Moschee oder die Fetva Stelle von Diyanet.",
    "tr": "Kendi durumun için lütfen camiinin imamına veya Diyanet'in fetva hattına danış.",
}


def ist_uebersetzung(text: str) -> bool:
    t = text.strip().lower()
    return t.startswith("maschinelle übersetzung") or t.startswith("makine çevirisi")


def ist_ueberleitung(text: str) -> bool:
    """Leerraum oder kurze Überleitung ohne Satzende, also keine eigene Aussage."""
    t = text.strip()
    if not t:
        return True
    return len(t.split()) <= MAX_WOERTER_OHNE_BELEG and not re.search(r"[.!?]", t)


def normalisieren(text: str) -> str:
    """Kleinschreibung, die auch türkisches İ und I richtig behandelt."""
    return text.lower().replace("̇", "").replace("ı", "i")


_KRISE_MUSTER = [re.compile(r"\b" + re.escape(normalisieren(w))) for w in KRISE_WOERTER]


def ist_krise(frage: str) -> bool:
    f = normalisieren(frage)
    return any(m.search(f) for m in _KRISE_MUSTER)


_DE = re.compile(r"\b(der|die|das|den|dem|ist|sind|was|wie|warum|wann|ich|du|und|oder|darf|dürfen|macht|kann|muss|soll|ein|eine|mein|meine|bei|beim|nach|wenn|für)\b")
_TR = re.compile(r"\b(ne|neden|nasıl|nedir|niçin|mi|mı|mu|mü|midir|mıdır|mudur|müdür|ve|ile|bir|bu|şu|ben|sen|için|olur|olmaz|gerekir|var|yok|kime|kimler|hangi|kaç|nerede|niye|nelerdir|verilir|yapılır|edilir|caiz mi)\b")


def sprache(frage: str) -> str:
    klein = frage.lower()
    de = len(_DE.findall(klein))
    tr = len(_TR.findall(klein)) + len(re.findall(r"[şğıİ]", frage))
    return "tr" if tr > de else "de"


def krisen_antwort(frage: str) -> dict:
    return {"antwort": KRISE_ANTWORT[sprache(frage)], "quellen": [], "teile": [], "art": "krise"}


def suchbegriffe(client: anthropic.Anthropic, con, frage: str) -> list[str]:
    """Haiku macht aus der Frage türkische Suchbegriffe für die Volltextsuche."""
    antwort = client.messages.create(
        model=SUCH_MODELL,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=(
            "Du bekommst eine Frage zu einem islamischen Thema auf Deutsch oder Türkisch. "
            "Gib 3 bis 8 türkische Suchbegriffe zurück, mit denen man passende Abschnitte in türkischen Texten "
            "von Diyanet, TDV und Semerkand findet (Fachbegriffe in türkischer Schreibweise, Grundformen). "
            "Antworte nur mit einer JSON Liste von Strings, ohne weiteren Text."
        ),
        messages=[{"role": "user", "content": frage}],
    )
    verbrauch_buchen(con, SUCH_MODELL, antwort.usage.input_tokens, antwort.usage.output_tokens)
    begriffe = []
    if antwort.stop_reason != "refusal":
        text = "".join(b.text for b in antwort.content if b.type == "text").strip()
        treffer = re.search(r"\[.*\]", text, re.DOTALL)
        try:
            begriffe = json.loads(treffer.group(0)) if treffer else []
        except json.JSONDecodeError:
            begriffe = []
    begriffe = [b for b in begriffe if isinstance(b, str) and b.strip()]
    # Nur wenn Haiku nichts liefert, dienen die Wörter der Frage selbst als Suchbegriffe
    return begriffe or re.findall(r"\w{4,}", frage)


def antworten(client: anthropic.Anthropic, con, frage: str) -> dict:
    """Ergebnis: {"antwort", "quellen": [{"titel","url","quelle"}], "teile": [{"text","belege":[Index in quellen]}], "art"}.

    art ist "antwort", "kein_treffer", "krise" oder "abgelehnt".
    """
    lang = sprache(frage)
    if ist_krise(frage):
        return krisen_antwort(frage)

    begriffe = suchbegriffe(client, con, frage)
    treffer = suchen(con, begriffe, anzahl=6)
    leer = {"antwort": KEIN_TREFFER[lang], "quellen": [], "teile": [], "art": "kein_treffer"}
    if len(treffer) < MIN_TREFFER:
        return leer

    ergebnisse = []
    for t in treffer:
        titel = f"{t['quelle']}: {t['titel']}"
        if t["nur_zusammenfassen"]:
            titel = "[NUR ZUSAMMENFASSEN] " + titel
        ergebnisse.append({
            "type": "search_result",
            "source": t["url"],
            "title": titel,
            "content": [{"type": "text", "text": t["text"]}],
            "citations": {"enabled": True},
        })

    nachricht = client.beta.messages.create(
        model=ANTWORT_MODELL,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        messages=[{"role": "user", "content": ergebnisse + [{"type": "text", "text": "Frage: " + frage}]}],
    )
    verbrauch_buchen(con, nachricht.model or ANTWORT_MODELL, nachricht.usage.input_tokens, nachricht.usage.output_tokens)

    if nachricht.stop_reason == "refusal":
        return {**leer, "art": "abgelehnt"}

    quellen, index_von_url, teile, ausgeblendet = [], {}, [], False
    vorher_belegt = False
    for block in nachricht.content:
        if block.type != "text":
            continue
        belege = []
        for c in (block.citations or []):
            if getattr(c, "type", "") != "search_result_location":
                continue
            if not 0 <= c.search_result_index < len(treffer):
                continue
            t = treffer[c.search_result_index]
            if t["url"] not in index_von_url:
                index_von_url[t["url"]] = len(quellen)
                quellen.append({"titel": t["titel"] or t["url"], "url": t["url"], "quelle": t["quelle"]})
            if index_von_url[t["url"]] not in belege:
                belege.append(index_von_url[t["url"]])
        if belege:
            teile.append({"text": block.text, "belege": belege})
            vorher_belegt = True
        elif ist_uebersetzung(block.text) and vorher_belegt:
            # Gekennzeichnete Übersetzung des unmittelbar davor belegten Zitats
            teile.append({"text": block.text, "belege": []})
        elif ist_ueberleitung(block.text):
            teile.append({"text": block.text, "belege": []})
        else:
            ausgeblendet = True
            vorher_belegt = False
            # Lücke markieren, damit die übrigen Teile nicht aneinanderkleben
            if teile and not teile[-1]["text"].endswith((" ", "\n")):
                teile.append({"text": " ", "belege": []})

    # Ohne einen einzigen Beleg zeigen wir keine Antwort (Regel: nur aus Quellen)
    if not quellen:
        return leer

    antwort_text = "".join(t["text"] for t in teile).strip()
    hinweise = []
    if ausgeblendet:
        hinweise.append(HINWEIS_AUSGEBLENDET[lang])
    if nachricht.stop_reason == "max_tokens":
        hinweise.append(HINWEIS_ABGESCHNITTEN[lang])
    # Der Verweis an Imam oder Fetva Stelle hängt immer an, unabhängig vom Modell
    antwort_text += "\n\n" + VERWEIS[lang]
    if hinweise:
        antwort_text += "\n\n" + "\n".join(hinweise)
    return {"antwort": antwort_text, "quellen": quellen, "teile": teile, "hinweise": hinweise, "art": "antwort"}
