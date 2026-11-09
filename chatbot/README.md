# SeydaAI, interner Prototyp

Arbeitsname SeydaAI (Name noch offen zwischen SeydaAI und EhliSunnahAI). Nur für den internen Test durch Anil, nicht öffentlich. Betreiber: Verein Reyhani Europa e.V.

Der Bot beantwortet Fragen ausschließlich aus eingelesenen öffentlichen Seiten von Diyanet (Din İşleri Yüksek Kurulu), TDV İslâm Ansiklopedisi und Semerkand einschließlich Serhendi. Jede Antwort nennt ihre Quellen mit Link. Findet er nichts, sagt er das.

## So funktioniert es

1. `einlesen.py` ruft die Seiten aus `quellen.json` ab (langsam, mit Pause, nach robots.txt) und speichert den Text in der Datei `seyda.db`.
2. Bei einer Frage macht Claude Haiku daraus türkische Suchbegriffe.
3. Die Volltextsuche findet bis zu sechs passende Abschnitte.
4. Claude Sonnet formuliert nur aus diesen Abschnitten eine Antwort. Die Claude API markiert, welche Textstücke sich auf welche Quelle stützen (Citations). Textstücke ohne Beleg blendet der Bot aus und sagt das unter der Antwort. Stehen bleiben nur kurze Überleitungen ohne Satz und die gekennzeichnete Übersetzung direkt nach einem belegten Zitat. Der Verweis an Imam oder Fetva Stelle steht fest unter jeder Antwort. Hat die Antwort gar keinen Beleg, zeigt er stattdessen „nichts gefunden“.
5. Bei Wörtern, die auf eine Krise oder Gewalt hindeuten, antwortet der Bot ohne Sprachmodell sofort mit Hilfsnummern, auf Deutsch oder Türkisch. Das gilt auch, wenn das Tageslimit erreicht ist.

## Windows: einfach per Doppelklick

1. Die ZIP Datei ganz entpacken (Rechtsklick, „Alle extrahieren“), nicht aus der ZIP heraus starten.
2. Im entpackten Ordner `SeydaAI_starten.bat` doppelklicken. Zeigt Windows eine Warnung, je nach Fenster auf „Weitere Informationen“ und dann „Trotzdem ausführen“ klicken oder auf „Ausführen“.
3. Beim ersten Mal richtet das Fenster Python ein (fehlt Python, bietet es an, es über winget zu installieren) und fragt nach dem API Schlüssel aus der [Claude Konsole](https://platform.claude.com/) und nach einem frei wählbaren Passwort für die Seite. Der Schlüssel wird sofort mit einer kostenlosen Abfrage geprüft.
4. Danach fragt es, ob Quellen eingelesen werden sollen, und öffnet SeydaAI im Browser. Benutzername beliebig, Passwort wie festgelegt.
5. Beenden: das Fenster schließen.

In der ZIP heißt der Ordner `SeydaAI`, im Repo `chatbot`; gemeint ist derselbe Ordner. Befehle wie `python zugang.py` gibst du unter Windows am besten so ein, damit das richtige Python greift: `"%LOCALAPPDATA%\SeydaAI\venv\Scripts\python.exe" zugang.py liste` (in der Eingabeaufforderung, im Ordner SeydaAI). Belegt ein anderes Programm die Adresse 127.0.0.1:8000, wählst du eine andere Zahl: im Ordner SeydaAI eine Eingabeaufforderung öffnen (in die Adresszeile des Explorers `cmd` tippen), dort `set SEYDA_PORT=8001` eingeben und danach im selben Fenster `SeydaAI_starten.bat` starten. Python aus dem Microsoft Store übergeht das Skript, weil es Dateien unter AppData umleiten kann.

Die Python Umgebung liegt unter `%LOCALAPPDATA%\SeydaAI\venv`, weil Windows sehr lange Pfade sonst nicht verträgt. Wenn du Schlüssel und Passwort merken lässt, liegen sie verschlüsselt in `%LOCALAPPDATA%\SeydaAI` (Windows DPAPI, lesbar nur mit deinem Windows Konto). Beim nächsten Start fragt das Fenster, ob es sie verwenden soll; mit `n` gibst du neue ein. Der Schlüssel landet nie im Projektordner, geht nur an die Schlüsselprüfung und an den SeydaAI Server und wird nicht dauerhaft in Windows gesetzt. So stört er auch Claude Code auf deinem Rechner nicht.

## Einrichten von Hand (Mac, Linux oder Windows)

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

## Zugänge für die Testgruppe

Jede Person bekommt einen eigenen Namen, einen zufälligen Code und ein eigenes Tageslimit. So lässt sich einzeln sperren, wer nicht mehr testen soll, und niemand verbraucht das persönliche Kontingent der anderen.

```
python zugang.py neu "Ayse K" 10
python zugang.py liste
python zugang.py sperren "Ayse K"
python zugang.py loeschen "Ayse K"
```

`neu` zeigt den Code genau einmal an. Gespeichert wird nur ein Prüfwert, der Code selbst lässt sich später nicht mehr anzeigen. Wer seinen Code verliert, bekommt mit `loeschen` und danach `neu` einen neuen. Beim Anmelden ist der Benutzername der Name aus `zugang.py` und das Passwort der Code. Der Name muss genau so eingegeben werden wie angelegt, auch Groß und Kleinschreibung und Leerzeichen zählen. Als Namen reichen Vornamen oder Kürzel, am besten ohne türkische Sonderzeichen (Ayse statt Ayşe), weil nicht jeder Browser sie beim Anmelden gleich überträgt. `loeschen` setzt auch den heutigen Zähler der Person zurück.

Gezählt wird jede Frage, die an ein Sprachmodell geht, auch wenn danach ein Fehler kommt. Fragen mit Krisenwörtern zählen nicht. Zusätzlich gilt `SEYDA_MAX_FRAGEN` als gemeinsame Obergrenze für alle zusammen, deine eigenen Fragen eingeschlossen. Ist sie erreicht, ist für alle Schluss, auch wenn jemand sein persönliches Limit noch nicht ausgeschöpft hat. Für die Testgruppe also passend hochsetzen, zum Beispiel 10 Personen mal 10 Fragen gleich 100.

Mit dem Passwort aus `SEYDA_PASSWORT` meldest du dich weiterhin selbst an, für dich gilt nur die gemeinsame Obergrenze. Ohne `SEYDA_PASSWORT` startet der Server nur, wenn mindestens ein aktiver, also nicht gesperrter Zugang angelegt ist.

Solange der Server nur auf deinem Rechner läuft, kommen die Kollegen noch nicht heran. Dafür braucht es den kleinen gemieteten Server aus dem Plan (Stufe B). Vor diesem Schritt sind noch zwei Dinge nötig: HTTPS, weil die Anmeldung Name und Code sonst lesbar durchs Netz schickt, und die Prüfung der Herkunft in `server.py`, die im Moment nur Anfragen von 127.0.0.1 und localhost zulässt.

## Was gespeichert wird

Fragen und Antworten werden nicht gespeichert. Ausnahme: Drückst du „Antwort melden“, landen diese eine Frage, die Antwort, die Quellen und deine Notiz in der Tabelle `meldungen` in `seyda.db`. Für die Kostenkontrolle zählt die Tabelle `verbrauch` pro Tag nur Modell und Tokens, ohne Text. Für die Zugänge stehen in `zugaenge` Name, Salz und Prüfwert des Codes, Tageslimit, ob der Zugang aktiv ist, und wann er angelegt wurde. In `fragen_pro_person` stehen nur Name, Tag und Anzahl der Fragen, ohne Inhalt. Zählerstände von früheren Tagen löscht der Server beim Start und bei jeder gezählten Frage über einen Zugang, es entsteht also kein Verlauf.

Höchstens 50 Fragen pro Tag (änderbar über `SEYDA_MAX_FRAGEN`). Das Limit zählt jede Frage, die an ein Sprachmodell geht.

## Kosten ansehen

```
python -c "from datenbank import verbinden; [print(tuple(z)) for z in verbinden().execute('select tag, modell, sum(eingabe), sum(ausgabe) from verbrauch group by 1,2')]"
```

Preise pro Million Tokens laut Anthropic: Sonnet 5.5 2 USD Eingabe und 10 USD Ausgabe, Haiku 5.5 0,10 und 0,50 USD.

## Grenzen dieses Prototyps

Die Volltextsuche findet nur Abschnitte, in denen die Suchbegriffe vorkommen. Ob das reicht, zeigt das Prüfset mit deinen 50 Fragen. Die Oberfläche in `web/index.html` folgt Entwurf 1 „Klassisch“ mit grünem Online Punkt; der Punkt wird grau, wenn der Server nicht antwortet. Die Schriften Cormorant Garamond und Source Sans 3 liegen in `web/schriften` (SIL Open Font License, Lizenztexte daneben, Dateien aus den Fontsource Paketen 5.3) und kommen vom eigenen Server, nicht von Google. Enthalten sind die Zeichensätze Latin und Latin Extended, also auch ğ, ş, ı und İ. Aus der TDV İslâm Ansiklopedisi zitiert der Bot nicht wörtlich, sondern fasst nur zusammen.
