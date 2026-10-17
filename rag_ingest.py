"""Ingest / incrementally sync a folder of documents into the RAG store.

Usage:  .venv/Scripts/python.exe rag_ingest.py "C:\\path\\to\\docs"
Reads .txt .md .pdf .docx .html .xlsx .htm — chunks, embeds, saves rag_db/.
Incremental: unchanged files are skipped (content-hash comparison), changed
files are re-embedded, deleted files drop out of the index.
"""
import hashlib
import os
import sys
import re
import html as htmllib
import json
import time

import rag_store

SKIP_DIRS = {"node_modules", ".git", ".venv", "__pycache__", "dist", "build",
             "powerpass-figma-designer"}
EXTS = (".txt", ".md", ".pdf", ".docx", ".html", ".htm", ".xlsx")


def walk_files(folder: str):
    """-> [(relpath, abspath)] for every ingestable file, vendor dirs skipped."""
    def fail(error):
        raise error
    for root, dirs, files in os.walk(folder, onerror=fail):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.lower().endswith(EXTS):
                path = os.path.join(root, name)
                yield os.path.relpath(path, folder), path


def file_md5(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract(path: str) -> list[tuple[str, str]]:
    """-> [(text, loc), ...] where loc labels the piece (page/sheet etc.)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        with open(path, encoding="utf-8", errors="replace") as f:
            return [(f.read(), "")]
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        return [(page.extract_text() or "", f"p.{i + 1}")
                for i, page in enumerate(reader.pages)]
    if ext == ".docx":
        import docx2txt
        return [(docx2txt.process(path), "")]
    if ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(v) for v in row if v is not None and
                         str(v).strip()]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                out.append(("\n".join(rows), ws.title))
        wb.close()
        return out
    if ext in (".html", ".htm"):
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
        text = htmllib.unescape(re.sub(r"<[^>]+>", "\n", raw))
        return [(re.sub(r"\n{3,}", "\n\n", text), "")]
    return []


def process_file(abs_path: str, rel: str, embed_progress=None):
    """Extract + chunk + embed one file -> (chunks, vectors) or None."""
    got = extract(abs_path)
    if not got:
        return None
    chunks = []
    for text, loc in got:
        chunks += rag_store.chunk_text(text, rel, loc)
    if not chunks:
        return None
    vecs = rag_store.embed([c["text"] for c in chunks], progress=embed_progress)
    return chunks, vecs


def sync(folder: str, progress=None):
    with rag_store.sync_lock():
        return _sync(folder, progress)


def _sync(folder: str, progress=None):
    """Incremental sync with optional progress(dict) reporting.

    Phases: scanning -> indexing (files_done/files_total, current file,
    chunks embedded) -> saving -> done.
    """
    def report(**kw):
        if progress:
            progress(kw)

    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise ValueError("Document folder does not exist or is unavailable.")
    report(phase="scanning")
    old = rag_store.load_files()
    now = {}
    failures = []
    for rel, path in walk_files(folder):
        try:
            now[rel] = file_md5(path)
        except Exception as e:
            print(f"  SKIP {rel}: {e.__class__.__name__}: {e}")
            failures.append({"source": rel, "status": "failed", "detail": str(e)})
    removed = sorted(r for r in old if r not in now)
    touched = sorted(r for r in now if force_or_new(old, now, r))
    print(f"[sync] {len(now)} ingestable files | "
          f"{len(touched)} new/changed, {len(removed)} removed, "
          f"{len(now) - len(touched)} unchanged")
    report(phase="indexing", files_done=0, files_total=len(touched),
           current="")

    empty = []
    for i, rel in enumerate(touched):
        report(current=rel, files_done=i)
        try:
            if rag_store.reuse_file(rel, now[rel]):
                print(f"  DEDUPE {rel} (identical content already indexed)")
                continue
            res = process_file(os.path.join(folder, rel), rel,
                               embed_progress=lambda d, t: report(
                                   current=rel, files_done=i,
                                   files_total=len(touched),
                                   chunks_done=d, chunks_total=t))
        except Exception as e:
            print(f"  SKIP {rel}: {e.__class__.__name__}: {e}")
            failures.append({"source": rel, "status": "failed", "detail": str(e)})
            rag_store.remove_file(rel)
            continue
        if res is None:
            print(f"  EMPTY {rel}")
            rag_store.remove_file(rel)
            empty.append({"source": rel, "status": "empty", "detail": "No readable text. Scanned PDFs need OCR."})
            continue
        chunks, vecs = res
        rag_store.save_file(rel, now[rel], chunks, vecs)
        print(f"  INDEXED {rel} ({len(chunks)} chunks)", flush=True)
    for rel in removed:
        rag_store.remove_file(rel)
        print(f"  REMOVED {rel}")
    report(phase="saving")
    total = rag_store.rebuild_index()
    result = {"updated_at": time.time(), "folder": folder,
              "issues": failures + empty}
    with open(rag_store.REPORT_PATH + ".tmp", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    os.replace(rag_store.REPORT_PATH + ".tmp", rag_store.REPORT_PATH)
    report(phase="done", files_done=len(touched))
    print(f"[sync] DONE: {total} chunks indexed "
          f"({len(touched)} files re-embedded, {len(removed)} removed)")
    return result


def force_or_new(old: dict, now: dict, rel: str) -> bool:
    return rel not in old or old[rel] != now[rel]


def main(folder: str):
    sync(folder)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('usage: rag_ingest.py "folder with documents"')
    main(sys.argv[1])
