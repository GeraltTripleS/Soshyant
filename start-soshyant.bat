@echo off
title Soshyant Assistant (local voice chat, port 8091)
cd /d "%~dp0"
echo Starting Soshyant Assistant...
echo Open http://127.0.0.1:8091 in your browser.
echo Close this window (or press Ctrl+C) to stop.
echo.
.venv\Scripts\python.exe bonsai_web.py
pause
