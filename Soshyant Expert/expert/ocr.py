"""Optional English OCR for scanned PDF pages and images.

Runs Baidu's Unlimited-OCR model (MIT licence) through the bundled llama.cpp server on its own
loopback port. Nothing is downloaded and nothing leaves this computer. It is validated for English
only: pages that come back mostly in Arabic script (Persian) are skipped, because testing showed
the model can silently change Persian numbers. See OCR.md and OCR-EVALUATION.md.
"""
import base64
import html
import io
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# The model only answers when this exact text follows the image, with nothing in between.
PROMPT = "document parsing."
# Pages whose text layer is shorter than this are treated as scanned.
MIN_TEXT_CHARS = 40
# Above this share of Arabic-script letters a page is not English and is not indexed.
MAX_ARABIC_SHARE = 0.3

LAYOUT = re.compile(r"^\s*([a-z_]+)\s*\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]\s*")
ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
LATIN = re.compile(r"[A-Za-z]")


def table_rows(table_html):
    """Cell texts per row. The model lists cells left to right as printed, so rows of a
    right-to-left table are reversed into reading order."""
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.S):
        cells = [re.sub(r"<[^>]+>", " ", cell).strip()
                 for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S)]
        rows.append(cells)
    joined = " ".join(" ".join(row) for row in rows)
    if len(ARABIC.findall(joined)) > len(joined) * 0.3:
        rows = [list(reversed(row)) for row in rows]
    return rows


def clean_output(raw):
    """Model output to plain text for indexing: drop layout labels and picture blocks, keep
    tables as 'cell | cell' rows."""
    text = re.sub(r"<｜[^｜>]{0,40}｜>", "", raw)
    text = re.sub(r"<\|/?det\|>", "", text)
    lines, keep = [], True
    for line in text.splitlines():
        match = LAYOUT.match(line)
        if match:
            keep = match.group(1) != "image"
            line = line[match.end():]
        if keep:
            lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"<\|[^>]{0,40}\|>", " ", text)
    text = re.sub(r"<table[^>]*>.*?</table>",
                  lambda m: "\n" + "\n".join(" | ".join(row) for row in table_rows(m.group(0))) + "\n",
                  text, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]{1,200}>", " ", text))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def looped(text, size=8, repeats=4):
    """True when the same run of words repeats — the model's failure mode on hard pages."""
    words = text.split()
    seen = {}
    for i in range(max(0, len(words) - size + 1)):
        key = tuple(words[i:i + size])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= repeats:
            return True
    return False


def repeated_lines(text, min_words=8):
    """True when a long line appears twice: on dense pages the model can lose its place and
    re-read a block, sometimes with wrong numbers, so the page is not trusted."""
    seen = set()
    for line in text.splitlines():
        line = " ".join(line.split())
        if len(line.split()) < min_words:
            continue
        if line in seen:
            return True
        seen.add(line)
    return False


def arabic_share(text):
    arabic, latin = len(ARABIC.findall(text)), len(LATIN.findall(text))
    return arabic / (arabic + latin) if arabic + latin else 0.0


# llama.cpp splits an image into 640 px tiles in the grid whose shape is closest to the image's
# (up to 32 tiles, ~100 tokens each, plus a 256-token overview). A cropped wide strip would match a
# 24-tile grid and take minutes on a CPU, so pages are padded to one of these cheap grids instead.
TILE = 640
GRIDS = [(1, 4), (1, 3), (1, 2), (2, 3), (2, 2), (3, 2), (2, 1), (3, 1), (4, 1)]


def prepare(image):
    """Page image ready for OCR, as PNG; None for a blank page.

    Crops to the printed area — the model answers nothing for a page that is mostly white paper,
    while the same text cropped reads correctly — then pads (centred, white) to the nearest cheap
    tile grid and resizes to exactly that grid, so llama.cpp uses 2–6 tiles."""
    from PIL import Image, ImageFilter
    image = image.convert("RGB")
    probe = image.convert("L")
    probe.thumbnail((800, 800))
    ink = probe.point(lambda value: 255 if value < 160 else 0).filter(ImageFilter.MedianFilter(3))
    box = ink.getbbox()
    if not box:
        return None
    ratio = image.width / probe.width
    pad = int(max(image.size) * 0.03)
    box = (max(0, int(box[0] * ratio) - pad), max(0, int(box[1] * ratio) - pad),
           min(image.width, int(box[2] * ratio) + pad), min(image.height, int(box[3] * ratio) + pad))
    image = image.crop(box)
    aspect = image.width / image.height
    columns, rows = min(GRIDS, key=lambda grid: max(aspect, grid[0] / grid[1]) / min(aspect, grid[0] / grid[1]))
    width = max(image.width, round(image.height * columns / rows))
    height = max(image.height, round(image.width * rows / columns))
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    canvas = canvas.resize((TILE * columns, TILE * rows), Image.LANCZOS)
    buffer = io.BytesIO()
    canvas.save(buffer, "PNG")
    return buffer.getvalue()


def pdf_page_images(body, numbers, max_side):
    """Render the given 1-based PDF pages (at most 200 dpi) and prepare them for OCR."""
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(body)
    try:
        for number in numbers:
            page = document[number - 1]
            try:
                width, height = page.get_size()
                scale = min(200 / 72, 2 * max_side / max(width, height, 1))
                yield number, prepare(page.render(scale=scale).to_pil())
            finally:
                page.close()
    finally:
        document.close()


def image_page_count(body):
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(body)) as image:
            return getattr(image, "n_frames", 1)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("The image could not be opened. Use PNG, JPG or TIFF.") from exc


def image_pages(body, max_side, limit):
    """Each frame of an image file (multi-page TIFF included), upright and prepared for OCR."""
    from PIL import Image, ImageOps, ImageSequence
    with Image.open(io.BytesIO(body)) as image:
        count = getattr(image, "n_frames", 1)
        if count > limit:
            raise ValueError(f"This image has {count} pages; OCR reads at most {limit} per document. Split it first.")
        for number, frame in enumerate(ImageSequence.Iterator(image), 1):
            yield number, prepare(ImageOps.exif_transpose(frame.convert("RGB")))


class LocalOCR:
    """Owns one loopback llama-server with the OCR model; started on demand, stopped when idle."""

    def __init__(self, config):
        self.config = config
        self.settings = config.settings
        self.url = f"http://127.0.0.1:{self.settings['ocr_port']}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.process = None
        self.log = None
        self.marker = None
        self.state = "stopped"
        self.lock = threading.Lock()
        self.busy = 0
        self.last_used = 0.0
        self.stopping = threading.Event()
        threading.Thread(target=self._stop_when_idle, daemon=True).start()

    def enabled(self):
        return bool(self.settings.get("ocr_enabled"))

    def installed(self):
        return all(Path(self.settings[key]).is_file() for key in ("ocr_model", "ocr_projector", "llama_executable"))

    def usable(self):
        return self.enabled() and self.installed()

    def status(self):
        return {"enabled": self.enabled(), "installed": self.installed(), "state": self.state,
                "device": "gpu" if self.settings["ocr_gpu_layers"] > 0 else "cpu", "languages": ["en"]}

    def _threads(self):
        configured = int(self.settings.get("ocr_threads") or 0)
        return configured if configured > 0 else max(2, min(8, (os.cpu_count() or 4) // 2))

    def ensure(self, canceled=lambda: False):
        with self.lock:
            if self.process is not None and self.process.poll() is None and self.state == "ready":
                return
            if not self.installed():
                raise RuntimeError("The OCR model files are missing. Provision assets/ocr before reading scanned pages.")
            # A foreign process is never adopted or terminated.
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", self.settings["ocr_port"])) == 0:
                    raise RuntimeError("The configured OCR port is occupied. Choose a different ocr_port.")
            threads = str(self._threads())
            command = [self.settings["llama_executable"], "--host", "127.0.0.1", "--port", str(self.settings["ocr_port"]),
                       "-m", self.settings["ocr_model"], "--mmproj", self.settings["ocr_projector"],
                       "-ngl", str(self.settings["ocr_gpu_layers"]), "-c", "6144", "--parallel", "1", "--temp", "0",
                       "--chat-template", "deepseek-ocr", "--no-jinja", "--flash-attn", "off", "--special",
                       # Loop guard recommended for this model in llama.cpp; kept weak so tables stay intact.
                       "--dry-multiplier", "0.8", "--dry-base", "1.75", "--dry-allowed-length", "35",
                       "--dry-penalty-last-n", "128", "--dry-sequence-breaker", "none",
                       "-t", threads, "-tb", threads]
            if self.settings["ocr_gpu_layers"] <= 0:
                command.append("--no-mmproj-offload")
            self.log = (self.config.data / "ocr-runtime.log").open("ab")
            self.state = "loading"
            self.last_used = time.monotonic()
            self.process = subprocess.Popen(command, stdout=self.log, stderr=self.log,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if canceled():
                    self._close()
                    raise InterruptedError("Indexing canceled.")
                if self.process.poll() is not None:
                    self._close()
                    self.state = "failed"
                    raise RuntimeError("The OCR runtime failed to start. Check data/ocr-runtime.log; on small GPUs set ocr_gpu_layers to 0.")
                try:
                    with self.opener.open(self.url + "/props", timeout=2) as response:
                        self.marker = json.load(response)["media_marker"]
                        self.state = "ready"
                        return
                except (urllib.error.URLError, OSError, KeyError, ValueError):
                    time.sleep(.5)
            self._close()
            self.state = "failed"
            raise RuntimeError("The OCR runtime did not become ready within two minutes.")

    def read(self, png, canceled=lambda: False):
        """OCR one page image. Returns (raw model output, stop type: 'eos' or 'limit')."""
        with self.lock:
            self.busy += 1
        try:
            self.ensure(canceled)
            payload = {"prompt": {"prompt_string": self.marker + PROMPT,
                                  "multimodal_data": [base64.b64encode(png).decode("ascii")]},
                       "temperature": 0, "n_predict": self.settings["ocr_max_tokens"],
                       "cache_prompt": False, "stream": True}
            request = urllib.request.Request(self.url + "/completion", data=json.dumps(payload).encode(),
                                             headers={"Content-Type": "application/json"})
            pieces, stop_type, started = [], None, time.monotonic()
            try:
                with self.opener.open(request, timeout=120) as response:
                    for line in response:
                        if canceled():
                            raise InterruptedError("Indexing canceled.")
                        if time.monotonic() - started > self.settings["ocr_page_seconds"]:
                            raise RuntimeError("OCR time limit reached for a page.")
                        if not line.startswith(b"data: "):
                            continue
                        event = json.loads(line[6:])
                        pieces.append(event.get("content", ""))
                        if event.get("stop"):
                            stop_type = event.get("stop_type")
                            break
            except (urllib.error.URLError, OSError) as exc:
                if isinstance(exc, InterruptedError):
                    raise
                raise RuntimeError("The OCR runtime connection failed. Check data/ocr-runtime.log.") from exc
            if stop_type is None:
                raise RuntimeError("The OCR result was interrupted.")
            return "".join(pieces), stop_type
        finally:
            with self.lock:
                self.busy -= 1
                self.last_used = time.monotonic()

    def read_pages(self, pages, total, progress=lambda value: None, canceled=lambda: False):
        """OCR (number, png or None for blank) pages.
        Returns ({number: text}, {'unreadable': [...], 'language': [...]})."""
        texts, skipped = {}, {"unreadable": [], "language": []}
        for done, (number, png) in enumerate(pages, 1):
            if canceled():
                raise InterruptedError("Indexing canceled.")
            if png is None:  # blank page: nothing to read
                continue
            progress(f"Reading scanned page {done} of {total} with OCR")
            raw, stop_type = self.read(png, canceled)
            text = clean_output(raw)
            if stop_type == "limit" or not text or looped(text) or repeated_lines(text):
                skipped["unreadable"].append(number)
            elif arabic_share(text) > MAX_ARABIC_SHARE:
                skipped["language"].append(number)
            else:
                texts[number] = text
        return texts, skipped

    def _stop_when_idle(self):
        while not self.stopping.wait(5):
            with self.lock:
                idle = time.monotonic() - self.last_used
                if self.process is not None and not self.busy and idle > self.settings["ocr_idle_seconds"]:
                    self._close()

    def _close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        if self.state != "failed":
            self.state = "stopped"
        if self.log is not None:
            self.log.close()
            self.log = None

    def close(self):
        with self.lock:
            self._close()

    def shutdown(self):
        self.stopping.set()
        self.close()
