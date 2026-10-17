@echo off
cd /d "%~dp0"
title Soshyant Expert - Private Knowledge
if not exist "runtime\python.exe" (
  echo The independent runtime is missing. Read README.md for provisioning.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8095 in your browser.
echo On first launch, use the code in data\FIRST-ADMIN-CODE.txt.
echo Close this window or press Ctrl+C to stop.
runtime\python.exe start.py %*
pause
