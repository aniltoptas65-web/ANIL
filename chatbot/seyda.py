"""Kern von SeydaAI: Frage verstehen, in den Quellen suchen, Antwort mit Beleg erzeugen."""

import json
import re

import anthropic

from datenbank import abschnitte_nach_nr, abschnitte_von, suchen, verbrauch_buchen

SUCH_MODELL = "claude-haiku-5-5"
ANTWORT_MODELL = "claude-sonnet-5-5"
KANDIDATEN = 30          # so viele Abschnitte holt die Volltextsuche
MAX_JE_SEITE = 3         # damit ein langer Artikel nicht alle Plätze belegt
MAX_AUSWAHL = 6          # so viele wählt Haiku für die Antwort aus
VORSCHAU_ZEICHEN = 700   # so viel Text je Kandidat sieht Haiku beim Auswählen
MAX_VERLAUF = 3          # so viele frühere Fragen und Antworten gehen mit
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
    "werde geschlagen", "wurde geschlagen", "wurde verprügelt", "geschlagen worden", "bedroht mich",
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
10. Halte die Antwort kurz: wenige Absätze, keine Einleitungsfloskeln.
11. Decken die Suchergebnisse nur einen Teil der Frage ab, beantworte diesen Teil und sag kurz, wozu du nichts gefunden hast.
12. Bezieht sich die Frage auf deine vorige Antwort (nicht verstanden, einfacher erklären, mehr Details), erkläre dieselben Inhalte einfacher oder genauer, wieder nur aus den Suchergebnissen. Frühere Antworten im Gespräch sind kein Beleg."""

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
    lang = sprache(frage)
    return {"antwort": KRISE_ANTWORT[lang], "quellen": [], "teile": [], "art": "krise", "sprache": lang}


VERSTEHEN_SYSTEM = """Du bereitest eine Volltextsuche in türkischen islamischen Texten vor (Fetvas und Beschlüsse des Din İşleri Yüksek Kurulu von Diyanet, Artikel der TDV İslâm Ansiklopedisi, Texte von Semerkand). Du bekommst die neue Nachricht und, falls vorhanden, die letzten Fragen und Antworten des Gesprächs.

frage: Die neue Nachricht als vollständige, eigenständige Frage in ihrer Sprache. Bezieht sie sich auf das Gespräch (zum Beispiel "nicht verstanden", "erklär einfacher", "und beim Fasten?", "bu cevap anlaşılmadı"), setze das Thema aus dem Gespräch ein.
rueckfrage: true, wenn die Nachricht sich auf die vorige Antwort bezieht und ohne sie nicht verständlich wäre, sonst false.
sprache: "tr", wenn die neue Nachricht türkisch ist (auch ohne türkische Sonderzeichen geschrieben), sonst "de".
begriffe: 4 bis 10 türkische Suchbegriffe in korrekter türkischer Schreibweise mit ı, ş, ğ, ç, ö, ü, als Wortstamm oder Grundform ohne Endungen. Nimm Fachbegriffe und die Wendungen, unter denen die Quellen das Thema behandeln, auch Synonyme. Die Suche findet alle Wörter, die mit dem Begriff beginnen, darum lieber kurz: "şart" findet auch "şartı" und "şartları". Beispiel für "Was sind die Säulen des Islams?": İslâm şart, beş şart, kelime-i şehâdet, namaz, oruç, zekât, hac. Keine Füllwörter."""

VERSTEHEN_SCHEMA = {
    "type": "object",
    "properties": {
        "frage": {"type": "string"},
        "rueckfrage": {"type": "boolean"},
        "sprache": {"type": "string", "enum": ["de", "tr"]},
        "begriffe": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["frage", "rueckfrage", "sprache", "begriffe"],
    "additionalProperties": False,
}

AUSWAHL_SYSTEM = """Du bekommst eine Frage und nummerierte Textabschnitte aus islamischen Quellen. Wähle die Abschnitte aus, mit denen sich die Frage beantworten lässt, die besten zuerst, höchstens 6.
Wähle einen Abschnitt nur, wenn er die Frage oder einen wesentlichen Teil davon direkt behandelt. Abschnitte, die das Thema nur nebenbei erwähnen, wählst du nicht. Hilft kein Abschnitt, gib eine leere Liste zurück."""

AUSWAHL_SCHEMA = {
    "type": "object",
    "properties": {"nummern": {"type": "array", "items": {"type": "integer"}}},
    "required": ["nummern"],
    "additionalProperties": False,
}


def verlauf_pruefen(roh) -> list[dict]:
    """Nimmt nur gültige, gekürzte Einträge aus dem vom Browser geschickten Verlauf (höchstens MAX_VERLAUF)."""
    if not isinstance(roh, list):
        return []
    sauber = []
    for e in roh[-10:]:
        if not isinstance(e, dict):
            continue
        frage = str(e.get("frage", "")).strip()[:1000]
        antwort = str(e.get("antwort", "")).strip()[:4000]
        urls = e.get("quellen", [])
        urls = [u[:500] for u in urls if isinstance(u, str) and u.startswith("https://")][:6] if isinstance(urls, list) else []
        nummern = e.get("abschnitte", [])
        nummern = [n for n in nummern if isinstance(n, int) and not isinstance(n, bool) and 0 < n < 2**62][:MAX_AUSWAHL] \
            if isinstance(nummern, list) else []
        if frage and antwort:
            sauber.append({"frage": frage, "antwort": antwort, "quellen": urls, "abschnitte": nummern})
    return sauber[-MAX_VERLAUF:]


def _json_aus(antwort):
    if antwort.stop_reason in ("refusal", "max_tokens"):
        return None
    text = "".join(b.text for b in antwort.content if b.type == "text").strip()
    try:
        daten = json.loads(text)
    except json.JSONDecodeError:
        return None
    return daten if isinstance(daten, dict) else None


def verstehen(client: anthropic.Anthropic, con, frage: str, verlauf: list[dict]) -> dict:
    """Haiku macht aus der Nachricht (mit Gesprächsverlauf) eine eigenständige Frage und türkische Suchbegriffe."""
    gespraech = "".join(
        f"Frühere Frage: {e['frage']}\nFrühere Antwort: {e['antwort'][:1500]}\n\n" for e in verlauf
    )
    antwort = client.messages.create(
        model=SUCH_MODELL,
        max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": VERSTEHEN_SCHEMA}},
        system=VERSTEHEN_SYSTEM,
        messages=[{"role": "user", "content": gespraech + "Neue Nachricht: " + frage}],
    )
    verbrauch_buchen(con, SUCH_MODELL, antwort.usage.input_tokens, antwort.usage.output_tokens, "verstehen")
    daten = _json_aus(antwort) or {}
    begriffe = daten.get("begriffe") if isinstance(daten.get("begriffe"), list) else []
    begriffe = [b.strip() for b in begriffe if isinstance(b, str) and b.strip()][:12]
    eigenstaendig = daten.get("frage") if isinstance(daten.get("frage"), str) and daten.get("frage").strip() else frage
    return {
        "frage": eigenstaendig.strip()[:1500],
        # Nur wenn Haiku nichts liefert, dienen die Wörter der Frage selbst als Suchbegriffe
        "begriffe": begriffe or re.findall(r"\w{4,}", frage),
        "rueckfrage": bool(daten.get("rueckfrage")) and bool(verlauf),
        "sprache": daten.get("sprache") if daten.get("sprache") in ("de", "tr") else sprache(frage),
    }


def kandidaten_suchen(con, begriffe: list[str], vorab: list[dict] = ()) -> list[dict]:
    """Bis zu KANDIDATEN Abschnitte: erst die vorab gesetzten (bei Rückfragen), dann die Gesamtsuche,
    dann die besten Treffer je Begriff, damit kein Begriff untergeht."""
    gewaehlt, je_seite = {}, {}

    def dazu(t: dict, frei: bool = False) -> None:
        if t["nr"] in gewaehlt or len(gewaehlt) >= KANDIDATEN:
            return
        if not frei and je_seite.get(t["url"], 0) >= MAX_JE_SEITE:
            return
        gewaehlt[t["nr"]] = t
        je_seite[t["url"]] = je_seite.get(t["url"], 0) + 1

    for t in vorab:
        dazu(t, frei=True)
    for t in suchen(con, begriffe, anzahl=40):
        if len(gewaehlt) >= KANDIDATEN - 2 * min(len(begriffe), 6):
            break
        dazu(t)
    for b in begriffe:
        for t in suchen(con, [b], anzahl=4):
            dazu(t)
    return list(gewaehlt.values())


def auswaehlen(client: anthropic.Anthropic, con, frage: str, kandidaten: list[dict]) -> list[dict]:
    """Haiku liest kurze Vorschauen aller Kandidaten und wählt die passenden aus."""
    liste = "\n\n".join(
        f"[{i}] {t['quelle']}: {t['titel']}\n{t['text'][:VORSCHAU_ZEICHEN]}" for i, t in enumerate(kandidaten)
    )
    antwort = client.messages.create(
        model=SUCH_MODELL,
        max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": AUSWAHL_SCHEMA}},
        system=AUSWAHL_SYSTEM,
        messages=[{"role": "user", "content": f"Frage: {frage}\n\nAbschnitte:\n\n{liste}"}],
    )
    verbrauch_buchen(con, SUCH_MODELL, antwort.usage.input_tokens, antwort.usage.output_tokens, "auswaehlen")
    daten = _json_aus(antwort)
    if daten is None:
        # Auswahl gescheitert: dann die ersten Treffer der Volltextsuche nehmen
        return kandidaten[:MAX_AUSWAHL]
    nummern = []
    for n in daten.get("nummern") if isinstance(daten.get("nummern"), list) else []:
        if isinstance(n, int) and not isinstance(n, bool) and 0 <= n < len(kandidaten) and n not in nummern:
            nummern.append(n)
    return [kandidaten[n] for n in nummern[:MAX_AUSWAHL]]


def antworten(client: anthropic.Anthropic, con, frage: str, verlauf: list[dict] = None) -> dict:
    """Ergebnis: {"antwort", "quellen": [{"titel","url","quelle"}], "teile": [{"text","belege":[Index in quellen]}], "art", "sprache"}.

    art ist "antwort", "kein_treffer", "krise" oder "abgelehnt". verlauf kommt aus verlauf_pruefen().
    """
    if ist_krise(frage):
        return krisen_antwort(frage)
    verlauf = verlauf or []

    verstanden = verstehen(client, con, frage, verlauf)
    lang = verstanden["sprache"]
    leer = {"antwort": KEIN_TREFFER[lang], "quellen": [], "teile": [], "art": "kein_treffer", "sprache": lang}

    # Bei einer Rückfrage gehören die zitierten Abschnitte der vorigen Antwort zu den Kandidaten
    # (fehlen deren Nummern, die ersten Abschnitte jeder ihrer Quellen)
    vorab = []
    if verstanden["rueckfrage"]:
        vorher = verlauf[-1]
        vorab = abschnitte_nach_nr(con, vorher["abschnitte"]) or abschnitte_von(con, vorher["quellen"])
    kandidaten = kandidaten_suchen(con, verstanden["begriffe"], vorab)
    if not kandidaten:
        return leer
    treffer = auswaehlen(client, con, verstanden["frage"], kandidaten)
    if not treffer:
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

    # Frühere Fragen und Antworten als normales Gespräch, die Suchergebnisse nur in der neuen Frage
    nachrichten = []
    for e in verlauf:
        nachrichten.append({"role": "user", "content": e["frage"]})
        nachrichten.append({"role": "assistant", "content": e["antwort"]})
    frage_text = "Frage: " + frage
    if verstanden["frage"] != frage:
        frage_text += "\n(Gemeint ist: " + verstanden["frage"] + ")"
    nachrichten.append({"role": "user", "content": ergebnisse + [{"type": "text", "text": frage_text}]})

    nachricht = client.beta.messages.create(
        model=ANTWORT_MODELL,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        messages=nachrichten,
    )
    verbrauch_buchen(con, nachricht.model or ANTWORT_MODELL, nachricht.usage.input_tokens, nachricht.usage.output_tokens, "antworten")

    if nachricht.stop_reason == "refusal":
        return {**leer, "art": "abgelehnt"}

    quellen, index_von_url, teile, ausgeblendet, zitiert = [], {}, [], False, []
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
            if t["nr"] not in zitiert:
                zitiert.append(t["nr"])
            if t["url"] not in index_von_url:
                index_von_url[t["url"]] = len(quellen)
                quellen.append({"titel": t["titel"] or t["url"], "url": t["url"], "quelle": t["quelle"]})
            if index_von_url[t["url"]] not in belege:
                belege.append(index_von_url[t["url"]])
        if belege:
            teile.append({"text": block.text, "belege": belege})
            vorher_belegt = True
        elif ist_uebersetzung(block.text) and vorher_belegt:
            # Gekennzeichnete Übersetzung des unmittelbar davor belegten Zitats, nur ihre eigene Zeile
            vorne = block.text[: len(block.text) - len(block.text.lstrip())]
            zeile, _, rest = block.text.lstrip().partition("\n")
            teile.append({"text": vorne + zeile + "\n", "belege": []})
            if rest.strip():
                ausgeblendet = True
                vorher_belegt = False
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
    return {"antwort": antwort_text, "quellen": quellen, "teile": teile, "hinweise": hinweise, "art": "antwort",
            "sprache": lang, "abschnitte": zitiert}
