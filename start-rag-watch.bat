@echo off
title RAG Watcher (auto-index document changes)
cd /d "%~dp0"
echo Watching C:\Users\asus\Desktop\Triton\Oreo — the knowledge base
echo re-syncs automatically when files are added, changed, or deleted.
echo Keep this window open while editing documents. Ctrl+C to stop.
echo.
.venv\Scripts\python.exe rag_watch.py "C:\Users\asus\Desktop\Triton\Oreo" 30
pause
