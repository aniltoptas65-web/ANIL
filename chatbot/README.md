# SeydaAI, interner Prototyp

Arbeitsname SeydaAI (Name noch offen zwischen SeydaAI und EhliSunnahAI). Nur für den internen Test durch Anil, nicht öffentlich. Betreiber: Verein Reyhani Europa e.V.

Der Bot beantwortet Fragen ausschließlich aus eingelesenen öffentlichen Seiten von Diyanet (Din İşleri Yüksek Kurulu), TDV İslâm Ansiklopedisi und Semerkand einschließlich Serhendi. Jede Antwort nennt ihre Quellen mit Link. Findet er nichts, sagt er das.

## So funktioniert es

1. `einlesen.py` ruft die Seiten aus `quellen.json` ab (langsam, mit Pause, nach robots.txt) und speichert den Text in der Datei `seyda.db`. Gespeichert werden nur Inhaltsseiten (Fetvas, Kurulbeschlüsse, häufige Fragen, Lexikonartikel), Menü und Übersichtsseiten dienen nur als Wegweiser.
2. Bei einer Frage macht Claude Haiku daraus eine eigenständige Frage und türkische Suchbegriffe. Dabei sieht Haiku die letzten drei Fragen und Antworten des Gesprächs, damit Rückfragen wie „nicht verstanden“ oder „und beim Fasten?“ funktionieren.
3. Die Volltextsuche holt bis zu 30 Kandidaten (höchstens drei Abschnitte je Seite), Treffer im Titel zählen dreifach. Claude Haiku liest kurze Vorschauen und wählt die bis zu sechs passenden aus. Passt keiner, sagt der Bot „nichts gefunden“. Bei einer Rückfrage kommen die in der vorigen Antwort zitierten Abschnitte zu den Kandidaten dazu.
4. Claude Sonnet formuliert nur aus diesen Abschnitten eine Antwort und sieht dabei auch die letzten drei Fragen und Antworten. Die Claude API markiert, welche Textstücke sich auf welche Quelle stützen (Citations). Textstücke ohne Beleg blendet der Bot aus und sagt das unter der Antwort. Stehen bleiben nur kurze Überleitungen ohne Satz und die gekennzeichnete Übersetzung direkt nach einem belegten Zitat. Der Verweis an Imam oder Fetva Stelle steht fest unter jeder Antwort. Hat die Antwort gar keinen Beleg, zeigt er stattdessen „nichts gefunden“.
5. Bei Wörtern, die auf eine Krise oder Gewalt hindeuten, antwortet der Bot ohne Sprachmodell sofort mit Hilfsnummern, auf Deutsch oder Türkisch. Das gilt auch, wenn das Tageslimit erreicht ist.

## Windows: einfach per Doppelklick

1. Die ZIP Datei ganz entpacken (Rechtsklick, „Alle extrahieren“), nicht aus der ZIP heraus starten.
2. Im entpackten Ordner `SeydaAI_starten.bat` doppelklicken. Zeigt Windows eine Warnung, je nach Fenster auf „Weitere Informationen“ und dann „Trotzdem ausführen“ klicken oder auf „Ausführen“.
3. Beim ersten Mal richtet das Fenster Python ein (fehlt Python, bietet es an, es über winget zu installieren) und fragt nach dem API Schlüssel aus der [Claude Konsole](https://platform.claude.com/) und nach einem frei wählbaren Passwort für die Seite. Der Schlüssel wird sofort mit einer kostenlosen Abfrage geprüft.
4. Danach fragt es, ob Quellen eingelesen werden sollen, bietet das Prüfset an (siehe unten) und öffnet SeydaAI im Browser. Benutzername beliebig, Passwort wie festgelegt.
5. Beenden: das Fenster schließen.

In der ZIP heißt der Ordner `SeydaAI`, im Repo `chatbot`; gemeint ist derselbe Ordner. Befehle wie `python zugang.py` gibst du unter Windows am besten so ein, damit das richtige Python greift: `"%LOCALAPPDATA%\SeydaAI\venv\Scripts\python.exe" zugang.py liste` (in der Eingabeaufforderung, im Ordner SeydaAI). Belegt ein anderes Programm die Adresse 127.0.0.1:8000, wählst du eine andere Zahl: im Ordner SeydaAI eine Eingabeaufforderung öffnen (in die Adresszeile des Explorers `cmd` tippen), dort `set SEYDA_PORT=8001` eingeben und danach im selben Fenster `SeydaAI_starten.bat` starten. Python aus dem Microsoft Store übergeht das Skript, weil es Dateien unter AppData umleiten kann.

Die Python Umgebung liegt unter `%LOCALAPPDATA%\SeydaAI\venv`, weil Windows sehr lange Pfade sonst nicht verträgt. Wenn du Schlüssel und Passwort merken lässt, liegen sie verschlüsselt in `%LOCALAPPDATA%\SeydaAI` (Windows DPAPI, lesbar nur mit deinem Windows Konto). Beim nächsten Start fragt das Fenster, ob es sie verwenden soll; mit `n` gibst du neue ein. Der Schlüssel landet nie im Projektordner, geht nur an die Schlüsselprüfung, das Prüfset und den SeydaAI Server und wird nicht dauerhaft in Windows gesetzt. So stört er auch Claude Code auf deinem Rechner nicht.

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

In `quellen.json` steht je Quelle, wo das Einlesen beginnt (`start`), welchen Adressen es folgen darf (`folgen`), aus welchen Seiten es Links sammelt (`links_aus`), welche Seiten gespeichert werden (`speichern`, ein Muster) und wie viele höchstens (`max_seiten`). Bei der TDV İslâm Ansiklopedisi beginnt es bei rund 90 Kernartikeln zu Glaube, Gottesdienst, Recht und Tasavvuf und nimmt deren verwandte Artikel dazu. Bei Diyanet liest es die Fetvas, die Beschlüsse des Kurul und die häufigen Fragen.

```
python einlesen.py
```

oder nur eine Quelle, zum Beispiel `python einlesen.py diyanet`. Bei zwei Sekunden Pause pro Seite dauert Diyanet (bis 1500 Seiten) geschätzt bis zu 75 Minuten, alle Quellen zusammen bis zu zwei Stunden. Abbrechen mit Strg+C ist jederzeit möglich: Inhaltsseiten, die in den letzten 30 Tagen nach denselben Regeln gespeichert wurden, ruft der nächste Lauf nicht noch einmal ab. Übersichtsseiten, aus denen er Links sammelt, liest er neu, damit er findet, was noch fehlt. `python einlesen.py --neu` holt alles frisch.

Seiten, die nach anderen Regeln eingelesen wurden (also auch alle Seiten aus dem ersten Lauf mit Menü und Firmenseiten) oder nicht mehr zum Muster passen, entfernt das Skript zu Beginn. Ändert sich eine Regel einer Quelle in `quellen.json`, liest es diese Quelle deshalb neu ein; neue Startadressen oder ein höheres `max_seiten` lösen das nicht aus. `semerkand.com.tr` ist laut ihrer Startseite die Seite der Semerkand Medya Grubu ohne religiöse Texte (nachgelesen am 9. November 2026), deshalb sind Semerkand und Serhendi im Moment leer. Sobald die Adressen der Seiten mit den Texten feststehen, kommen sie in `quellen.json`.

## Prüfset

```
python pruefset.py
```

stellt 20 Grundfragen auf Deutsch und Türkisch (darunter die Säulen des Islams) und eine Rückfrage zur ersten Antwort. Die Antworten mit Quellen landen in `pruefbericht_JJJJ-MM-TT_HHMM.md` im selben Ordner, oben stehen die Zahl der eingelesenen Seiten, wie viele Fragen eine Antwort bekamen und die Kosten laut Tokenzählung. Ein Lauf kostet geschätzt 20 bis 60 US Cent und zählt zum Tageslimit. Das Windows Startfenster bietet das Prüfset bei jedem Start an (`p`).

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

## Spracheingabe und Vorlesen

Neben dem Eingabefeld gibt es ein Mikrofon, darunter die Wahl zwischen Deutsch und Türkçe. Der erkannte Text landet im Eingabefeld und wird erst gesendet, wenn du ihn geprüft hast. Das Mikrofon erscheint nur, wenn der Browser Spracherkennung anbietet. Laut den Kompatibilitätsdaten von [MDN](https://developer.mozilla.org/docs/Web/API/SpeechRecognition#browser_compatibility) sind das Chrome und Edge sowie Safari, dort über die ältere Schnittstelle mit dem Vorsatz webkit. In Browsern ohne Spracherkennung, zum Beispiel älteren Firefox Versionen, fehlt der Knopf. Getestet ist bisher nur, dass der Knopf in Chromium erscheint, nicht die Erkennung mit echtem Mikrofon. Laut [MDN](https://developer.mozilla.org/docs/Web/API/Web_Speech_API/Using_the_Web_Speech_API) schickt der Browser die Aufnahme dafür in der Regel an einen Onlinedienst; deshalb fragt die Seite beim ersten Mal nach. Kann der Browser die gewählte Sprache auf dem Gerät selbst erkennen, nutzt die Seite das und fragt nicht. SeydaAI selbst bekommt keine Aufnahme, nur den Text.

Jede Antwort hat einen Knopf „Vorlesen“. Er nimmt bevorzugt eine Stimme, die laut Browser auf dem Gerät läuft. Gibt es für die Sprache nur eine Onlinestimme, fragt die Seite vorher, weil der Antworttext dann an einen Onlinedienst geht. Ohne Zustimmung liest eine andere Stimme des Geräts, mit falscher Aussprache.

## Was gespeichert wird

SeydaAI speichert Fragen und Antworten nicht. Ausnahme: Drückst du „Antwort melden“, landen diese eine Frage, die Antwort, die Quellen und deine Notiz in der Tabelle `meldungen` in `seyda.db`. Den Gesprächsverlauf für Rückfragen (die letzten drei Fragen und Antworten) hält nur die geöffnete Seite im Browser. Er geht mit jeder neuen Frage an den SeydaAI Server, der ihn nicht ablegt, und an die Claude API. Was Anthropic mit Eingaben an die API macht, etwa wie lange sie aufbewahrt werden, regeln die Bedingungen von Anthropic; das ist vor der Testgruppe zu klären. Neu laden beginnt ein neues Gespräch. Für die Kostenkontrolle zählt die Tabelle `verbrauch` pro Tag nur Modell und Tokens, ohne Text. Für die Zugänge stehen in `zugaenge` Name, Salz und Prüfwert des Codes, Tageslimit, ob der Zugang aktiv ist, und wann er angelegt wurde. In `fragen_pro_person` stehen nur Name, Tag und Anzahl der Fragen, ohne Inhalt. Zählerstände von früheren Tagen löscht der Server beim Start und bei jeder gezählten Frage über einen Zugang, es entsteht also kein Verlauf.

Höchstens 50 Fragen pro Tag (änderbar über `SEYDA_MAX_FRAGEN`). Das Limit zählt jede Frage, die an ein Sprachmodell geht.

## Kosten ansehen

```
python -c "from datenbank import verbinden; [print(tuple(z)) for z in verbinden().execute('select tag, modell, schritt, sum(eingabe), sum(ausgabe) from verbrauch group by 1,2,3')]"
```

Jede Frage braucht drei Aufrufe: Haiku versteht die Frage (`verstehen`), Haiku wählt Abschnitte aus (`auswaehlen`), Sonnet antwortet (`antworten`). Geschätzt kostet eine Frage zusammen 1 bis 3 US Cent.

Preise pro Million Tokens laut Anthropic: Sonnet 5.5 2 USD Eingabe und 10 USD Ausgabe, Haiku 5.5 0,10 und 0,50 USD.

## Grenzen dieses Prototyps

Die Volltextsuche findet nur Abschnitte, in denen die Suchbegriffe vorkommen; die Auswahl durch Haiku kann nur unter diesen Kandidaten wählen. Ob das reicht, zeigt das Prüfset. Im Kopf steht das Logo von Reyhani Europa (`web/reyhani_logo.png`, Hintergrund freigestellt). Die Oberfläche in `web/index.html` folgt Entwurf 1 „Klassisch“ mit grünem Online Punkt; der Punkt wird grau, wenn der Server nicht antwortet. Die Schriften Cormorant Garamond und Source Sans 3 liegen in `web/schriften` (SIL Open Font License, Lizenztexte daneben, Dateien aus den Fontsource Paketen 5.3) und kommen vom eigenen Server, nicht von Google. Enthalten sind die Zeichensätze Latin und Latin Extended, also auch ğ, ş, ı und İ. Aus der TDV İslâm Ansiklopedisi zitiert der Bot nicht wörtlich, sondern fasst nur zusammen.
