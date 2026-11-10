# SeydaAI, interner Prototyp

Arbeitsname SeydaAI (Name noch offen zwischen SeydaAI und EhliSunnahAI). Nur für den internen Test durch Anil, nicht öffentlich. Betreiber: Verein Reyhani Europa e.V.

Der Bot beantwortet Fragen ausschließlich aus eingelesenen öffentlichen Seiten von Diyanet (Din İşleri Yüksek Kurulu), TDV İslâm Ansiklopedisi und Semerkand einschließlich Serhendi. Jede Antwort nennt ihre Quellen mit Link. Findet er nichts, sagt er das.

## So funktioniert es

1. `einlesen.py` ruft die Seiten aus `quellen.json` ab (langsam, mit Pause, nach robots.txt) und speichert den Text in der Datei `seyda.db`. Gespeichert werden nur Inhaltsseiten (Fetvas, Kurulbeschlüsse, häufige Fragen, Lexikonartikel), Menü und Übersichtsseiten dienen nur als Wegweiser.
2. Bei einer Frage macht Claude Haiku daraus eine eigenständige Frage und türkische Suchbegriffe. Dabei sieht Haiku die letzten drei Fragen und Antworten des Gesprächs, damit Rückfragen wie „nicht verstanden“ oder „und beim Fasten?“ funktionieren.
3. Die Volltextsuche holt bis zu 30 Kandidaten (höchstens drei Abschnitte je Seite), Treffer im Titel zählen dreifach. Claude Haiku liest kurze Vorschauen und wählt die bis zu acht passenden aus, auch ergänzende Abschnitte mit Bedingungen, Ausnahmen oder Begründungen. Passt keiner, sagt der Bot „nichts gefunden“. Bei den drei besten kommt jeweils der nächste Abschnitt derselben Seite dazu, weil Aufzählungen oft über zwei Abschnitte gehen; insgesamt bekommt Sonnet höchstens zehn. Bei einer Rückfrage kommen die in der vorigen Antwort zitierten Abschnitte zu den Kandidaten dazu.
4. Claude Sonnet formuliert nur aus diesen Abschnitten eine Antwort und sieht dabei auch die letzten drei Fragen und Antworten. Es denkt vorher kurz nach (Gründlichkeit „medium“, einstellbar über `ANTWORT_GRUENDLICHKEIT` in `seyda.py`) und baut die Antwort fest auf: zuerst ein oder zwei Sätze als direkte Antwort, dann Aufzählungen als nummerierte Liste mit dem Fachbegriff in Fett und kurzer Erklärung, danach Bedingungen und Ausnahmen, in einfachen Sätzen. Die Claude API markiert, welche Textstücke sich auf welche Quelle stützen (Citations). Textstücke ohne Beleg blendet der Bot aus und sagt das unter der Antwort. Stehen bleiben nur kurze Überleitungen ohne Satz, Gliederung (Leerzeilen, Satzzeichen, Listennummern und Stichwörter mit Doppelpunkt wie „**Namaz** (Gebet):“) und die gekennzeichnete Übersetzung direkt nach einem belegten Zitat. Enthält ein solches Stück ein Urteilswort, wird es trotzdem ausgeblendet, damit kein unbelegtes Urteil als Stichwort durchrutscht. Dazu zählen Wörter wie „ist“, „nicht“, „ja“ oder „nein“ und alle Formen von Wörtern wie „haram“, „caiz“, „farz“, „sünnet“, „kabul“, „erlaubt“, „untersagt“ oder „Problem“, also auch „haramdır“, „kabul edilmez“, „verpflichtend“ oder „unproblematisch“, außerdem türkische Verneinungen wie „olmaz“ oder „içilmez“. Übersetzungen wie „Pflichtabgabe“ für Zekât gelten nicht als Urteil. Sonnet ist zusätzlich angewiesen, ein Urteil nie ins Stichwort zu schreiben, sondern in den belegten Satz dahinter. Wird ein Stück ausgeblendet, bleiben seine Zeilenumbrüche und Listennummern stehen, damit die Gliederung erhalten bleibt. Die Seite zeigt hinter jeder belegten Zeile eine kleine Nummer, die zur nummerierten Quellenliste unter der Antwort passt. Der Verweis an Imam oder Fetva Stelle steht fest unter jeder Antwort. Hat die Antwort gar keinen Beleg, zeigt er stattdessen „nichts gefunden“.
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

stellt 20 Grundfragen auf Deutsch und Türkisch (darunter die Säulen des Islams) und eine Rückfrage zur ersten Antwort. Die Antworten mit Quellen landen in `pruefbericht_JJJJ-MM-TT_HHMM.md` im selben Ordner, oben stehen die Zahl der eingelesenen Seiten, wie viele Fragen eine Antwort bekamen und die Kosten laut Tokenzählung. Ein Lauf kostet geschätzt 40 US Cent bis 1 US Dollar und zählt zum Tageslimit. Das Windows Startfenster bietet das Prüfset bei jedem Start an (`p`).

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

Neben dem Eingabefeld gibt es ein Mikrofon, darunter die Wahl zwischen Deutsch und Türkçe. Der erkannte Text landet im Eingabefeld und wird erst gesendet, wenn du ihn geprüft hast. Das Mikrofon erscheint nur, wenn der Browser Spracherkennung anbietet. Laut den Kompatibilitätsdaten von [MDN](https://developer.mozilla.org/docs/Web/API/SpeechRecognition#browser_compatibility) sind das Chrome und Edge sowie Safari, dort über die ältere Schnittstelle mit dem Vorsatz webkit. Firefox führen die MDN Daten erst ab sehr neuen Versionen; in Browsern ohne Spracherkennung fehlt der Knopf. Getestet ist bisher nur, dass der Knopf in Chromium erscheint, nicht die Erkennung mit echtem Mikrofon. Laut [MDN](https://developer.mozilla.org/docs/Web/API/Web_Speech_API/Using_the_Web_Speech_API) schickt der Browser die Aufnahme dafür in der Regel an einen Onlinedienst; deshalb fragt die Seite beim ersten Mal nach. Kann der Browser die gewählte Sprache auf dem Gerät selbst erkennen, nutzt die Seite das und fragt nicht. SeydaAI selbst bekommt keine Aufnahme, nur den Text.

Jede Antwort hat einen Knopf „Vorlesen“. Die Seite sucht je Sprache die deutlichste Stimme, die das Gerät anbietet: zuerst natürliche Stimmen (in Microsoft Edge heißen sie „Online (Natural)“, bei Google auf Android und ChromeOS „Natural“), dann verbesserte Apple Stimmen („Erweitert“, „Premium“, „Geliştirilmiş“), dann Google Stimmen, zuletzt die übrigen. Türkische Antworten liest eine türkische Stimme, ein türkisches Zitat in einer deutschen Antwort ebenfalls, ebenso ein ganzer türkischer Satz. Deutsche Sätze mit türkischen Fachbegriffen wie „Dazu gehören Kıyâm, Rükû und Secde“ liest die deutsche Stimme. Gibt es keine türkische Stimme, überspringt die Seite nur das Zitat und sagt das; die deutsche Übersetzung darunter wird gelesen, alles andere liest die deutsche Stimme. Vorher entfernt die Seite Formatzeichen, Links und arabische Schrift und schreibt Abkürzungen aus (zum Beispiel „z. B.“, „(s.a.v.)“, „Hz.“, „vb.“). Gelesen wird etwas langsamer als normal und in kurzen Stücken, weil laut Readium manche Stimmen in Chrome Texte abbrechen, die länger als 14 Sekunden dauern.

Bevor die Seite eine Onlinestimme nimmt, fragt sie einmal, weil der vorgelesene Text dann an den Anbieter der Stimme geht (zum Beispiel Microsoft oder Google). Über das Zahnrad oben rechts lassen sich die Stimme je Sprache, das Tempo und die Onlinestimmen ändern, mit Hörprobe; wer dort selbst eine Onlinestimme auswählt, schaltet damit Onlinestimmen ein, und Ausschalten setzt die Auswahl zurück. Am PC klingt es nach unserer Einschätzung in Microsoft Edge am deutlichsten, weil Edge die natürlichen Stimmen für Deutsch und Türkisch mitbringt (Stimmenlisten von Readium: [de.json](https://github.com/readium/speech/blob/main/json/de.json), [tr.json](https://github.com/readium/speech/blob/main/json/tr.json)); laut [Readium](https://readium.org/speech/docs/WebSpeech.html) brauchen diese Stimmen eine Internetverbindung. In der Liste von Readium steht für Chrome am PC keine türkische Stimme. Chrome auf Android liefert laut Readium keine echte Stimmenliste, sondern eine Liste von Sprachen, auch solcher, deren Sprachpaket fehlt; dann liest Chrome mit einer englischen Stimme. Wer auf Android türkische Antworten hören will, installiert in den Einstellungen des Handys unter Sprachausgabe das türkische Sprachpaket. Getestet ist die Auswahl mit nachgebildeten Stimmenlisten, nicht mit echten Lautsprechern.

## Chatverlauf und Handy

Links steht eine Seitenleiste mit früheren Unterhaltungen, auf dem Handy über das Menü oben links. Dort gibt es „Neuer Chat“, alte Unterhaltungen lassen sich öffnen, weiterführen und einzeln oder alle löschen. Der Stift oben rechts startet ebenfalls einen neuen Chat; auf sehr schmalen Handys (300 Pixel Breite und weniger) fehlt er aus Platzgründen, dort geht das über das Menü. Die obere Leiste mit Menü, Stift und Zahnrad bleibt beim Scrollen stehen. Nach dem Senden springt die Seite nach unten, und auf dem Handy schließt sich die Tastatur. Sobald die Antwort da ist, springt die Seite an ihren Anfang. Die Seite ist zuerst für Handybreiten gebaut und auf 280, 320, 360, 390 und 414 Pixel Breite sowie am PC getestet (am Rechner nachgebildet, nicht auf einem echten Handy).

Der Verlauf liegt im Speicher der Seite auf dem jeweiligen Gerät, höchstens 50 Unterhaltungen mit je 40 Fragen. Wird der Speicher voll, fällt die älteste Unterhaltung weg; passt nicht einmal die neueste hinein, sagt die Seite unten in der Seitenleiste, dass nichts gespeichert wurde. Wer das Gerät benutzt, kann den Verlauf sehen, auch wenn sich mehrere Personen mit verschiedenen Zugängen am selben Gerät anmelden. Darum lässt er sich über das Zahnrad ausschalten; dabei werden die gespeicherten Unterhaltungen auf dem Gerät gelöscht und die Seite beginnt einen neuen Chat. Solange der Verlauf aus ist, wird nichts gespeichert, und beim Wiedereinschalten beginnt der Verlauf leer. Ist die Seite in mehreren Fenstern offen, zeigen alle denselben Verlauf; wird eine Unterhaltung in einem Fenster gelöscht, verschwindet sie auch in den anderen. Fragen, auf die der Bot mit den Hilfsnummern antwortet (Krise, Gewalt), kommen nie in den Verlauf.

Mit dem Hosting soll ein Verlauf auf dem Server dazukommen, der auf Handy und PC gleich ist; dafür braucht es eine Anmeldung je Person und eine ausdrückliche Einwilligung, weil Fragen zum Glauben religiöse Überzeugungen erkennen lassen können ([Art. 9 DSGVO](https://recht.nulegal.eu/gesetze/DSGVO/9)). Solange SeydaAI auf deinem PC läuft (Adresse 127.0.0.1), ist es vom Handy aus nicht erreichbar. Die Handyansicht lässt sich am PC trotzdem ansehen: in Edge oder Chrome F12 drücken und dann Strg+Umschalt+M.

## Was gespeichert wird

Der SeydaAI Server speichert Fragen und Antworten aus dem Chat nicht. Ausnahmen: Drückst du „Antwort melden“, landen diese eine Frage, die Antwort, die Quellen und deine Notiz in der Tabelle `meldungen` in `seyda.db`. Das Prüfset schreibt seine eigenen Fragen und Antworten in den Prüfbericht. Den Chatverlauf hält nur das Gerät, auf dem gefragt wird (siehe Chatverlauf und Handy), ebenso die gewählten Stimmen und das Tempo. Damit mehrere offene Fenster gelöschte Unterhaltungen nicht wieder speichern, merkt sich die Seite bei eingeschaltetem Verlauf außerdem die zufälligen Nummern der zuletzt gelöschten Unterhaltungen und nach „Alle löschen“ eine zufällige Marke, beides ohne Inhalt und ohne Uhrzeit; beim Ausschalten des Verlaufs werden auch diese gelöscht. Die letzten drei Fragen und Antworten der offenen Unterhaltung gehen mit jeder neuen Frage an den SeydaAI Server, der sie nicht ablegt, und an die Claude API. Was Anthropic mit Eingaben an die API macht, etwa wie lange sie aufbewahrt werden, regeln die Bedingungen von Anthropic; das ist vor der Testgruppe zu klären. Für die Kostenkontrolle zählt die Tabelle `verbrauch` pro Tag nur Modell und Tokens, ohne Text. Für die Zugänge stehen in `zugaenge` Name, Salz und Prüfwert des Codes, Tageslimit, ob der Zugang aktiv ist, und wann er angelegt wurde. In `fragen_pro_person` stehen nur Name, Tag und Anzahl der Fragen, ohne Inhalt. Zählerstände von früheren Tagen löscht der Server beim Start und bei jeder gezählten Frage über einen Zugang, es entsteht also kein Verlauf.

Höchstens 50 Fragen pro Tag (änderbar über `SEYDA_MAX_FRAGEN`). Das Limit zählt jede Frage, die an ein Sprachmodell geht.

## Kosten ansehen

```
python -c "from datenbank import verbinden; [print(tuple(z)) for z in verbinden().execute('select tag, modell, schritt, sum(eingabe), sum(ausgabe) from verbrauch group by 1,2,3')]"
```

Jede Frage braucht drei Aufrufe: Haiku versteht die Frage (`verstehen`), Haiku wählt Abschnitte aus (`auswaehlen`), Sonnet antwortet (`antworten`). Geschätzt kostet eine Frage zusammen 2 bis 5 US Cent; der größte Teil entfällt auf Sonnet, das bis zu zehn Abschnitte liest und vor der Antwort kurz nachdenkt. Bei einem Monatslimit von 20 USD reicht das grob für 400 bis 1000 Fragen. Die echten Zahlen zeigt die Tabelle `verbrauch` oder der Kopf des Prüfberichts.

Preise pro Million Tokens laut Anthropic: Sonnet 5.5 2 USD Eingabe und 10 USD Ausgabe, Haiku 5.5 0,10 und 0,50 USD.

## Grenzen dieses Prototyps

Die Volltextsuche findet nur Abschnitte, in denen die Suchbegriffe vorkommen; die Auswahl durch Haiku kann nur unter diesen Kandidaten wählen. Ob das reicht, zeigt das Prüfset. Im Kopf steht das Logo von Reyhani Europa (`web/reyhani_logo.png`, Hintergrund freigestellt). Die Oberfläche in `web/index.html` folgt Entwurf 1 „Klassisch“ mit grünem Online Punkt; der Punkt wird grau, wenn der Server nicht antwortet. Die Schriften Cormorant Garamond und Source Sans 3 liegen in `web/schriften` (SIL Open Font License, Lizenztexte daneben, Dateien aus den Fontsource Paketen 5.3) und kommen vom eigenen Server, nicht von Google. Enthalten sind die Zeichensätze Latin und Latin Extended, also auch ğ, ş, ı und İ. Aus der TDV İslâm Ansiklopedisi zitiert der Bot nicht wörtlich, sondern fasst nur zusammen.
