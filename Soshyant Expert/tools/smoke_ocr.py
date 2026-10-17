"""Real English OCR check on a temporary copy: generated scan → OCR → indexed passages.

Uses the bundled OCR model and llama.cpp runtime; customer documents are never touched.
Usage: runtime\\python.exe tools\\smoke_ocr.py [--gpu]
"""
import argparse
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from expert.config import Config  # noqa: E402
from expert.knowledge import Knowledge  # noqa: E402
from expert.storage import Store  # noqa: E402

LINES = ["Aurora X200 Service Manual - Section 7.2 Housing Assembly",
         "Tighten the M12 housing bolts in a star pattern to 30 Nm.",
         "Repeat the pattern and tighten all bolts to the final torque of 60 Nm.",
         "Replace the housing gasket (part GS-450) whenever the housing is opened.",
         "Never run the pump dry for more than 30 seconds."]
EXPECTED = ["M12", "60 Nm", "GS-450", "30 seconds"]


def scanned_page():
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    page = Image.new("L", (1240, 1754), 255)  # A4 at 150 dpi
    draw = ImageDraw.Draw(page)
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, 30)
            break
        except OSError:
            font = ImageFont.load_default(size=30)
    y = 140
    for line in LINES:
        draw.text((110, y), line, fill=20, font=font)
        y += 70
    return page.rotate(0.6, fillcolor=255).filter(ImageFilter.GaussianBlur(0.6))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", action="store_true", help="run OCR on the GPU instead of the CPU")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "config").mkdir()
        shutil.copy2(ROOT / "config/domain.json", root / "config/domain.json")
        settings = json.loads((ROOT / "config/server.json").read_text(encoding="utf-8"))
        real = Config()
        settings.update(embedding_mode="lexical", ocr_enabled=True, ocr_gpu_layers=99 if args.gpu else 0,
                        llama_executable=real.settings["llama_executable"], ocr_model=real.settings["ocr_model"],
                        ocr_projector=real.settings["ocr_projector"])
        (root / "config/server.json").write_text(json.dumps(settings), encoding="utf-8")
        config = Config(root)
        knowledge = Knowledge(Store(config.data), config)
        try:
            if not knowledge.ocr.installed():
                raise SystemExit("OCR model files are missing in assets/ocr.")
            page = scanned_page()
            pdf = io.BytesIO()
            page.convert("RGB").save(pdf, "PDF", resolution=150, save_all=True,
                                     append_images=[page.point(lambda _: 255).convert("RGB")])  # page 2 is blank
            png = io.BytesIO()
            page.save(png, "PNG")
            for name, body in (("scan.pdf", pdf.getvalue()), ("photo.png", png.getvalue())):
                identity = knowledge.add(name, body)
                started = time.time()
                result = knowledge.index(identity, progress=lambda phase: print("  ", phase, flush=True))
                rows = knowledge.store.rows("SELECT location,text FROM chunks WHERE document_id=?", (identity,))
                text = " ".join(row["text"] for row in rows)
                missing = [word for word in EXPECTED if word not in text]
                print(f"{name}: {result['passages']} passages in {time.time() - started:.1f}s; "
                      f"locations {sorted({row['location'] for row in rows})}")
                if missing:
                    raise SystemExit(f"{name}: OCR text is missing {missing}: {text[:300]!r}")
            print(f"English OCR check passed ({'GPU' if args.gpu else 'CPU'}).")
        finally:
            knowledge.ocr.shutdown()


if __name__ == "__main__":
    main()
