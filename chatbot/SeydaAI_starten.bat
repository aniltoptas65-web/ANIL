@echo off
rem SeydaAI starten: beim ersten Mal wird alles eingerichtet, danach startet nur der Server.
rem Die eigentliche Arbeit macht starten.ps1 im selben Ordner.
if not exist "%~dp0starten.ps1" (
  echo Bitte die ZIP Datei zuerst ganz entpacken: Rechtsklick, Alle extrahieren. Dann im entpackten Ordner noch einmal doppelklicken.
  echo.
  pause
  exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0starten.ps1"
echo.
pause
