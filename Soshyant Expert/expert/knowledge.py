"""Local document extraction, transactional publication and hybrid retrieval."""
from collections import Counter
import hashlib
import html
from html.parser import HTMLParser
import io
import json
import math
from pathlib import Path
import re
import threading
import time
import unicodedata
import uuid
import zipfile
import xml.etree.ElementTree as ET

from .ocr import MIN_TEXT_CHARS, LocalOCR, image_page_count, image_pages, pdf_page_images


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".xlsx", ".html", ".htm"} | IMAGE_EXTENSIONS
STOP = set("the a an and or of to for in on is are was were be with this that what how "
           "does do can could would should please tell me about my your it its "
           "از به در و یا که این آن را با برای یک چه چگونه است هست می من شما".split())


def normalize(text):
    return unicodedata.normalize("NFKC", text).lower().translate(str.maketrans("يىك", "ییک")).replace("\u200c", " ")


def tokens(text):
    return [word for word in re.findall(r"[^\W_]+(?:-[^\W_]+)*", normalize(text), re.UNICODE)
            if word not in STOP and len(word) > 1]


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def check_zip(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if len(archive.infolist()) > 10000 or sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError("The document expands beyond the safe extraction limit.")


def extract(filename, body, ocr=None, progress=lambda value: None, canceled=lambda: False, report=None):
    """Return (text, location) parts. With a usable `ocr`, scanned PDF pages and image files are
    read with English OCR; `report` (a dict) then receives scanned/OCR page counts and skipped pages."""
    extension = Path(filename).suffix.lower()
    report = {} if report is None else report
    if extension not in EXTENSIONS:
        raise ValueError("Unsupported document type.")
    if extension in IMAGE_EXTENSIONS:
        if ocr is None:
            raise ValueError("Images are read with English OCR. Turn on OCR in Documents and make sure its model files are installed.")
        count = image_page_count(body)
        report["scanned"] = count
        texts, skipped = ocr.read_pages(image_pages(body, ocr.settings["ocr_max_side"], ocr.settings["ocr_max_pages"]),
                                        count, progress, canceled)
        report.update(ocr_pages=len(texts), **skipped)
        return [(text, f"page {number} (OCR)") for number, text in sorted(texts.items())]
    if extension in (".txt", ".md"):
        return [(body.decode("utf-8-sig", errors="replace"), "text")]
    if extension in (".html", ".htm"):
        parser = PlainHTML()
        parser.feed(body.decode("utf-8-sig", errors="replace"))
        return [(html.unescape("".join(parser.parts)), "text")]
    if extension == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs must be unlocked before upload.")
        if len(reader.pages) > 2000:
            raise ValueError("Split PDFs longer than 2,000 pages before upload.")
        parts = [(page.extract_text() or "", f"page {i + 1}") for i, page in enumerate(reader.pages)]
        scanned = [i + 1 for i, (text, _) in enumerate(parts) if len(text.strip()) < MIN_TEXT_CHARS]
        report["scanned"] = len(scanned)
        if scanned and ocr is not None:
            limit = ocr.settings["ocr_max_pages"]
            if len(scanned) > limit:
                raise ValueError(f"This PDF has {len(scanned)} scanned pages; OCR reads at most {limit} per document. Split it first.")
            texts, skipped = ocr.read_pages(pdf_page_images(body, scanned, ocr.settings["ocr_max_side"]),
                                            len(scanned), progress, canceled)
            report.update(ocr_pages=len(texts), **skipped)
            for number, text in texts.items():
                parts[number - 1] = (text, f"page {number} (OCR)")
        return parts
    check_zip(body)
    if extension == ".docx":
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = ["".join(p.itertext()) for p in root.findall(".//w:p", ns)]
        return [("\n\n".join(paragraphs), "document")]
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        output = []
        for sheet in workbook.worksheets:
            for number, row in enumerate(sheet.iter_rows(values_only=True), 1):
                if number > 100000:
                    raise ValueError("Split sheets longer than 100,000 rows before upload.")
                text = " | ".join("" if cell is None else str(cell) for cell in row)
                if text.strip(" |"):
                    output.append((text, f"sheet {sheet.title}, row {number}"))
        return output
    finally:
        workbook.close()


def _page_list(numbers):
    shown = ", ".join(str(n) for n in numbers[:10]) + (f" and {len(numbers) - 10} more" if len(numbers) > 10 else "")
    return ("page " if len(numbers) == 1 else "pages ") + shown


def ocr_note(report):
    """Admin-facing note about scanned pages that OCR did not index."""
    notes = []
    if report.get("language"):
        pages = report["language"]
        notes.append(f"OCR skipped {_page_list(pages)}: OCR supports English only, so "
                     f"{'that page was' if len(pages) == 1 else 'those pages were'} not indexed.")
    if report.get("unreadable"):
        pages = report["unreadable"]
        notes.append(f"OCR could not read {_page_list(pages)} reliably, so "
                     f"{'it was' if len(pages) == 1 else 'they were'} not indexed.")
    return " ".join(notes)


def chunk_parts(parts, size=650, overlap=80):
    output = []
    for text, location in parts:
        text = re.sub(r"[ \t]+", " ", text).strip()
        offset = 0
        while offset < len(text):
            end = min(len(text), offset + size)
            if end < len(text):
                boundary = text.rfind(" ", offset + size // 2, end)
                if boundary > offset:
                    end = boundary
            piece = text[offset:end].strip()
            if len(piece) >= 20:
                output.append({"text": piece, "location": location})
            if end >= len(text):
                break
            offset = max(offset + 1, end - overlap)
    return output


class LocalEmbeddings:
    """No hub client or download path: loads only explicitly supplied files."""
    def __init__(self, settings):
        self.settings = settings
        self.directory = Path(settings["embedding_directory"])
        self.session = None
        self.lock = threading.Lock()

    def ready(self):
        return all((self.directory / name).is_file() for name in ("model_optimized.onnx", "tokenizer.json"))

    def encode(self, texts):
        import numpy as np
        with self.lock:
            if self.session is None:
                if not self.ready():
                    raise RuntimeError("Local search-model files are missing. Provision assets before indexing.")
                import onnxruntime as ort
                ort.disable_telemetry_events()
                from tokenizers import Tokenizer
                options = ort.SessionOptions()
                options.intra_op_num_threads = 4
                self.session = ort.InferenceSession(str(self.directory / "model_optimized.onnx"),
                                                   sess_options=options, providers=["CPUExecutionProvider"])
                self.tokenizer = Tokenizer.from_file(str(self.directory / "tokenizer.json"))
                self.tokenizer.enable_truncation(max_length=self.settings["embedding_max_tokens"])
                self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
            outputs = []
            names = {item.name for item in self.session.get_inputs()}
            for start in range(0, len(texts), 32):
                encoded = self.tokenizer.encode_batch(texts[start:start + 32])
                values = {"input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
                          "attention_mask": np.array([e.attention_mask for e in encoded], dtype=np.int64),
                          "token_type_ids": np.array([e.type_ids for e in encoded], dtype=np.int64)}
                result = self.session.run(None, {key: value for key, value in values.items() if key in names})[0]
                if result.ndim == 3:
                    mask = values["attention_mask"][..., None]
                    result = (result * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
                result = result / np.linalg.norm(result, axis=1, keepdims=True).clip(min=1e-9)
                outputs.extend(np.asarray(result, dtype=np.float32))
            return outputs


class Knowledge:
    def __init__(self, store, config):
        self.store, self.config = store, config
        self.embeddings = LocalEmbeddings(config.settings)
        self.ocr = LocalOCR(config)
        self.publication_lock = threading.RLock()

    def list_documents(self, include_archived=False, owner=None):
        from .permissions import clause
        return self.store.rows("SELECT d.id,d.filename,d.title,d.version,d.priority,d.status,d.error,d.active,"
                               "d.created,d.updated,length(d.content) AS bytes,count(c.id) AS passages,"
                               "coalesce((SELECT restricted FROM document_access WHERE document_id=d.id),0) AS restricted "
                               "FROM documents d LEFT JOIN chunks c ON c.document_id=d.id "
                                 + ("WHERE NOT EXISTS(SELECT 1 FROM watched_files w WHERE w.stage_id=d.id) " if include_archived else "WHERE d.active=1 ")
                                 + ('AND '+clause()+' ' if owner is not None else '')
                                 + "GROUP BY d.id ORDER BY d.updated DESC", (owner,) if owner is not None else ())

    def add(self, filename, body, title="", priority=0, restricted=False):
        if not filename or Path(filename).name != filename or "\\" in filename:
            raise ValueError("Use a simple filename without folders.")
        if Path(filename).suffix.lower() not in EXTENSIONS:
            raise ValueError("Supported: PDF, DOCX, XLSX, TXT, MD, HTML and scanned images (PNG, JPG, TIFF).")
        if not body or len(body) > self.config.settings["max_document_mb"] * 1024 * 1024:
            raise ValueError("The document is empty or exceeds the upload limit.")
        if not -10 <= priority <= 10:
            raise ValueError("Source priority must be between -10 and 10.")
        if not isinstance(restricted, bool):
            raise ValueError('Choose the initial document access.')
        identity, now = uuid.uuid4().hex, time.time()
        with self.store.connect() as db:
            db.execute("INSERT INTO documents(id,filename,title,content,sha256,priority,status,created,updated) "
                           "VALUES(?,?,?,?,?,?,'pending',?,?)", (identity, filename, (title or filename)[:200], body,
                           hashlib.sha256(body).hexdigest(), priority, now, now))
            if restricted:
                db.execute('INSERT INTO document_access VALUES(?,1)', (identity,))
        return identity

    def index(self, identity, progress=lambda value: None, canceled=lambda: False, staged=False):
        document = self.store.one("SELECT * FROM documents WHERE id=? AND active=?", (identity, int(not staged)))
        if not document:
            raise ValueError("Document is not available.")
        self.store.execute("UPDATE documents SET status='indexing',error='' WHERE id=?", (identity,))
        try:
            progress("Extracting readable text")
            report = {}
            ocr = self.ocr if self.ocr.usable() else None
            chunks = chunk_parts(extract(document["filename"], document["content"], ocr, progress, canceled, report))
            note = ocr_note(report)
            if not chunks:
                if report.get("scanned") and ocr is None:
                    raise ValueError("No readable text found. This looks like a scan: turn on English OCR in Documents "
                                     "(its model files must be installed) or upload a text version.")
                raise ValueError(("No readable text found. " + note).strip())
            existing = self.store.one("SELECT count(*) AS n FROM chunks WHERE document_id<>?", (identity,))["n"]
            if staged:
                existing -= self.store.one('SELECT count(*) AS n FROM chunks WHERE document_id=(SELECT document_id FROM watched_files WHERE stage_id=?)', (identity,))['n']
            if existing + len(chunks) > self.config.settings["max_chunks"]:
                raise ValueError("Knowledge capacity reached. Split or reduce the document collection.")
            if canceled():
                raise InterruptedError("Indexing canceled.")
            vectors = [None] * len(chunks)
            if self.config.settings["embedding_mode"] == "hybrid":
                vectors = []
                for start in range(0, len(chunks), 32):
                    if canceled():
                        raise InterruptedError("Indexing canceled.")
                    progress(f"Building local search index: {start}/{len(chunks)} passages")
                    vectors.extend(self.embeddings.encode([c["text"] for c in chunks[start:start + 32]]))
            with self.publication_lock, self.store.connect() as db:
                active = db.execute("SELECT active FROM documents WHERE id=?", (identity,)).fetchone()
                if not active or bool(active[0]) == staged or canceled():
                    raise InterruptedError("Indexing canceled.")
                db.execute("DELETE FROM chunks WHERE document_id=?", (identity,))
                db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?)", [
                    (uuid.uuid4().hex, identity, document["version"], c["location"], c["text"],
                     vector.tobytes() if vector is not None else None) for c, vector in zip(chunks, vectors)])
                db.execute("UPDATE documents SET status='indexed',error=?,updated=? WHERE id=?", (note, time.time(), identity))
                version = db.execute("SELECT value FROM meta WHERE key='knowledge_version'").fetchone()[0] if staged else self.store.version(db)
            return {"document_id": identity, "passages": len(chunks), "knowledge_version": version}
        except Exception as exc:
            self.store.execute("UPDATE documents SET status='failed',error=?,updated=? WHERE id=?", (str(exc)[:500], time.time(), identity))
            raise

    def replace(self, identity, filename, body):
        if not filename or Path(filename).name != filename or "\\" in filename:
            raise ValueError("Use a simple filename without folders.")
        if Path(filename).suffix.lower() not in EXTENSIONS or not body or len(body) > self.config.settings["max_document_mb"] * 1024 * 1024:
            raise ValueError("Invalid or oversized replacement document.")
        with self.publication_lock, self.store.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id=? AND active=1", (identity,)).fetchone()
            if not row or row["status"] == "indexing":
                raise ValueError("Document is missing or is being indexed.")
            db.execute("INSERT INTO document_revisions VALUES(?,?,?,?,?,?)", (identity, row["version"],
                       row["filename"], row["content"], row["sha256"], time.time()))
            db.execute("UPDATE documents SET filename=?,content=?,sha256=?,version=version+1,status='pending',error='',updated=? WHERE id=?",
                       (filename, body, hashlib.sha256(body).hexdigest(), time.time(), identity))
            self.store.version(db)

    def archive(self, identity, archived=True):
        with self.publication_lock, self.store.connect() as db:
            if not db.execute("SELECT id FROM documents WHERE id=?", (identity,)).fetchone():
                raise ValueError("Document not found.")
            db.execute("UPDATE documents SET active=?,updated=? WHERE id=?", (int(not archived), time.time(), identity))
            self.store.version(db)

    def delete_archived(self, identity):
        with self.publication_lock, self.store.connect() as db:
            document = db.execute('SELECT active FROM documents WHERE id=?', (identity,)).fetchone()
            if not document:
                raise ValueError('Document not found.')
            if document['active']:
                raise ValueError('Archive the document before permanently deleting it.')
            db.execute('DELETE FROM chunks WHERE document_id=?', (identity,))
            db.execute('DELETE FROM document_revisions WHERE document_id=?', (identity,))
            db.execute('DELETE FROM documents WHERE id=?', (identity,))
            self.store.version(db)

    def search(self, question, glossary=None, limit=5, owner=None):
        import numpy as np
        from .permissions import clause
        with self.store.connect() as db:
            version = db.execute("SELECT value FROM meta WHERE key='knowledge_version'").fetchone()[0]
            rows = [dict(row) for row in db.execute(
                "SELECT c.id,c.document_id,c.document_version,c.location,c.text,c.vector,d.filename,d.title,d.priority "
                "FROM chunks c JOIN documents d ON d.id=c.document_id "
                "WHERE d.active=1 AND d.status='indexed'" + (' AND '+clause() if owner is not None else ''),
                (owner,) if owner is not None else ())]
        if not rows:
            return [], version
        query = question
        for term, expanded in (glossary or {}).items():
            if normalize(term) in normalize(question):
                query += " " + expanded
        wanted = set(tokens(query))
        terms = [Counter(tokens(row["text"] + " " + row["title"])) for row in rows]
        document_frequency = Counter(t for counts in terms for t in wanted if t in counts)
        average = max(1, sum(sum(c.values()) for c in terms) / len(terms))
        lexical = []
        for counts in terms:
            length = sum(counts.values())
            score = sum(math.log(1 + (len(rows) - document_frequency[t] + .5) / (document_frequency[t] + .5))
                        * counts[t] * 2.2 / (counts[t] + 1.2 * (.25 + .75 * length / average))
                        for t in wanted if counts[t])
            lexical.append(score)
        semantic = [0.] * len(rows)
        if self.config.settings["embedding_mode"] == "hybrid" and any(row["vector"] for row in rows):
            q = self.embeddings.encode([query])[0]
            for i, row in enumerate(rows):
                if row["vector"]:
                    v = np.frombuffer(row["vector"], dtype=np.float32)
                    semantic[i] = float(v @ q) if v.shape == q.shape else 0.
        lexical_order = sorted(range(len(rows)), key=lambda i: lexical[i], reverse=True)
        semantic_order = sorted(range(len(rows)), key=lambda i: semantic[i], reverse=True)
        ranks = {}
        for scores, order in ((lexical, lexical_order), (semantic, semantic_order)):
            for rank, i in enumerate(order):
                if scores[i] > 0:
                    ranks[i] = ranks.get(i, 0) + 1 / (60 + rank)
        floor = self.config.settings["semantic_floor"]
        eligible = [i for i in ranks if lexical[i] > 0 or semantic[i] >= floor]
        eligible.sort(key=lambda i: (ranks[i], rows[i]["priority"]), reverse=True)
        result = []
        for i in eligible[:limit]:
            row = rows[i]
            result.append({key: value for key, value in row.items() if key not in ("vector", "priority")})
        return result, version
