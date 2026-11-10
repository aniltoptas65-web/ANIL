# SeydaAI auf Cloudflare einrichten und verwalten (Windows). Wird von Cloudflare_einrichten.bat aufgerufen.
#
# Beim ersten Mal: Node.js prüfen oder installieren, wrangler (das Werkzeug von Cloudflare) einrichten,
# mit deinem eigenen Cloudflare Konto anmelden, Datenbank in der EU anlegen, Texte hochladen,
# SeydaAI unter ki.reyhani-europa.de veröffentlichen, API Schlüssel als Secret hinterlegen, ersten Zugang anlegen.
# Danach: ein Menü für Zugänge, neues Hochladen und neue Versionen.
#
# Die Anmeldung bei Cloudflare läuft über deinen Browser mit deinem Konto. Der API Schlüssel geht direkt an
# Cloudflare (als verschlüsseltes Secret des Workers). Er wird weder in einer Datei im Projektordner noch
# dauerhaft in Windows gespeichert.

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:WRANGLER_SEND_METRICS = "false"
$env:PYTHONUNBUFFERED = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Hauptordner = Split-Path -Parent $PSScriptRoot
$Adresse = "https://ki.reyhani-europa.de"
$Konfig = Join-Path $PSScriptRoot "wrangler.jsonc"
$Platzhalter = "noch-nicht-angelegt"
$Ablage = Join-Path $env:LOCALAPPDATA "SeydaAI"
$venvPy = Join-Path $Ablage "venv\Scripts\python.exe"
$SchluesselDatei = Join-Path $Ablage "api_schluessel.txt"
$WranglerJs = Join-Path $PSScriptRoot "node_modules\wrangler\bin\wrangler.js"
$Merker = Join-Path $PSScriptRoot "node_modules\.seyda_paketstand"
$MindestNode = [version]"22.12.0"
$script:Node = $null

function Stopp([string]$text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Red
    exit 1
}

function Abschnitt([string]$text) {
    Write-Host ""
    Write-Host "== $text ==" -ForegroundColor Cyan
}

function Hinweis([string]$text) {
    Write-Host $text -ForegroundColor Yellow
}

function Klartext($sicher) {
    return (New-Object System.Net.NetworkCredential("", $sicher)).Password
}

# Schreibt Text als UTF 8 ohne BOM (wrangler liest Dateien mit BOM nicht)
function OhneBomSchreiben([string]$pfad, [string]$text) {
    [System.IO.File]::WriteAllText($pfad, $text, (New-Object System.Text.UTF8Encoding $false))
}

# ---------- Node.js und wrangler ----------

function NodeVersion([string]$pfad) {
    try {
        $v = & $pfad -p "process.versions.node" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return [version]("$v".Trim()) }
    } catch { }
    return $null
}

function NodeFinden {
    $kandidaten = New-Object System.Collections.ArrayList
    $befehl = Get-Command node -ErrorAction SilentlyContinue
    if ($befehl) { [void]$kandidaten.Add($befehl.Source) }
    foreach ($ort in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($ort) { [void]$kandidaten.Add((Join-Path $ort "nodejs\node.exe")) }
    }
    foreach ($k in $kandidaten) {
        if (-not (Test-Path -LiteralPath $k)) { continue }
        $v = NodeVersion $k
        if ($v -and $v -ge $MindestNode) { return $k }
    }
    return $null
}

function PfadNeuLaden {
    $maschine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $benutzer = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$maschine;$benutzer"
}

function NodeBereitstellen {
    $script:Node = NodeFinden
    if ($script:Node) { return }
    Abschnitt "Node.js einrichten (nur beim ersten Mal)"
    Write-Host "Für die Werkzeuge von Cloudflare braucht es Node.js ab Version $MindestNode."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $antwort = Read-Host "Soll ich Node.js (LTS) jetzt über winget installieren? Windows fragt dabei eventuell nach deiner Erlaubnis. (j/n)"
        if ($antwort -match '^[jJyY]') {
            winget install --exact --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
            PfadNeuLaden
            $script:Node = NodeFinden
        }
    }
    if (-not $script:Node) {
        Stopp "Bitte Node.js (Version LTS) von https://nodejs.org/ installieren und danach Cloudflare_einrichten.bat noch einmal doppelklicken."
    }
}

# Die geprüfte Node.js Version vorn in den Suchpfad dieses Fensters, damit cloud.py und npm dieselbe verwenden
function NodeVorn {
    $ordner = Split-Path -Parent $script:Node
    $env:Path = "$ordner;$env:Path"
}

function PaketeBereitstellen {
    $stand = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot "package-lock.json")).Hash
    if ((Test-Path -LiteralPath $WranglerJs) -and (Test-Path -LiteralPath $Merker) -and ((Get-Content -LiteralPath $Merker -Raw).Trim() -eq $stand)) {
        return
    }
    Abschnitt "Werkzeuge von Cloudflare installieren (beim ersten Mal ein bis zwei Minuten)"
    $ordner = Split-Path -Parent $script:Node
    $npmCli = Join-Path $ordner "node_modules\npm\bin\npm-cli.js"
    if (-not (Test-Path -LiteralPath $npmCli)) { Stopp "npm wurde neben Node.js nicht gefunden ($npmCli). Bitte Node.js von https://nodejs.org/ neu installieren." }
    & $script:Node $npmCli ci --no-audit --no-fund --loglevel=error
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $WranglerJs)) {
        Stopp "Die Installation hat nicht geklappt. Besteht eine Internetverbindung? Die Meldung steht oben."
    }
    OhneBomSchreiben $Merker $stand
    Write-Host "Fertig."
}

# wrangler mit erfasster Ausgabe (für Abfragen wie whoami)
function Wrangler {
    & $script:Node $WranglerJs @args
}

# wrangler direkt im Fenster, damit Rückfragen von wrangler (etwa zu vorhandenen DNS Einträgen) erscheinen
# und nicht automatisch beantwortet werden
function WranglerImFenster([string]$argumente) {
    $p = Start-Process -FilePath $script:Node -ArgumentList "`"$WranglerJs`" $argumente" -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru
    $null = $p.Handle  # sonst liefert Windows PowerShell den Rückgabewert manchmal nicht
    $p.WaitForExit()
    return $p.ExitCode
}

# ---------- Cloudflare Anmeldung ----------

function AnmeldungLesen {
    $ausgabe = (Wrangler whoami --json 2>$null | Out-String)
    if ($LASTEXITCODE -ne 0) { return $null }
    $start = $ausgabe.IndexOf("{")
    if ($start -lt 0) { return $null }
    try { return ($ausgabe.Substring($start) | ConvertFrom-Json) } catch { return $null }
}

function KontoEintragen($konten) {
    $text = [System.IO.File]::ReadAllText($Konfig)
    if ($text -match '"account_id"') { return }
    Write-Host "Mit dieser Anmeldung sind mehrere Cloudflare Konten verbunden:"
    for ($i = 0; $i -lt $konten.Count; $i++) { Write-Host "  $($i + 1) = $($konten[$i].name)" }
    while ($true) {
        $wahl = Read-Host "In welchem Konto liegt reyhani-europa.de? Nummer eingeben"
        $n = 0
        if ([int]::TryParse($wahl, [ref]$n) -and $n -ge 1 -and $n -le $konten.Count) { break }
    }
    $id = "$($konten[$n - 1].id)"
    if ($id -notmatch '^[0-9a-fA-F]{32}$') { Stopp "Die Kontonummer sieht ungewöhnlich aus. Bitte in der Cloudflare Übersicht prüfen." }
    $neu = $text -replace '("name":\s*"seydaai",)', "`$1`n  `"account_id`": `"$id`","
    OhneBomSchreiben $Konfig $neu
    Write-Host "Konto $($konten[$n - 1].name) eingetragen."
}

function Anmelden {
    $wer = AnmeldungLesen
    if (-not $wer) {
        Abschnitt "Bei Cloudflare anmelden"
        Write-Host "Gleich öffnet sich dein Browser mit der Cloudflare Anmeldung. Dort mit dem Konto anmelden, in dem"
        Write-Host "reyhani-europa.de liegt, und den Zugriff für wrangler erlauben. Danach geht es hier weiter."
        Read-Host "Enter drücken, um den Browser zu öffnen" | Out-Null
        [void](WranglerImFenster "login")
        $wer = AnmeldungLesen
        if (-not $wer) { Stopp "Die Anmeldung bei Cloudflare hat nicht geklappt. Bitte noch einmal starten." }
    }
    $konten = @($wer.accounts)
    if ($konten.Count -gt 1) { KontoEintragen $konten }
    if ($konten.Count -eq 1) { Write-Host "Angemeldet bei Cloudflare, Konto: $($konten[0].name)" }
}

# ---------- Python für cloud.py ----------

# Ruft cloud.py auf. Die Ausgabe geht direkt ins Fenster, zurück kommt nur der Rückgabewert.
function Cloud {
    & $venvPy (Join-Path $PSScriptRoot "cloud.py") @args | Out-Host
    return $LASTEXITCODE
}

function PythonPruefen {
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Stopp "Die Python Umgebung von SeydaAI fehlt. Bitte zuerst SeydaAI_starten.bat einmal ausführen (richtet Python ein und liest die Quellen ein), danach Cloudflare_einrichten.bat."
    }
}

# Die eingelesenen Texte liegen in seyda.db im Ordner SeydaAI. Wurde die neue ZIP in einen neuen Ordner entpackt,
# liegt seyda.db noch im alten Ordner. Dann kann man sie hier auswählen und sie wird hierher kopiert.
function DatenbankDateiPruefen {
    $ziel = Join-Path $Hauptordner "seyda.db"
    if (Test-Path -LiteralPath $ziel) { return $true }
    Hinweis "Im Ordner $Hauptordner liegt noch keine seyda.db mit den eingelesenen Texten."
    Write-Host "Hast du die Quellen schon in einem anderen SeydaAI Ordner eingelesen, zum Beispiel aus einer älteren ZIP?"
    $wahl = Read-Host "a = dort die Datei seyda.db auswählen und hierher kopieren, Enter = überspringen"
    if ($wahl -notmatch '^[aA]') {
        Write-Host "Übersprungen. Später: SeydaAI_starten.bat einlesen lassen, dann hier im Menü Texte hochladen."
        return $false
    }
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = "Die alte seyda.db auswählen"
        $dialog.Filter = "SeydaAI Datenbank (seyda.db)|seyda.db"
        $dialog.InitialDirectory = [Environment]::GetFolderPath("UserProfile")
        if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { Write-Host "Keine Datei gewählt."; return $false }
        Copy-Item -LiteralPath $dialog.FileName -Destination $ziel
        Write-Host "seyda.db kopiert."
        return $true
    } catch {
        Write-Host "Das Auswahlfenster ging nicht auf. Bitte seyda.db von Hand in den Ordner $Hauptordner kopieren und noch einmal starten."
        return $false
    }
}

# ---------- Einzelne Schritte ----------

function DatenbankEinrichten {
    Abschnitt "Datenbank in der EU"
    if ((Cloud datenbank) -ne 0) { Stopp "Die Datenbank ließ sich nicht einrichten. Die Meldung steht oben." }
}

function TexteHochladen([bool]$fragen) {
    Abschnitt "Texte hochladen"
    if ($fragen) {
        $stand = (& $venvPy (Join-Path $PSScriptRoot "cloud.py") stand 2>$null | Out-String)
        if ($stand -match "Zuletzt hochgeladen") {
            Write-Host $stand.Trim()
            $wahl = Read-Host "Die Texte sind schon in Cloudflare. Neu hochladen? (j = ja, Enter = nein)"
            if ($wahl -notmatch '^[jJyY]') { return }
        }
    }
    if (-not (DatenbankDateiPruefen)) { return }
    Write-Host "Das dauert einige Minuten."
    if ((Cloud hochladen) -ne 0) { Hinweis "Das Hochladen hat nicht geklappt, die Meldung steht oben. Später im Menü noch einmal versuchen." }
}

# Gibt $true zurück, wenn die neue Version unter der Adresse läuft
function Veroeffentlichen {
    Abschnitt "SeydaAI unter $Adresse veröffentlichen"
    Write-Host "Falls wrangler auf Englisch fragt, ob vorhandene Einträge für ki.reyhani-europa.de ersetzt werden sollen"
    Write-Host "(""Update them to point to this script instead?""): nur mit y antworten, wenn diese Adresse für nichts anderes"
    Write-Host "genutzt wird. Die Vereinsseite reyhani-europa.de selbst ist davon nicht betroffen."
    if ((WranglerImFenster "deploy") -ne 0) {
        Hinweis ("Das Veröffentlichen hat nicht geklappt, die Meldung steht oben. Häufige Gründe: reyhani-europa.de liegt in einem " +
            "anderen Cloudflare Konto, oder für ki.reyhani-europa.de gibt es schon einen DNS Eintrag (dann in Cloudflare unter " +
            "DNS den Eintrag ki löschen und noch einmal versuchen). Mehr dazu in README.md unter Cloudflare.")
        return $false
    }
    return $true
}

function SchluesselVorhanden {
    $liste = (Wrangler secret list 2>$null | Out-String)
    return ($LASTEXITCODE -eq 0 -and $liste -match '"ANTHROPIC_API_KEY"')
}

function SchluesselHinterlegen([bool]$nurWennFehlt) {
    Abschnitt "API Schlüssel in Cloudflare hinterlegen"
    if ($nurWennFehlt -and (SchluesselVorhanden)) {
        $wahl = Read-Host "In Cloudflare ist schon ein API Schlüssel hinterlegt. Enter = behalten, n = neuen hinterlegen"
        if ($wahl -notmatch '^[nN]') { return }
    }
    $schluessel = ""
    if (Test-Path -LiteralPath $SchluesselDatei) {
        $wahl = Read-Host "Den Schlüssel verwenden, den SeydaAI_starten auf diesem Rechner gespeichert hat? (Enter = ja, n = anderen eingeben)"
        if ($wahl -notmatch '^[nN]') {
            try {
                $schluessel = Klartext (Get-Content -LiteralPath $SchluesselDatei -ErrorAction Stop | ConvertTo-SecureString -ErrorAction Stop)
            } catch {
                Write-Host "Der gespeicherte Schlüssel ließ sich nicht lesen. Bitte eingeben."
            }
        }
    }
    while ($true) {
        if (-not $schluessel) {
            Write-Host "Den API Schlüssel findest du in der Claude Konsole: https://platform.claude.com/"
            Write-Host "Tipp: Dort einen eigenen Schlüssel ""SeydaAI Cloudflare"" anlegen, dann lässt er sich getrennt sperren."
            $schluessel = (Klartext (Read-Host "API Schlüssel einfügen (Rechtsklick oder Strg+V, er erscheint nur als Sternchen)" -AsSecureString)).Trim()
        }
        if ($schluessel -notmatch '^sk-ant-[A-Za-z0-9_-]+$') {
            Write-Host "Das sieht nicht wie ein Claude API Schlüssel aus, er beginnt mit sk-ant. Bitte noch einmal."
            $schluessel = ""
            continue
        }
        Write-Host "Prüfe den Schlüssel ..."
        $env:ANTHROPIC_API_KEY = $schluessel
        & $venvPy (Join-Path $Hauptordner "startpruefung.py") schluessel
        $ergebnis = $LASTEXITCODE
        Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
        if ($ergebnis -eq 2) {
            Hinweis "Claude lehnt diesen Schlüssel ab. Bitte einen gültigen Schlüssel eingeben."
            $schluessel = ""
            continue
        }
        break
    }
    # Über die Eingabe (nicht als Argument), damit der Schlüssel nicht in der Prozessliste steht
    $schluessel | & $script:Node $WranglerJs secret put ANTHROPIC_API_KEY | Out-Host
    $ok = ($LASTEXITCODE -eq 0)
    $schluessel = $null
    if (-not $ok) { Stopp "Der Schlüssel ließ sich nicht in Cloudflare hinterlegen. Die Meldung steht oben." }
    Write-Host "Der Schlüssel ist in Cloudflare hinterlegt."
}

function ZugangAnlegen {
    Abschnitt "Zugang anlegen"
    Write-Host "Jede Person meldet sich auf der Seite mit Name und Zugangscode an."
    $name = (Read-Host "Name für den Zugang, zum Beispiel Ayse K (Enter = überspringen)").Trim()
    if (-not $name) { return }
    $limit = (Read-Host "Fragen pro Tag für diese Person (Enter = 10)").Trim()
    if (-not $limit) { $limit = "10" }
    [void](Cloud zugang neu $name $limit)
}

function ZugangAendern([string]$befehl) {
    $name = (Read-Host "Name des Zugangs (genau wie in der Liste)").Trim()
    if ($name) { [void](Cloud zugang $befehl $name) }
}

function MeldungenZeigen {
    Abschnitt "Gemeldete Antworten"
    # cloud.py merkt sich die Zeit der spätesten angezeigten Meldung; gelöscht wird nur bis dahin
    $datei = Join-Path ([System.IO.Path]::GetTempPath()) "seyda_meldungen_bis.txt"
    Remove-Item -LiteralPath $datei -ErrorAction SilentlyContinue
    if ((Cloud meldungen --merken $datei) -ne 0) { return }
    if (-not (Test-Path -LiteralPath $datei)) { return }
    $bis = (Get-Content -LiteralPath $datei -Raw).Trim()
    Remove-Item -LiteralPath $datei -ErrorAction SilentlyContinue
    $wahl = Read-Host "Diese Meldungen jetzt in Cloudflare löschen? (j = ja, Enter = behalten)"
    if ($wahl -match '^[jJyY]') { [void](Cloud meldungen loeschen $bis) }
}

function AllesEinrichten {
    Anmelden
    DatenbankEinrichten
    TexteHochladen $true
    if (-not (Veroeffentlichen)) { Stopp "Die Einrichtung ist hier stehen geblieben. Nach der Lösung Cloudflare_einrichten.bat noch einmal doppelklicken; die Einrichtung macht dann weiter, Fertiges wird übersprungen." }
    SchluesselHinterlegen $true
    $liste = (& $venvPy (Join-Path $PSScriptRoot "cloud.py") zugang liste 2>$null | Out-String)
    if ($liste -match "Noch keine Zugänge") { ZugangAnlegen }
    Write-Host ""
    Write-Host "SeydaAI ist eingerichtet: $Adresse" -ForegroundColor Green
    Write-Host "Beim allerersten Mal kann es einige Minuten dauern, bis Adresse und Zertifikat überall bekannt sind."
}

# ---------- Ablauf ----------

Write-Host "SeydaAI auf Cloudflare" -ForegroundColor Yellow
PythonPruefen
NodeBereitstellen
NodeVorn
PaketeBereitstellen

if ([System.IO.File]::ReadAllText($Konfig).Contains($Platzhalter)) {
    AllesEinrichten
} else {
    # Wurde die Einrichtung abgebrochen (zum Beispiel beim Veröffentlichen), fehlt der API Schlüssel noch
    Anmelden
    if (-not (SchluesselVorhanden)) {
        Hinweis "Die Einrichtung ist noch nicht fertig. Ich mache dort weiter."
        AllesEinrichten
    }
}

while ($true) {
    Write-Host ""
    Write-Host "Was möchtest du tun?" -ForegroundColor Cyan
    Write-Host "  1 = Zugang anlegen"
    Write-Host "  2 = Zugänge anzeigen"
    Write-Host "  3 = Zugang sperren (meldet die Person überall ab)"
    Write-Host "  4 = Zugang löschen"
    Write-Host "  5 = Gemeldete Antworten ansehen"
    Write-Host "  6 = Texte neu hochladen (nach neuem Einlesen mit SeydaAI_starten.bat)"
    Write-Host "  7 = Neue Version veröffentlichen"
    Write-Host "  8 = API Schlüssel in Cloudflare ändern"
    Write-Host "  9 = Fehlermeldungen live ansehen (Strg+C beendet das und dieses Fenster)"
    Write-Host "  10 = Alles einrichten oder prüfen"
    Write-Host "  Enter = Beenden"
    $wahl = (Read-Host "Nummer").Trim()
    switch ($wahl) {
        "1" { Anmelden; ZugangAnlegen }
        "2" { Anmelden; [void](Cloud zugang liste) }
        "3" { Anmelden; ZugangAendern "sperren" }
        "4" { Anmelden; ZugangAendern "loeschen" }
        "5" { Anmelden; MeldungenZeigen }
        "6" { Anmelden; TexteHochladen $false }
        "7" { Anmelden; [void](Veroeffentlichen) }
        "8" { Anmelden; SchluesselHinterlegen $false }
        "9" { Anmelden; [void](WranglerImFenster "tail --format pretty") }
        "10" { AllesEinrichten }
        "" { exit 0 }
        default { Write-Host "Bitte eine Nummer von 1 bis 10 eingeben." }
    }
}
