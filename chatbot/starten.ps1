# SeydaAI starten (Windows). Wird von SeydaAI_starten.bat aufgerufen.
#
# Beim ersten Mal: Python prüfen oder installieren, Pakete einrichten, API Schlüssel und Passwort abfragen,
# Quellen einlesen. Danach: Server starten und Browser öffnen.
#
# Der API Schlüssel landet nie in diesem Ordner. Auf Wunsch wird er mit dem Windows eigenen Schutz (DPAPI)
# verschlüsselt unter %LOCALAPPDATA%\SeydaAI gespeichert; nur dein Windows Benutzerkonto kann ihn wieder lesen.
# Als Umgebungsvariable gilt er nur in diesem Fenster und verschwindet, wenn es geschlossen wird.

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot
# Python schreibt UTF 8, damit türkische Zeichen wie İ und ş richtig ankommen
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Port = 8000
$Adresse = "http://127.0.0.1:$Port"

function Stopp([string]$text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Red
    exit 1
}

function Abschnitt([string]$text) {
    Write-Host ""
    Write-Host "== $text ==" -ForegroundColor Cyan
}

# Sucht ein Python ab Version 3.10. Gibt den Befehl als Liste zurück (zum Beispiel py -3), sonst $null.
function PythonFinden {
    $kandidaten = New-Object System.Collections.ArrayList
    [void]$kandidaten.Add(@("py", "-3"))
    [void]$kandidaten.Add(@("python"))
    $muster = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python3*\python.exe"),
        (Join-Path $env:ProgramFiles "Python3*\python.exe")
    )
    foreach ($m in $muster) {
        Get-ChildItem -Path $m -ErrorAction SilentlyContinue | ForEach-Object { [void]$kandidaten.Add(@($_.FullName)) }
    }
    foreach ($k in $kandidaten) {
        $befehl = $k[0]
        $rest = @($k | Select-Object -Skip 1)
        try {
            $ausgabe = & $befehl @rest -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)" 2>$null
            if ($LASTEXITCODE -eq 0 -and "$ausgabe".Trim() -eq "1") { return ,$k }
        } catch { }
    }
    return $null
}

# Liest eine geheime Angabe: gespeichert und verschlüsselt, oder neu abgefragt.
function GeheimHolen([string]$datei, [string]$frage, [string]$pruefMuster, [string]$pruefHinweis) {
    if (Test-Path -LiteralPath $datei) {
        try {
            $sicher = Get-Content -LiteralPath $datei -ErrorAction Stop | ConvertTo-SecureString -ErrorAction Stop
            $klar = (New-Object System.Net.NetworkCredential("", $sicher)).Password
            if ($klar) { return $klar }
        } catch {
            Write-Host "Die gespeicherte Angabe ließ sich nicht lesen, bitte neu eingeben."
        }
    }
    while ($true) {
        $sicher = Read-Host $frage -AsSecureString
        $klar = (New-Object System.Net.NetworkCredential("", $sicher)).Password
        $klar = $klar.Trim()
        if (-not $klar) { Write-Host "Die Eingabe war leer."; continue }
        if ($pruefMuster -and ($klar -notmatch $pruefMuster)) { Write-Host $pruefHinweis; continue }
        break
    }
    $merken = Read-Host "Auf diesem Rechner verschlüsselt merken, damit du es nicht jedes Mal eingeben musst? (j/n)"
    if ($merken -match '^[jJyY]') {
        $ordner = Split-Path -Parent $datei
        New-Item -ItemType Directory -Force -Path $ordner | Out-Null
        ConvertTo-SecureString $klar -AsPlainText -Force | ConvertFrom-SecureString | Set-Content -LiteralPath $datei
        Write-Host "Gespeichert. Zum Ändern die Datei $datei löschen."
    }
    return $klar
}

Write-Host "SeydaAI, interner Test" -ForegroundColor Yellow

# 1. Python Umgebung
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
    Abschnitt "Python einrichten (nur beim ersten Mal)"
    $py = PythonFinden
    if (-not $py) {
        Write-Host "Python 3.10 oder neuer wurde nicht gefunden."
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            $antwort = Read-Host "Soll ich Python 3.12 jetzt über winget installieren? (j/n)"
            if ($antwort -match '^[jJyY]') {
                winget install --exact --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
                $py = PythonFinden
            }
        }
        if (-not $py) {
            Stopp "Bitte Python von https://www.python.org/downloads/ installieren, dabei das Häkchen 'Add python.exe to PATH' setzen, und danach SeydaAI_starten.bat noch einmal doppelklicken."
        }
    }
    $befehl = $py[0]
    $rest = @($py | Select-Object -Skip 1)
    & $befehl @rest -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) { Stopp "Die Python Umgebung ließ sich nicht anlegen. Die Meldung steht oben." }
}

Abschnitt "Pakete prüfen"
& $venvPy -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Stopp "Die Pakete ließen sich nicht installieren. Besteht eine Internetverbindung? Die Meldung steht oben." }
Write-Host "Pakete sind bereit."

# 2. Schlüssel und Passwort, nur für dieses Fenster
Abschnitt "Zugang"
$geheim = Join-Path $env:LOCALAPPDATA "SeydaAI"
$frage = "API Schlüssel aus der Claude Konsole einfügen (Rechtsklick fügt ein, die Eingabe bleibt unsichtbar)"
$hinweis = "Das sieht nicht wie ein Claude API Schlüssel aus, er beginnt mit sk-ant. Bitte noch einmal."
$env:ANTHROPIC_API_KEY = GeheimHolen (Join-Path $geheim "api_schluessel.txt") $frage '^sk-ant-' $hinweis
$frage = "Passwort für die SeydaAI Seite festlegen (frei wählbar, mindestens 8 Zeichen)"
$env:SEYDA_PASSWORT = GeheimHolen (Join-Path $geheim "seiten_passwort.txt") $frage '^.{8,}$' "Bitte mindestens 8 Zeichen."
Write-Host "Im Browser später: Benutzername beliebig, Passwort wie gerade festgelegt."

# 3. Quellen einlesen
Abschnitt "Quellen"
$stand = & $venvPy -c "from datenbank import verbinden; c = verbinden(); [print(f'{q}: {n} Seiten') for q, n in c.execute('select quelle, count(*) from seiten group by quelle')]"
if ($LASTEXITCODE -ne 0) { Stopp "Die Datenbank ließ sich nicht öffnen. Die Meldung steht oben." }
if ($stand) {
    Write-Host "Bereits eingelesen:"
    $stand | ForEach-Object { Write-Host "  $_" }
    $wahl = Read-Host "Neu einlesen? d = nur Diyanet, a = alle Quellen, Enter = nein, gleich starten"
} else {
    Write-Host "Noch keine Quellen eingelesen. Das Skript liest langsam und mit Pause, damit die Seiten nicht belastet werden."
    $wahl = Read-Host "Jetzt einlesen? d = nur Diyanet (etwa 10 Minuten), a = alle Quellen (etwa 30 Minuten), n = nicht jetzt"
}
if ($wahl -match '^[dD]') {
    & $venvPy einlesen.py diyanet
} elseif ($wahl -match '^[aA]') {
    & $venvPy einlesen.py
}
if ($wahl -match '^[dDaA]') {
    if ($LASTEXITCODE -ne 0) { Write-Host "Beim Einlesen gab es einen Fehler, die Meldung steht oben. Der Server startet trotzdem." -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "Jetzt eingelesen:"
    & $venvPy -c "from datenbank import verbinden; c = verbinden(); [print(f'  {q}: {n} Seiten') for q, n in c.execute('select quelle, count(*) from seiten group by quelle')]"
}

# 4. Server starten und Browser öffnen
Abschnitt "SeydaAI starten"
$server = Start-Process -FilePath $venvPy -ArgumentList "server.py" -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru
$bereit = $false
for ($i = 0; $i -lt 40 -and -not $server.HasExited; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient("127.0.0.1", $Port)
        $tcp.Close()
        $bereit = $true
        break
    } catch { }
}
Start-Sleep -Seconds 1
if ($server.HasExited) {
    Stopp "SeydaAI hat sich gleich wieder beendet, die Meldung steht oben. Läuft SeydaAI vielleicht schon in einem anderen Fenster, oder belegt ein anderes Programm den Port $Port?"
}
if ($bereit) { Start-Process $Adresse }
Write-Host ""
Write-Host "SeydaAI läuft unter $Adresse" -ForegroundColor Green
Write-Host "Zum Beenden dieses Fenster schließen."
$server.WaitForExit()
Write-Host "SeydaAI wurde beendet."
