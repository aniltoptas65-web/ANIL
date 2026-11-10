# SeydaAI starten (Windows). Wird von SeydaAI_starten.bat aufgerufen.
#
# Beim ersten Mal: Python prüfen oder installieren, Pakete einrichten, API Schlüssel und Passwort abfragen,
# Quellen einlesen, auf Wunsch das Prüfset. Danach: Server starten und Browser öffnen.
#
# Die Python Umgebung liegt unter %LOCALAPPDATA%\SeydaAI\venv, weil Windows sehr lange Pfade sonst nicht verträgt.
# Der API Schlüssel landet nie im Projektordner. Auf Wunsch wird er mit dem Windows eigenen Schutz (DPAPI)
# verschlüsselt unter %LOCALAPPDATA%\SeydaAI gespeichert; nur dein Windows Benutzerkonto kann ihn wieder lesen.
# Als Umgebungsvariable steht er nur kurz für die Schlüsselprüfung, das Prüfset und den Start des SeydaAI Servers bereit und wird danach
# wieder entfernt; der Browser und andere später gestartete Programme bekommen ihn nicht.

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot
# Python schreibt UTF 8, damit türkische Zeichen wie İ und ş richtig ankommen
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Port = 8000
if ($env:SEYDA_PORT) { $Port = [int]$env:SEYDA_PORT }
$Adresse = "http://127.0.0.1:$Port"
$Ablage = Join-Path $env:LOCALAPPDATA "SeydaAI"
$VenvOrdner = Join-Path $Ablage "venv"
$venvPy = Join-Path $VenvOrdner "Scripts\python.exe"
$SchluesselDatei = Join-Path $Ablage "api_schluessel.txt"
$PasswortDatei = Join-Path $Ablage "seiten_passwort.txt"

function Stopp([string]$text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Red
    exit 1
}

function Abschnitt([string]$text) {
    Write-Host ""
    Write-Host "== $text ==" -ForegroundColor Cyan
}

function PortBelegt([int]$nummer) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient("127.0.0.1", $nummer)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

# Sucht ein Python ab Version 3.10. Gibt den Befehl als Liste zurück (zum Beispiel py -3), sonst $null.
# Python aus dem Microsoft Store (Pfad mit WindowsApps) wird übergangen, weil es Schreibzugriffe unter
# AppData umleiten kann und die Umgebung dann nicht dort landet, wo das Skript sie sucht.
function PythonFinden {
    $kandidaten = New-Object System.Collections.ArrayList
    [void]$kandidaten.Add(@("py", "-3"))
    $muster = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python3*\python.exe"),
        (Join-Path $env:ProgramFiles "Python3*\python.exe")
    )
    foreach ($m in $muster) {
        Get-ChildItem -Path $m -ErrorAction SilentlyContinue | ForEach-Object { [void]$kandidaten.Add(@($_.FullName)) }
    }
    [void]$kandidaten.Add(@("python"))
    foreach ($k in $kandidaten) {
        $befehl = $k[0]
        $rest = @($k | Select-Object -Skip 1)
        try {
            $ausgabe = & $befehl @rest -c "import sys; print(1 if sys.version_info >= (3, 10) and 'windowsapps' not in sys.executable.lower() else 0)" 2>$null
            if ($LASTEXITCODE -eq 0 -and "$ausgabe".Trim() -eq "1") { return ,$k }
        } catch { }
    }
    return $null
}

function UmgebungBrauchbar {
    if (-not (Test-Path -LiteralPath $venvPy)) { return $false }
    try {
        & $venvPy -m pip --version 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function UmgebungLoeschen {
    Remove-Item -LiteralPath $VenvOrdner -Recurse -Force -ErrorAction SilentlyContinue
}

function Klartext($sicher) {
    return (New-Object System.Net.NetworkCredential("", $sicher)).Password
}

# Fragt eine geheime Angabe ab. Die Eingabe erscheint nur als Sternchen.
function GeheimAbfragen([string]$frage, [string]$pruefMuster, [string]$pruefHinweis) {
    while ($true) {
        $klar = (Klartext (Read-Host $frage -AsSecureString)).Trim()
        if (-not $klar) { Write-Host "Die Eingabe war leer."; continue }
        if ($pruefMuster -and ($klar -notmatch $pruefMuster)) { Write-Host $pruefHinweis; continue }
        return $klar
    }
}

function GeheimMerken([string]$datei, [string]$klar) {
    $merken = Read-Host "Auf diesem Rechner verschlüsselt merken, damit du es nicht jedes Mal eingeben musst? (j/n)"
    if ($merken -match '^[jJyY]') {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $datei) | Out-Null
        ConvertTo-SecureString $klar -AsPlainText -Force | ConvertFrom-SecureString | Set-Content -LiteralPath $datei
        Write-Host "Gespeichert."
    } elseif (Test-Path -LiteralPath $datei) {
        Remove-Item -LiteralPath $datei -Force -ErrorAction SilentlyContinue
    }
}

# Liest eine gespeicherte Angabe, wenn vorhanden und gewünscht. Gibt sonst eine leere Zeichenkette zurück.
function GeheimGespeichert([string]$datei, [string]$name) {
    if (-not (Test-Path -LiteralPath $datei)) { return "" }
    try {
        $klar = Klartext (Get-Content -LiteralPath $datei -ErrorAction Stop | ConvertTo-SecureString -ErrorAction Stop)
    } catch {
        Write-Host "$name ist gespeichert, ließ sich aber nicht lesen. Bitte neu eingeben."
        return ""
    }
    $wahl = Read-Host "$name ist gespeichert. Enter = verwenden, n = neu eingeben"
    if ($wahl -match '^[nN]') { return "" }
    return $klar
}

Write-Host "SeydaAI, interner Test" -ForegroundColor Yellow

if (PortBelegt $Port) {
    Stopp "Unter $Adresse antwortet schon ein Programm. Läuft SeydaAI vielleicht schon in einem anderen Fenster? Dann einfach den Browser dort verwenden oder das andere Fenster schließen. Ist kein anderes SeydaAI Fenster offen, belegt ein anderes Programm diese Adresse; dann hilft oft ein Neustart des Rechners. Sonst steht in der Anleitung README.md, wie man eine andere Adresse wählt."
}

# 1. Python Umgebung
if (-not (UmgebungBrauchbar)) {
    Abschnitt "Python einrichten (nur beim ersten Mal)"
    UmgebungLoeschen
    $py = PythonFinden
    if (-not $py) {
        Write-Host "Python 3.10 oder neuer wurde nicht gefunden. Python aus dem Microsoft Store zählt dabei nicht mit, weil es hier nicht zuverlässig funktioniert."
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            $antwort = Read-Host "Soll ich Python 3.12 jetzt über winget installieren? Windows fragt dabei eventuell nach deiner Erlaubnis. (j/n)"
            if ($antwort -match '^[jJyY]') {
                winget install --exact --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
                $py = PythonFinden
            }
        }
        if (-not $py) {
            Stopp "Bitte Python von https://www.python.org/downloads/ installieren und danach SeydaAI_starten.bat noch einmal doppelklicken. Beim klassischen Installer dabei das Häkchen 'Add python.exe to PATH' setzen."
        }
    }
    New-Item -ItemType Directory -Force -Path $Ablage | Out-Null
    $befehl = $py[0]
    $rest = @($py | Select-Object -Skip 1)
    & $befehl @rest -m venv $VenvOrdner
    if ($LASTEXITCODE -ne 0 -or -not (UmgebungBrauchbar)) {
        UmgebungLoeschen
        Stopp "Die Python Umgebung ließ sich nicht anlegen. Die Meldung steht oben. Hilft oft: Python direkt von https://www.python.org/downloads/ installieren und noch einmal starten."
    }
}

Abschnitt "Pakete prüfen (beim ersten Mal etwa eine Minute)"
& $venvPy -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Stopp "Die Pakete ließen sich nicht installieren. Besteht eine Internetverbindung? Die Meldung steht oben. Passiert das immer wieder, den Ordner $VenvOrdner löschen und neu starten."
}
Write-Host "Pakete sind bereit."

# 2. Schlüssel und Passwort. Sie bleiben in Variablen. Der Schlüssel geht nur an Schlüsselprüfung, Prüfset und Server, das Passwort nur an den Server.
Abschnitt "Zugang"
$schluessel = GeheimGespeichert $SchluesselDatei "Ein API Schlüssel"
while ($true) {
    $neu = $false
    if (-not $schluessel) {
        Write-Host "Den API Schlüssel findest du in der Claude Konsole: https://platform.claude.com/"
        $schluessel = GeheimAbfragen "API Schlüssel einfügen (mit Rechtsklick oder Strg+V, er erscheint nur als Sternchen)" '^sk-ant-' "Das sieht nicht wie ein Claude API Schlüssel aus, er beginnt mit sk-ant. Bitte noch einmal."
        $neu = $true
    }
    Write-Host "Prüfe den Schlüssel ..."
    $env:ANTHROPIC_API_KEY = $schluessel
    & $venvPy startpruefung.py schluessel
    $ergebnis = $LASTEXITCODE
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    if ($ergebnis -eq 2) {
        Write-Host "Claude lehnt diesen Schlüssel ab. Bitte einen gültigen Schlüssel eingeben." -ForegroundColor Yellow
        Remove-Item -LiteralPath $SchluesselDatei -Force -ErrorAction SilentlyContinue
        $schluessel = ""
        continue
    }
    if ($ergebnis -eq 0) { Write-Host "Der Schlüssel ist gültig." }
    if ($neu) { GeheimMerken $SchluesselDatei $schluessel }
    break
}

$passwort = GeheimGespeichert $PasswortDatei "Ein Passwort für die SeydaAI Seite"
if ($passwort) {
    Write-Host "Im Browser später: Benutzername beliebig, Passwort wie gespeichert. Vergessen? Dann beim nächsten Start n wählen und ein neues festlegen."
} else {
    $passwort = GeheimAbfragen "Passwort für die SeydaAI Seite festlegen (frei wählbar, mindestens 8 Zeichen)" '^.{8,}$' "Bitte mindestens 8 Zeichen."
    GeheimMerken $PasswortDatei $passwort
    Write-Host "Im Browser später: Benutzername beliebig, Passwort wie gerade festgelegt."
}

# 3. Quellen einlesen
Abschnitt "Quellen"
$stand = & $venvPy startpruefung.py quellen
if ($LASTEXITCODE -ne 0) { Stopp "Die Datenbank ließ sich nicht öffnen. Die Meldung steht oben." }
if ($stand) {
    Write-Host "Bereits eingelesen:"
    $stand | ForEach-Object { Write-Host "  $_" }
    Write-Host "Seiten, die schon nach den aktuellen Regeln gespeichert sind, werden übersprungen. Ein neuer Lauf holt nur, was noch fehlt."
    $wahl = Read-Host "Einlesen (fortsetzen)? d = nur Diyanet, a = alle Quellen, Enter = nein, gleich starten"
} else {
    Write-Host "Noch keine Quellen eingelesen. Das Skript liest langsam und mit Pause, damit die Seiten nicht belastet werden."
    $wahl = Read-Host "Jetzt einlesen? d = nur Diyanet (bis etwa 75 Minuten), a = alle Quellen (bis etwa 2 Stunden), n = nicht jetzt"
}
if ($wahl -match '^[dDaA]') {
    Write-Host "Abbrechen mit Strg+C. Bereits eingelesene Seiten bleiben gespeichert; beim nächsten Start geht es dort weiter."
    if ($wahl -match '^[dD]') { & $venvPy einlesen.py diyanet } else { & $venvPy einlesen.py }
    if ($LASTEXITCODE -ne 0) { Write-Host "Beim Einlesen gab es einen Fehler, die Meldung steht oben. Der Server startet trotzdem." -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "Jetzt eingelesen:"
    & $venvPy startpruefung.py quellen | ForEach-Object { Write-Host "  $_" }
}

# 4. Prüfset (freiwillig): 20 Grundfragen und eine Rückfrage, Bericht als Datei
Abschnitt "Prüfset"
$wahl = Read-Host "Prüfset mit 20 Grundfragen laufen lassen? p = ja (dauert einige Minuten, kostet geschätzt 40 US Cent bis 1 US Dollar, zählt 21 Fragen zum Tageslimit), Enter = nein"
if ($wahl -match '^[pP]') {
    $env:ANTHROPIC_API_KEY = $schluessel
    & $venvPy pruefset.py
    $ergebnis = $LASTEXITCODE
    Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
    if ($ergebnis -ne 0) { Write-Host "Das Prüfset lief nicht durch, die Meldung steht oben. Der Server startet trotzdem." -ForegroundColor Yellow }
}

# 5. Server starten und Browser öffnen. Nur der Server bekommt Schlüssel und Passwort.
Abschnitt "SeydaAI starten"
if (PortBelegt $Port) {
    Stopp "Unter $Adresse antwortet inzwischen ein anderes Programm. Bitte das andere Fenster schließen und neu starten."
}
$env:ANTHROPIC_API_KEY = $schluessel
$env:SEYDA_PASSWORT = $passwort
$server = Start-Process -FilePath $venvPy -ArgumentList "server.py" -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru
Remove-Item Env:ANTHROPIC_API_KEY, Env:SEYDA_PASSWORT -ErrorAction SilentlyContinue
$bereit = $false
for ($i = 0; $i -lt 40 -and -not $server.HasExited; $i++) {
    Start-Sleep -Milliseconds 500
    if (PortBelegt $Port) { $bereit = $true; break }
}
if ($server.HasExited) {
    Stopp "SeydaAI hat sich gleich wieder beendet, die Meldung steht oben."
}
Write-Host ""
if ($bereit) {
    Start-Process $Adresse
    Write-Host "SeydaAI läuft unter $Adresse" -ForegroundColor Green
} else {
    Write-Host "SeydaAI startet langsamer als erwartet. Bitte $Adresse gleich selbst im Browser öffnen." -ForegroundColor Yellow
}
Write-Host "Zum Beenden dieses Fenster schließen (oder Strg+C drücken und danach J wählen)."
$server.WaitForExit()
Write-Host "SeydaAI wurde beendet."
