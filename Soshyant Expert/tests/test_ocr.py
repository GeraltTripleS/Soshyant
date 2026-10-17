import io
import json
import unittest

from PIL import Image, ImageDraw

from expert.config import Config
from expert.knowledge import extract, ocr_note
from expert.ocr import LocalOCR, arabic_share, clean_output, looped, prepare, repeated_lines, table_rows
from test_engine import Fixture


def page(ink=True, size=(620, 877)):
    image = Image.new("RGB", size, "white")
    if ink:
        draw = ImageDraw.Draw(image)
        for y in range(80, 200, 30):
            draw.rectangle((60, y, 520, y + 12), fill="black")
    return image


def pdf(*pages):
    buffer = io.BytesIO()
    pages[0].save(buffer, "PDF", resolution=75, save_all=True, append_images=list(pages[1:]))
    return buffer.getvalue()


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


ENGLISH = ("<|det|>title [86, 65, 582, 93]<|/det|>Pump Manual\n<|det|>text [85, 176, 875, 217]<|/det|>"
           "Torque the M12 housing bolts to 60 Nm.<｜end▁of▁sentence｜>", "eos")
PERSIAN = ("<|det|>text [87, 140, 912, 184]<|/det|>مرخصی استحقاقی هر سال ۲۶ روز است و به سال بعد منتقل می‌شود.", "eos")
LOOP = ("<|det|>text [1, 2, 3, 4]<|/det|>" + "4. 4. 4. 4. " * 40, "limit")


class FakeOCR(LocalOCR):
    """Real page classification (LocalOCR.read_pages) over canned model outputs; no runtime."""

    def __init__(self, outputs, **settings):
        self.settings = {"ocr_max_pages": 200, "ocr_max_side": 1600, **settings}
        self.outputs = list(outputs)
        self.images = []

    def usable(self):
        return True

    def read(self, image, canceled=lambda: False):
        self.images.append(image)
        return self.outputs.pop(0)

    def close(self):
        pass

    def shutdown(self):
        pass


class OutputTests(unittest.TestCase):
    def test_layout_labels_and_pictures_are_removed_and_tables_kept_as_rows(self):
        raw = ("<|det|>title [1, 2, 3, 4]<|/det|>Maintenance\n<|det|>image [5, 6, 7, 8]<|/det|>logo text\n"
               "<|det|>table [9, 9, 9, 9]<|/det|><table><tr><td>Part</td><td>Interval</td></tr>"
               "<tr><td>Filter</td><td>500 h</td></tr></table>\ntext [1, 1, 2, 2]Record every action.<｜end▁of▁sentence｜>")
        text = clean_output(raw)
        self.assertEqual(text, "Maintenance\n\nPart | Interval\nFilter | 500 h\n\nRecord every action.")
        self.assertNotIn("logo", text)

    def test_right_to_left_table_cells_are_returned_in_reading_order(self):
        rows = table_rows("<table><tr><td>کد قطعه</td><td>اقدام</td><td>ردیف</td></tr></table>")
        self.assertEqual(rows, [["ردیف", "اقدام", "کد قطعه"]])

    def test_loops_repeated_lines_and_script_are_detected(self):
        self.assertTrue(looped("۴. ۴. ۴. ۴. " * 20))
        self.assertFalse(looped("Torque the M12 housing bolts to 60 Nm in a star pattern."))
        line = "Step 20: Use only ISO VG 46 hydraulic oil in the main reservoir."
        self.assertTrue(repeated_lines(f"{line}\nStep 21: Tighten the flange bolts.\n{line}"))
        self.assertFalse(repeated_lines("Oil filter | 500 h\nOil filter | 500 h\n" + line))  # short rows may repeat
        self.assertGreater(arabic_share("مرخصی استحقاقی ۲۶ روز"), 0.9)
        self.assertEqual(arabic_share("Pump X200 manual"), 0)

    def test_blank_pages_are_skipped_and_pages_fit_a_small_tile_grid(self):
        self.assertIsNone(prepare(page(ink=False)))
        # The ink block at the top of a portrait page is wide, so it gets a wide 2–4 tile grid.
        prepared = Image.open(io.BytesIO(prepare(page())))
        self.assertGreater(prepared.width, prepared.height)
        for image in (page(), page(size=(2480, 3508)), Image.new("RGB", (900, 1300), "black")):
            width, height = Image.open(io.BytesIO(prepare(image))).size
            self.assertEqual((width % 640, height % 640), (0, 0))
            self.assertLessEqual((width // 640) * (height // 640), 6)

    def test_admin_note_names_skipped_pages(self):
        self.assertEqual(ocr_note({}), "")
        note = ocr_note({"language": [2], "unreadable": [3, 4]})
        self.assertIn("page 2: OCR supports English only", note)
        self.assertIn("pages 3, 4 reliably", note)


class ExtractionTests(Fixture):
    def use(self, ocr):
        self.engine.knowledge.ocr.shutdown()
        self.engine.knowledge.ocr = ocr
        return ocr

    def test_only_scanned_pdf_pages_with_ink_go_to_ocr(self):
        ocr = FakeOCR([ENGLISH])
        report = {}
        parts = extract("scan.pdf", pdf(page(ink=False), page()), ocr, report=report)
        self.assertEqual(len(ocr.images), 1)  # the blank page never reaches the model
        self.assertEqual(parts[0][1], "page 1")
        self.assertEqual(parts[1], ("Pump Manual\nTorque the M12 housing bolts to 60 Nm.", "page 2 (OCR)"))
        self.assertEqual(report, {"scanned": 2, "ocr_pages": 1, "unreadable": [], "language": []})

    def test_persian_and_unreadable_pages_are_not_indexed_and_are_reported(self):
        self.use(FakeOCR([ENGLISH, PERSIAN, LOOP]))
        identity = self.engine.knowledge.add("scan.pdf", pdf(page(), page(), page()))
        result = self.engine.knowledge.index(identity)
        self.assertEqual(result["passages"], 1)
        rows = self.store.rows("SELECT location,text FROM chunks WHERE document_id=?", (identity,))
        self.assertEqual([row["location"] for row in rows], ["page 1 (OCR)"])
        document = self.store.one("SELECT status,error FROM documents WHERE id=?", (identity,))
        self.assertEqual(document["status"], "indexed")
        self.assertIn("page 2: OCR supports English only", document["error"])
        self.assertIn("could not read page 3", document["error"])
        sources, _ = self.engine.knowledge.search("M12 housing bolts torque")
        self.assertEqual(sources[0]["location"], "page 1 (OCR)")

    def test_scan_without_usable_ocr_explains_how_to_enable_it(self):
        self.assertFalse(self.engine.knowledge.ocr.usable())  # fixture has no OCR model files
        identity = self.engine.knowledge.add("scan.pdf", pdf(page()))
        with self.assertRaisesRegex(ValueError, "turn on English OCR"):
            self.engine.knowledge.index(identity)

    def test_images_are_read_with_ocr_and_need_it(self):
        identity = self.engine.knowledge.add("photo.png", png(page()))
        with self.assertRaisesRegex(ValueError, "read with English OCR"):
            self.engine.knowledge.index(identity)
        self.use(FakeOCR([ENGLISH]))
        self.assertEqual(self.engine.knowledge.index(identity)["passages"], 1)

    def test_scanned_page_limit_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "reads at most 1"):
            extract("scan.pdf", pdf(page(), page()), FakeOCR([], ocr_max_pages=1))


class SettingsTests(Fixture):
    def test_older_settings_files_get_ocr_defaults_and_toggle_persists(self):
        path = self.root / "config/server.json"
        settings = {key: value for key, value in json.loads(path.read_text()).items() if not key.startswith("ocr_")}
        path.write_text(json.dumps(settings))
        config = Config(self.root)
        self.assertTrue(config.settings["ocr_enabled"])
        self.assertTrue(config.settings["ocr_model"].endswith("unlimited-ocr-Q4_K_M.gguf"))
        self.assertEqual(config.settings["ocr_gpu_layers"], 0)
        config.save_setting("ocr_enabled", False)
        self.assertFalse(json.loads(path.read_text())["ocr_enabled"])
        self.assertFalse(Config(self.root).settings["ocr_enabled"])


if __name__ == "__main__":
    unittest.main()
