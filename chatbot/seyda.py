"""Kern von SeydaAI: Frage verstehen, in den Quellen suchen, Antwort mit Beleg erzeugen."""

import json
import re
import unicodedata

import anthropic

from datenbank import abschnitt_danach, abschnitte_nach_nr, abschnitte_von, suchen, verbrauch_buchen

SUCH_MODELL = "claude-haiku-5-5"
ANTWORT_MODELL = "claude-sonnet-5-5"
KANDIDATEN = 30          # so viele Abschnitte holt die Volltextsuche
MAX_JE_SEITE = 3         # damit ein langer Artikel nicht alle Plätze belegt
MAX_AUSWAHL = 8          # so viele wählt Haiku für die Antwort aus
MIT_FOLGEABSCHNITT = 3   # bei den besten so vielen kommt der nächste Abschnitt derselben Seite dazu (Listen reißen oft ab)
MAX_ABSCHNITTE = 10      # so viele Abschnitte bekommt Sonnet höchstens
VORSCHAU_ZEICHEN = 700   # so viel Text je Kandidat sieht Haiku beim Auswählen
MAX_VERLAUF = 3          # so viele frühere Fragen und Antworten gehen mit
# Gründlichkeit beim Antworten. "medium" denkt vor der Antwort kurz nach und verbindet mehrere Abschnitte besser,
# kostet aber etwas mehr und dauert ein paar Sekunden länger. "low" ist billiger und schneller.
ANTWORT_GRUENDLICHKEIT = "medium"
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
5. Nimm keine Stellung zu Konflikten zwischen Gemeinschaften, Richtungen oder Personen.
6. Formuliere in eigenen Worten. Zitiere höchstens einen kurzen Satz wörtlich, im türkischen Original in einer eigenen Zeile, und schreib in die nächste Zeile "Maschinelle Übersetzung:" mit der deutschen Übersetzung, wenn du auf Deutsch antwortest.
7. Aus Suchergebnissen, deren Titel mit [NUR ZUSAMMENFASSEN] beginnt, zitierst du nie wörtlich, sondern fasst nur zusammen.
8. Antworte in der Sprache der Frage (Deutsch oder Türkisch). Fachbegriffe wie mekruh, tahrîmen mekruh oder müfsid lässt du stehen und erklärst sie beim ersten Vorkommen kurz, statt sie zu übersetzen. Übersetze mekruh nie mit "verboten".
9. Wirke nicht wie ein offizieller Dienst von Diyanet oder TDV.
10. Nutze alles, was die Suchergebnisse zur Frage hergeben: vollständige Aufzählungen, Bedingungen, Ausnahmen, Begründungen und Belege aus Koran und Hadith, wenn die Quelle sie nennt. Lass nichts Wichtiges weg, aber schreib nichts, was nicht in den Suchergebnissen steht.
11. Decken die Suchergebnisse nur einen Teil der Frage ab, beantworte diesen Teil und sag kurz, wozu du nichts gefunden hast.
12. Bezieht sich die Frage auf deine vorige Antwort (nicht verstanden, einfacher erklären, mehr Details), erkläre dieselben Inhalte einfacher oder genauer, wieder nur aus den Suchergebnissen. Frühere Antworten im Gespräch sind kein Beleg.
13. Ist die Frage unklar oder umgangssprachlich, beantworte die wahrscheinlichste Lesart.

So baust du die Antwort auf, damit sie übersichtlich ist:
- Beginne mit ein oder zwei Sätzen, die die Frage direkt beantworten. Keine Einleitung, keine Wiederholung der Frage.
- Danach die Einzelheiten. Aufzählungen (zum Beispiel die Säulen des Islams oder die Farz des Gebets) schreibst du als nummerierte Liste: jeder Punkt in einer eigenen Zeile, beginnend mit "1. ", "2. " usw., dann der Begriff in **fett**, ein Doppelpunkt und eine kurze Erklärung. In einer Klammer hinter dem Begriff steht höchstens seine deutsche Übersetzung. Ein Urteil (zum Beispiel haram, caiz, farz, erlaubt, verboten) steht nie im Stichwort, sondern im belegten Satz dahinter. Ist der Begriff selbst ein Urteilswort (etwa tahrîmen mekruh, sünnet, farz-ı kifâye) oder fasst eine Zwischenzeile Punkte nach ihrem Urteil zusammen (etwa was Kaza und Keffaret erfordert), schreib das als ganzen Satz mit Beleg, nicht als Stichwort. Für Punkte ohne Reihenfolge nimmst du eine Liste mit "- ".
- Bedingungen, Ausnahmen und abweichende Meinungen kommen danach in einen eigenen kurzen Absatz.
- Kurze Absätze mit höchstens drei Sätzen, dazwischen eine Leerzeile. Keine Überschriften mit #, keine Tabellen, keine Emojis.
- Einfache, klare Sätze, die auch Jugendliche verstehen. Eine Aussage pro Satz. Keine Gedankenstriche; verbinde mit Punkt, Komma oder Doppelpunkt.
- So lang wie nötig, meist 100 bis 300 Wörter. Keine Schlussformel: Den Hinweis auf den Imam hängt das Programm selbst an."""

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


def _falten(text: str) -> str:
    """Für Wortvergleiche: klein, ohne Akzente und Sonderzeichen (â wird a, ş wird s, ü wird u, ı und İ werden i)."""
    t = unicodedata.normalize("NFKD", text.replace("ı", "i").replace("İ", "I"))
    return "".join(z for z in t if not unicodedata.combining(z)).lower()


def _woerter(text: str) -> list[str]:
    # Apostrophe verbinden, damit "bid'at" ein Wort bleibt und "İslâm'ın" als "islamin" zählt
    return re.findall(r"\w+", re.sub(r"['’`]", "", _falten(text)))


# Wörter, die ein Urteil oder eine Aussage tragen. Steht eines davon in einem Textstück ohne Beleg, ist es keine
# bloße Gliederung und wird ausgeblendet (lieber ein Stichwort zu viel weg als ein unbelegtes Urteil sichtbar).
# Alle Listen sind gefaltet (ohne Akzente, ı und İ als i), damit Schreibweisen wie "Sünnet" und "sunnet" gleich zählen.
_URTEILSWOERTER = {_falten(w) for w in (
    "ist", "sind", "war", "wird", "werden", "macht", "machen", "muss", "müssen", "darf", "dürfen", "kann", "können",
    "soll", "sollen", "gilt", "gelten", "nicht", "nie", "niemals", "ja", "nein", "genau", "stimmt", "natürlich",
    "selbstverständlich", "sicher", "klar", "durchaus", "absolut", "ok", "okay", "tabu",
    "musst", "müsste", "müssten", "kannst", "könnte", "könnten", "darfst", "dürfte", "dürften", "sollst", "sollte",
    "sollten", "solltest", "besser", "gewiss", "sicherlich", "eindeutig", "definitiv", "bestimmt", "ordnung",
    "var", "yok", "olur", "evet", "hayır", "tabii", "elbette", "kesinlikle", "aynen", "evla", "evladır", "doğrudur",
    "möglich", "unmöglich", "nachholen", "nachzuholen", "nachgeholt", "unrein",
    "muhakkak", "edilir", "yapılır", "kılınır", "olunur", "tutulur", "verilir", "sayılır",
)}
# Wortanfänge mit Urteil, auch gebeugt: haramdır, caizdir, Sünde, bozmaz, kabul edilmez
_URTEILSANFAENGE = tuple(_falten(w) for w in (
    "kein", "sünd", "gebot", "brech", "bricht", "gebroch", "statthaft", "strafbar", "legitim", "ratsam", "gültig",
    "ungültig", "nötig", "unnötig", "gestatt", "abzurat", "abgerat", "lobenswert", "tadel", "verdienstvoll",
    "zweifelhaft", "unzweifelhaft", "zweifellos", "şüpheli", "şüphesiz",
    "sunna", "şirk", "küfr", "küfür", "batıl", "yanlış", "gerek", "lazım", "değil", "boz", "olmaz", "olmama",
    "kabul", "makbul", "efdal", "tavsiye", "zarar", "kaçın", "sakın", "terk", "mümkün", "muteber", "geçer",
))
# Wortteile mit Urteil, auch mitten im Wort: unzulässig, unerlaubt, unproblematisch, Rauchverbot, untersagt
_URTEILSTEILE = tuple(_falten(w) for w in (
    "erlaub", "verbot", "verbiet", "untersag", "zuläss", "pflicht", "empfehl", "empfohl", "verwerf",
    "verpön", "erwünscht", "notwendig", "obligat", "bedenk", "problem", "richtig", "falsch",
    "korrekt", "schäd", "schad", "geduldet", "toleriert", "ablehn", "abzulehn", "abgelehnt", "akzeptab", "akzeptiert",
    "harmlos", "unterlass", "meid", "vorzuzieh", "wirksam", "verwehr",
    "haram", "helal", "halal", "caiz", "mekruh", "makruh", "mubah", "günah", "yasak", "farz", "fard", "vacip", "vacib",
    "wajib", "sünnet", "müstehap", "müstehab", "mustahab", "mendup", "mendub", "bidat", "sahih", "fasit", "fasid",
    "geçersiz", "geçerli", "zorunlu", "mecburi", "serbest", "sakınca", "uygun", "sevap", "sevab", "nafile",
    "keffaret", "kefaret",
))
# Übliche Übersetzungen und Sachwörter, die nur zufällig einen Wortteil oben enthalten
_KEIN_URTEIL = {_falten(w) for w in (
    "Pflichtabgabe", "Pflichtabgaben", "Pflichtgebet", "Pflichtgebete", "Pflichtgebets", "Pflichtalmosen", "Pflichten",
    "Pflichtteil", "Pflichtteile", "Grundpflicht", "Grundpflichten", "namaz", "temeli", "kemali", "cemali", "ameli",
)}
_KEIN_URTEIL_ANFANG = tuple(_falten(w) for w in ("Unreinheit", "Gültigkeit", "Gerekçe"))
# Türkische Passivformen sind in einer Frageüberschrift wie "Zekât kimlere verilir" kein Urteil
_PASSIV = {_falten(w) for w in ("edilir", "yapılır", "kılınır", "olunur", "tutulur", "verilir", "sayılır")}
_FRAGEWOERTER = {_falten(w) for w in ("nasıl", "kime", "kimlere", "kimler", "neler", "nelerdir", "ne", "nerede", "ne zaman",
                                     "hangi", "niçin", "neden", "wie", "wem", "wann", "wo", "warum", "wozu")}


def _ist_urteilswort(w: str) -> bool:
    if w in _KEIN_URTEIL or w.startswith(_KEIN_URTEIL_ANFANG):
        return False
    if w in _URTEILSWOERTER or w.startswith(_URTEILSANFAENGE) or any(t in w for t in _URTEILSTEILE):
        return True
    # Türkische Endungen mit Urteil: olmaz, edilmez (Verneinung, aber nicht namaz), kılınmalı, içilmemeli (Pflicht),
    # okuyabilir (Erlaubnis)
    return len(w) > 4 and w.endswith(("maz", "mez", "mali", "meli", "malidir", "melidir", "abilir", "ebilir",
                                      "abilirsin", "ebilirsin", "abilirler", "ebilirler"))


def _hat_urteil(text: str) -> bool:
    woerter = _woerter(text)
    frage = any(w in _FRAGEWOERTER for w in woerter)
    for i, w in enumerate(woerter):
        if frage and w in _PASSIV:
            continue
        if w == "besser" and woerter[i + 1:i + 2] == ["gesagt"]:
            continue
        if _ist_urteilswort(w):
            return True
    return False


def ist_ueberleitung(text: str) -> bool:
    """Leerraum oder kurze Überleitung ohne Satzende und ohne Urteilswort, also keine eigene Aussage."""
    t = text.strip()
    if not t:
        return True
    return len(t.split()) <= MAX_WOERTER_OHNE_BELEG and not re.search(r"[.!?]", t) and not _hat_urteil(t)


_LISTENZEICHEN = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+")
# Stichwort einer Liste: "**Namaz** (Gebet):" oder "**Kurz gesagt:**" oder "Bedingungen:", immer mit Doppelpunkt am Ende
_STICHWORT_FETT = re.compile(r"^\*\*([^*]+?):?\*\*\s*(?:\(([^()]*)\))?\s*:?$")
_STICHWORT = re.compile(r"^([^*():]+?)\s*(?:\(([^()]*)\))?\s*:$")


def ist_gliederung(text: str) -> bool:
    """Reine Gliederung ohne eigene Aussage: Leerraum, Satzzeichen, Listennummern und Stichwörter mit Doppelpunkt
    wie "2. **Namaz** (Gebet): ". Ein fettes Stichwort hat höchstens 5 Wörter, ein normales höchstens 2, die Klammer
    höchstens 4. Kein Satzende, kein Urteilswort. Alles andere ohne Beleg wird ausgeblendet."""
    for zeile in text.split("\n"):
        rest = _LISTENZEICHEN.sub("", zeile).strip()
        if not re.search(r"\w", rest):
            continue  # nur Leerraum, Satzzeichen oder Listenzeichen
        if not rest.endswith(":") and not rest.endswith(":**"):
            return False
        m = _STICHWORT_FETT.match(rest)
        grenze = 5
        if not m:
            m = _STICHWORT.match(rest)
            grenze = 2
        if not m:
            return False
        wort, klammer = m.group(1), m.group(2) or ""
        if len(wort.split()) > grenze or len(klammer.split()) > 4:
            return False
        if re.search(r"[.!?]", wort + klammer) or _hat_urteil(wort + " " + klammer):
            return False
    return True


def geruest(text: str) -> str:
    """Was von einem ausgeblendeten Stück stehen bleibt: seine Zeilenumbrüche, Zeilen, die reine Gliederung sind, und
    das Listenzeichen seiner letzten Zeile. So bleibt der belegte Rest dieser Zeile ein Listenpunkt und die Gliederung
    fällt nicht zusammen. Zeilen mit eigener Aussage fallen ganz weg."""
    zeilen = text.split("\n")
    aus = []
    for i, zeile in enumerate(zeilen):
        if re.search(r"\w", zeile) and ist_gliederung(zeile):
            aus.append(zeile)
        elif i == len(zeilen) - 1 and _LISTENZEICHEN.match(zeile):
            aus.append(_LISTENZEICHEN.match(zeile).group(0))
        else:
            aus.append("")
    return "\n".join(aus)


_LEERER_PUNKT = re.compile(r"(?:^|(?<=\n))[ \t]*(?:\d{1,2}[.)]|[-*•])[ \t]+$")


def leere_punkte_entfernen(teile: list[dict]) -> None:
    """Ein Listenzeichen ohne belegten Text dahinter in derselben Zeile wäre ein leerer Punkt; es fällt weg."""
    for i, t in enumerate(teile):
        if t["belege"] or not _LEERER_PUNKT.search(t["text"]):
            continue
        folgt = teile[i + 1]["text"] if i + 1 < len(teile) else ""
        if not folgt.strip() or folgt.lstrip(" \t").startswith("\n"):
            t["text"] = _LEERER_PUNKT.sub("", t["text"])


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


VERSTEHEN_SYSTEM = """Du bereitest eine Volltextsuche in türkischen islamischen Texten vor (Fetvas und Beschlüsse des Din İşleri Yüksek Kurulu von Diyanet, Artikel der TDV İslâm Ansiklopedisi). Du bekommst die neue Nachricht und, falls vorhanden, die letzten Fragen und Antworten des Gesprächs.

frage: Die neue Nachricht als vollständige, eigenständige Frage in ihrer Sprache. Bezieht sie sich auf das Gespräch (zum Beispiel "nicht verstanden", "erklär einfacher", "und beim Fasten?", "bu cevap anlaşılmadı"), setze das Thema aus dem Gespräch ein.
rueckfrage: true, wenn die Nachricht sich auf die vorige Antwort bezieht und ohne sie nicht verständlich wäre, sonst false.
sprache: "tr", wenn die neue Nachricht türkisch ist (auch ohne türkische Sonderzeichen geschrieben), sonst "de".
Die Nachricht kann Tippfehler, Umgangssprache, fehlende Sonderzeichen oder gemischtes Deutsch und Türkisch enthalten. Erkenne, was gemeint ist, und arbeite damit.
begriffe: 4 bis 10 türkische Suchbegriffe in korrekter türkischer Schreibweise mit ı, ş, ğ, ç, ö, ü, als Wortstamm oder Grundform ohne Endungen. Nimm Fachbegriffe und die Wendungen, unter denen die Quellen das Thema behandeln, auch Synonyme. Die Suche findet alle Wörter, die mit dem Begriff beginnen, darum lieber kurz: "şart" findet auch "şartı" und "şartları". Beispiel für "Was sind die Säulen des Islams?": İslâm şart, beş şart, kelime-i şehâdet, namaz, oruç, zekât, hac. Deutsche Begriffe übersetzt du in die türkischen Fachwörter, zum Beispiel Gebet = namaz, Gebetswaschung = abdest, Ganzkörperwaschung = gusül, Fasten = oruç, Pilgerfahrt = hac, Opfer = kurban, Glaubensgrundsätze = iman esasları, Bittgebet = dua, Gottesgedenken = zikir, Sufismus = tasavvuf. Keine Füllwörter."""

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

AUSWAHL_SYSTEM = """Du bekommst eine Frage und nummerierte Textabschnitte aus islamischen Quellen. Wähle die Abschnitte aus, mit denen sich die Frage gründlich beantworten lässt, die besten zuerst, höchstens 8.
Wähle einen Abschnitt, wenn er die Frage oder einen wesentlichen Teil davon direkt behandelt, auch wenn er nur ergänzt: Bedingungen, Ausnahmen, Begründungen, Belege oder die Erklärung eines Begriffs aus der Frage. Abschnitte, die das Thema nur nebenbei erwähnen, wählst du nicht. Hilft kein Abschnitt, gib eine leere Liste zurück."""

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
        nummern = [n for n in nummern if isinstance(n, int) and not isinstance(n, bool) and 0 < n < 2**62][:MAX_ABSCHNITTE] \
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


def mit_folgeabschnitten(con, treffer: list[dict]) -> list[dict]:
    """Hängt an die besten Treffer den direkt folgenden Abschnitt derselben Seite an, weil Aufzählungen
    oft über die Grenze zweier Abschnitte gehen. Höchstens MAX_ABSCHNITTE insgesamt."""
    ergebnis = list(treffer)
    schon = {t["nr"] for t in treffer}
    for t in treffer[:MIT_FOLGEABSCHNITT]:
        if len(ergebnis) >= MAX_ABSCHNITTE:
            break
        folge = abschnitt_danach(con, t)
        if folge and folge["nr"] not in schon:
            # direkt hinter seinen Vorgänger, damit der Text in der richtigen Reihenfolge steht
            ergebnis.insert(ergebnis.index(t) + 1, folge)
            schon.add(folge["nr"])
    return ergebnis[:MAX_ABSCHNITTE]


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
    treffer = mit_folgeabschnitten(con, treffer)

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
        output_config={"effort": ANTWORT_GRUENDLICHKEIT},
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
            # Was in diesem Stück noch folgt, gilt wie jedes andere Stück ohne Beleg
            if not rest.strip() or ist_gliederung(rest):
                if rest:
                    teile.append({"text": rest, "belege": []})
            else:
                ausgeblendet = True
                vorher_belegt = False
                if geruest(rest):
                    teile.append({"text": geruest(rest), "belege": []})
        elif ist_ueberleitung(block.text) or ist_gliederung(block.text):
            teile.append({"text": block.text, "belege": []})
        else:
            ausgeblendet = True
            vorher_belegt = False
            # Zeilenumbrüche und Listenzeichen bleiben, sonst eine Lücke, damit die übrigen Teile nicht aneinanderkleben
            gerippe = geruest(block.text)
            if gerippe:
                teile.append({"text": gerippe, "belege": []})
            elif teile and not teile[-1]["text"].endswith((" ", "\n")):
                teile.append({"text": " ", "belege": []})
    leere_punkte_entfernen(teile)

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
    return {"antwort": antwort_text, "quellen": quellen, "teile": teile, "hinweise": hinweise, "verweis": VERWEIS[lang],
            "art": "antwort", "sprache": lang, "abschnitte": zitiert}
