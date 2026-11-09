@echo off
rem SeydaAI starten: beim ersten Mal wird alles eingerichtet, danach startet nur der Server.
rem Die eigentliche Arbeit macht starten.ps1 im selben Ordner.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0starten.ps1"
echo.
pause
