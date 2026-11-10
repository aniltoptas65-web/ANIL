@echo off
rem SeydaAI auf Cloudflare einrichten und verwalten (Zugaenge, neues Hochladen, neue Versionen).
rem Die eigentliche Arbeit macht cloudflare\einrichten.ps1.
if not exist "%~dp0cloudflare\einrichten.ps1" (
  echo Bitte die ZIP Datei zuerst ganz entpacken: Rechtsklick, Alle extrahieren. Dann im entpackten Ordner noch einmal doppelklicken.
  echo.
  pause
  exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0cloudflare\einrichten.ps1"
echo.
pause
