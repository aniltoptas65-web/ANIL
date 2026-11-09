# SeydaAI, interner Prototyp

Arbeitsname SeydaAI (Name noch offen zwischen SeydaAI und EhliSunnahAI). Nur für den internen Test durch Anil, nicht öffentlich. Betreiber: Verein Reyhani Europa e.V.

Der Bot beantwortet Fragen ausschließlich aus eingelesenen öffentlichen Seiten von Diyanet (Din İşleri Yüksek Kurulu), TDV İslâm Ansiklopedisi und Semerkand einschließlich Serhendi. Jede Antwort nennt ihre Quellen mit Link. Findet er nichts, sagt er das.

## So funktioniert es

1. `einlesen.py` ruft die Seiten aus `quellen.json` ab (langsam, mit Pause, nach robots.txt) und speichert den Text in der Datei `seyda.db`.
2. Bei einer Frage macht Claude Haiku daraus türkische Suchbegriffe.
3. Die Volltextsuche findet bis zu sechs passende Abschnitte.
4. Claude Sonnet formuliert nur aus diesen Abschnitten eine Antwort. Die Claude API markiert, welche Textstücke sich auf welche Quelle stützen (Citations). Textstücke ohne Beleg blendet der Bot aus und sagt das unter der Antwort. Stehen bleiben nur kurze Überleitungen ohne Satz und die gekennzeichnete Übersetzung direkt nach einem belegten Zitat. Der Verweis an Imam oder Fetva Stelle steht fest unter jeder Antwort. Hat die Antwort gar keinen Beleg, zeigt er stattdessen „nichts gefunden“.
5. Bei Wörtern, die auf eine Krise oder Gewalt hindeuten, antwortet der Bot ohne Sprachmodell sofort mit Hilfsnummern, auf Deutsch oder Türkisch. Das gilt auch, wenn das Tageslimit erreicht ist.

## Einrichten auf deinem Rechner

Du brauchst Python 3.10 oder neuer ([python.org](https://www.python.org/downloads/); unter Windows bei der Installation das Häkchen „Add python.exe to PATH“ setzen) und einen API Schlüssel aus der [Claude Konsole](https://platform.claude.com/). Lege dort zuerst ein Monatslimit fest, Vorschlag 20 USD.

Im Ordner `chatbot` einmalig:

```
pip install -r requirements.txt
```

Schlüssel und Passwort setzen (Windows PowerShell):

```
$env:ANTHROPIC_API_KEY = "dein Schlüssel"
$env:SEYDA_PASSWORT = "ein Passwort deiner Wahl"
```

Auf dem Mac oder unter Linux:

```
export ANTHROPIC_API_KEY="dein Schlüssel"
export SEYDA_PASSWORT="ein Passwort deiner Wahl"
```

Den Schlüssel nie in eine Datei im Repo schreiben.

## Quellen einlesen

Zuerst in `quellen.json` die Startadressen im Browser prüfen. `semerkand.com.tr` ist laut ihrer Startseite die Seite der Semerkand Medya Grubu (nachgelesen am 9. November 2026); falls die Artikel auf einer anderen Adresse liegen, dort eintragen. Für Serhendi ist noch keine Adresse eingetragen, weil eine kurze Websuche keine offizielle Seite ergeben hat. Dann:

```
python einlesen.py
```

oder nur eine Quelle, zum Beispiel `python einlesen.py diyanet`. Pro Quelle werden höchstens 200 Seiten gelesen (in `quellen.json` änderbar). Bei zwei Sekunden Pause dauert das pro Quelle etwa zehn Minuten.

## Starten

```
python server.py
```

Dann im Browser `http://127.0.0.1:8000` öffnen. Benutzername ist egal, Passwort wie gesetzt. Der Server ist nur auf deinem Rechner erreichbar.

## Was gespeichert wird

Fragen und Antworten werden nicht gespeichert. Ausnahme: Drückst du „Antwort melden“, landen diese eine Frage, die Antwort, die Quellen und deine Notiz in der Tabelle `meldungen` in `seyda.db`. Für die Kostenkontrolle zählt die Tabelle `verbrauch` pro Tag nur Modell und Tokens, ohne Text.

Höchstens 50 Fragen pro Tag (änderbar über `SEYDA_MAX_FRAGEN`). Das Limit zählt jede Frage, die an ein Sprachmodell geht.

## Kosten ansehen

```
python -c "from datenbank import verbinden; [print(tuple(z)) for z in verbinden().execute('select tag, modell, sum(eingabe), sum(ausgabe) from verbrauch group by 1,2')]"
```

Preise pro Million Tokens laut Anthropic: Sonnet 5.5 2 USD Eingabe und 10 USD Ausgabe, Haiku 5.5 0,10 und 0,50 USD.

## Grenzen dieses Prototyps

Die Volltextsuche findet nur Abschnitte, in denen die Suchbegriffe vorkommen. Ob das reicht, zeigt das Prüfset mit deinen 50 Fragen. Die Oberfläche in `web/index.html` folgt Entwurf 1 „Klassisch“ mit grünem Online Punkt; der Punkt wird grau, wenn der Server nicht antwortet. Die Schriften Cormorant Garamond und Source Sans 3 lädt die Seite bewusst nicht von Google; ohne sie zeigt der Browser Georgia und eine Systemschrift. Vor der Testgruppe binde ich sie lokal ein. Aus der TDV İslâm Ansiklopedisi zitiert der Bot nicht wörtlich, sondern fasst nur zusammen.
