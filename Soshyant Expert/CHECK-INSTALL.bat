@echo off
cd /d "%~dp0"
runtime\python.exe manage.py check --full
pause
