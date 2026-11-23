@echo off
cd /d "%~dp0"
runtime\python.exe tools\setup_speech.py
if errorlevel 1 echo Speech setup failed. Please keep this message for troubleshooting.
pause
