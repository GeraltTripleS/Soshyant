"""Local RAG store: chunk text, embed with fastembed, cosine search via numpy.

Storage is deliberately transparent — no database server:
  rag_db/chunks.jsonl    one chunk per line: {source, loc, text}
  rag_db/embeddings.npy  float32 matrix, row i matches chunks.jsonl line i
"""
import json
import os
import re

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(ROOT, "rag_db")
CHUNKS_PATH = os.path.join(DB_DIR, "chunks.jsonl")
VECTORS_PATH = os.path.join(DB_DIR, "embeddings.npy")
FILES_PATH = os.path.join(DB_DIR, "files.json")      # relpath -> content md5
CHUNK_DIR = os.path.join(DB_DIR, "chunks")           # per-file chunk json
VEC_DIR = os.path.join(DB_DIR, "vectors")            # per-file vector matrix
MODEL_NAME = "BAAI/bge-small-en-v1.5"
CHUNK_CHARS = 1200
OVERLAP_CHARS = 150

_model = None


def _embedder():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL_NAME)
    return _model


def embed(texts, progress=None):
    """fastembed returns L2-normalized vectors, so cosine = dot product.
    Batched; progress(done, total) fires per batch; prints stay for CLI use."""
    out = []
    B = 64
    for i in range(0, len(texts), B):
        batch = [t[:4000] for t in texts[i:i + B]]
        out.extend(_embedder().embed(batch))
        done = min(i + B, len(texts))
        if progress:
            progress(done, len(texts))
        if done % 256 < B or done == len(texts):
            print(f"  embedded {done}/{len(texts)}", flush=True)
    return np.array(out, dtype=np.float32)


def chunk_text(text: str, source: str, loc: str = "") -> list[dict]:
    """Split text into ~CHUNK_CHARS chunks (linear memory — never quadratic).

    Oversized paragraphs are pre-split on lines, and pathological single
    lines are hard-sliced, so no string operation can explode.
    """
    def split_big(p: str) -> list[str]:
        if len(p) <= CHUNK_CHARS:
            return [p]
        out, cur = [], ""
        for line in p.split("\n"):
            while len(line) > CHUNK_CHARS:      # pathological single line
                out.append(line[:CHUNK_CHARS])
                line = line[CHUNK_CHARS:]
            if len(cur) + len(line) > CHUNK_CHARS and cur:
                out.append(cur)
                cur = line
            else:
                cur = (cur + "\n" + line).strip()
        if cur:
            out.append(cur)
        return out

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    paras = [q for p in paras for q in split_big(p)]

    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) > CHUNK_CHARS and buf:
            chunks.append({"source": source, "loc": loc, "text": buf})
            buf = buf[-OVERLAP_CHARS:]
        buf = (buf + "\n\n" + p).strip()
    if buf:
        chunks.append({"source": source, "loc": loc, "text": buf})
    return [c for c in chunks if len(c["text"]) > 20]


def save(chunks: list[dict], vectors: np.ndarray):
    os.makedirs(DB_DIR, exist_ok=True)
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    np.save(VECTORS_PATH, vectors)


# ---------------- per-file store (incremental sync) ----------------

def load_files() -> dict:
    """-> {relpath: content_md5} for every indexed file."""
    if not os.path.exists(FILES_PATH):
        return {}
    with open(FILES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_files(files: dict):
    os.makedirs(DB_DIR, exist_ok=True)
    with open(FILES_PATH, "w", encoding="utf-8") as f:
        json.dump(files, f, ensure_ascii=False, indent=0)


def save_file(rel: str, h: str, chunks: list[dict], vectors: np.ndarray):
    """Store one file's chunks + vectors under its content hash."""
    os.makedirs(CHUNK_DIR, exist_ok=True)
    os.makedirs(VEC_DIR, exist_ok=True)
    key = h[:16]
    with open(os.path.join(CHUNK_DIR, key + ".json"), "w",
              encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False)
    np.save(os.path.join(VEC_DIR, key + ".npy"), vectors)
    files = load_files()
    files[rel] = h
    _save_files(files)


def remove_file(rel: str):
    """Drop a file from the index; artifacts removed only if no other
    indexed file shares the same content hash."""
    files = load_files()
    h = files.pop(rel, None)
    _save_files(files)
    if h and sum(1 for v in files.values() if v == h) == 0:
        key = h[:16]
        for p in (os.path.join(CHUNK_DIR, key + ".json"),
                  os.path.join(VEC_DIR, key + ".npy")):
            if os.path.exists(p):
                os.remove(p)


def rebuild_index() -> int:
    """Concatenate every indexed file into chunks.jsonl + embeddings.npy
    (the flat store that search reads). -> total chunk count."""
    files = load_files()
    chunks, vecs = [], []
    for rel, h in sorted(files.items()):
        key = h[:16]
        cj = os.path.join(CHUNK_DIR, key + ".json")
        vn = os.path.join(VEC_DIR, key + ".npy")
        if not (os.path.exists(cj) and os.path.exists(vn)):
            continue
        cs = json.load(open(cj, encoding="utf-8"))
        v = np.load(vn)
        if len(cs) != len(v):
            continue
        chunks.extend(cs)
        vecs.append(v)
    os.makedirs(DB_DIR, exist_ok=True)
    tmp = CHUNKS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    os.replace(tmp, CHUNKS_PATH)          # atomic: readers never see partial
    tmpv = VECTORS_PATH + ".tmp"
    with open(tmpv, "wb") as f:           # np.save appends .npy to paths —
        if vecs:                          # pass a file handle to avoid it
            np.save(f, np.concatenate(vecs).astype(np.float32))
        else:
            np.save(f, np.zeros((0, 384), dtype=np.float32))
    os.replace(tmpv, VECTORS_PATH)
    return len(chunks)


def load():
    """-> (chunks, vectors) or ([], None) when nothing is indexed yet."""
    if not (os.path.exists(CHUNKS_PATH) and os.path.exists(VECTORS_PATH)):
        return [], None
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = [json.loads(ln) for ln in f if ln.strip()]
    vecs = np.load(VECTORS_PATH)
    return chunks, vecs


def search(query: str, k: int = 6, min_score: float = 0.35):
    """Top-k chunks for a query, or [] when the store is empty/no match."""
    chunks, vecs = load()
    if not chunks:
        return []
    q = embed([query])[0]
    scores = vecs @ q
    order = np.argsort(-scores)[:k]
    out = []
    for i in order:
        if scores[i] < min_score:
            continue
        c = dict(chunks[i])
        c["score"] = float(scores[i])
        out.append(c)
    return out


def stats() -> dict:
    chunks, vecs = load()
    return {"chunks": len(chunks),
            "files": len({c["source"] for c in chunks}) if chunks else 0,
            "indexed": vecs is not None}
