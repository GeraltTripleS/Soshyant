"""Watch a document folder and keep the RAG index in sync automatically.

Usage:  .venv/Scripts/python.exe rag_watch.py "C:\\path\\to\\docs" [interval_s]
Polls the folder hash tree every `interval_s` seconds (default 30) and runs
an incremental sync whenever a file is added, changed, or deleted.
"""
import os
import sys
import time

import rag_ingest
import rag_store


def snapshot(folder: str) -> dict:
    now = {}
    for rel, path in rag_ingest.walk_files(folder):
        try:
            now[rel] = rag_ingest.file_md5(path)
        except Exception:
            pass
    return now


def main():
    if len(sys.argv) >= 2:
        folder = os.path.abspath(sys.argv[1])
    else:
        saved = os.path.join(rag_store.DB_DIR, "folder.txt")
        if not os.path.isfile(saved):
            sys.exit("Select and sync a document folder in Soshyant first, or pass a folder path.")
        with open(saved, encoding="utf-8") as f:
            folder = f.read().strip()
    if not os.path.isdir(folder):
        sys.exit("The document folder is unavailable. Select it again in Soshyant.")
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    print(f"[watch] {folder}")
    print(f"[watch] polling every {interval}s — Ctrl+C to stop")
    last = rag_store.load_files()   # compare against what's indexed
    while True:
        try:
            now = snapshot(folder)
            if now != last:
                added = sorted(r for r in now if r not in last)
                removed = sorted(r for r in last if r not in now)
                changed = sorted(r for r in now if r in last and
                                 now[r] != last[r])
                print(f"[watch] {time.strftime('%H:%M:%S')} change detected: "
                      f"+{len(added)} ~{len(changed)} -{len(removed)}")
                rag_ingest.sync(folder)
                # Empty/unsupported files are not indexed, but shouldn't cause
                # an endless re-sync when nothing in the folder has changed.
                last = now
            time.sleep(interval)
        except KeyboardInterrupt:
            print("[watch] stopped")
            return
        except Exception as e:
            print(f"[watch] error ({e.__class__.__name__}: {e}) — retrying")
            time.sleep(interval)


if __name__ == "__main__":
    main()
