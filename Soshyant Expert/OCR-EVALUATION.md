# English OCR evaluation (Unlimited-OCR)

**Date:** 2026-10-17 · **Outcome: adopted for English. Not used for Persian.** The user guide is [OCR.md](OCR.md).

## Summary

- **English: excellent.** On all 12 English test images (clean, scanned and phone photo; including a table and a two-column page) the character error was **0.0%**, every number was correct and nothing looped. Speed on an RTX 3070 Laptop GPU (8 GB): **~2.5 s per page on the GPU**, **~38 s per page on the CPU only**.
- **Persian: not reliable enough.** A few pages came out nearly perfect (1–2% error), but on others the model looped, dropped lines, scrambled mixed Persian/English lines and **silently changed numbers**: `۴۸ ساعت → ۸ ساعت`, `هر ۵۰۰ ساعت → هر ۲۰۰ ساعت`, `هر ۲۵۰۰ ساعت → هر ۲۰۰ ساعت`, `X200 → ۲۰۰`. With the shipped model, none of the 12 Persian images reached <5% error. That is unacceptable for a product whose answers cite facts, so Persian OCR output is never indexed.
- **No new runtime.** It runs on the bundled llama.cpp (`assets/llama`, build b10709). No PyTorch, CUDA toolkit, Linux or Docker.
- **Hardware:** on an 8 GB GPU the OCR model cannot sit next to a ~6 GB chat model, so OCR runs on the CPU by default.

## What was tested

| | |
|---|---|
| Machine | Windows 11, RTX 3070 Laptop GPU 8 GB, Ryzen 9 5900HS (8 cores), 39 GB RAM |
| Runtime | Bundled `llama-server.exe` (b10709, commit 9a9394a89 — includes llama.cpp's Unlimited-OCR support, PRs #24969 and #25614) |
| Model files | `sabafallah/Unlimited-OCR-GGUF` @ `af78953c…` (published by the author of llama.cpp's Unlimited-OCR support; weights from baidu/Unlimited-OCR, MIT). Q4_K_M 1.95 GB and Q8_0 3.13 GB language parts, image encoder (BF16) 0.83 GB. The shipped files and their SHA-256 are in `assets/ocr/provenance.json`. |
| Test pages | 8 synthetic pages with exact reference text. English: manual with torque values, maintenance table, two-column procedure, dense 8.5 pt terms. Persian: HR policy with numbered clauses, right-to-left table, mixed Persian/English spec sheet, dense 9.5 pt terms. Each in 3 versions — **clean** (~240 dpi), **scan** (~200 dpi, rotated, blurred, noisy, JPEG) and **phone photo** (~120 dpi, perspective, uneven light, JPEG) — 24 images. Rendered with Chrome so Persian shaping is correct. |
| Metrics | Character error after search-style normalization (case, Persian/Arabic letter variants, digit forms, ZWNJ, markup), word recall/precision, share of reference numbers found, loop detection. |
| Configs | Q4 vs Q8 · image as-is vs capped at 1600 / 1280 px · GPU, CPU, GPU-image + CPU-text hybrid · loop guard on/off |

> These were synthetic pages: real fonts with simulated scanning. Real scans add stamps, handwriting, skew and poor print, so the English figures are a best case. The Persian failures happened on *easy* pages, which makes them a strong negative signal.

## Results

### Accuracy (12 English and 12 Persian images per config)

| Config | English: mean error | English: pages <5% error | English: numbers found | Persian: median error | Persian: pages <5% error | Persian: numbers found | Persian loops |
|---|---|---|---|---|---|---|---|
| **Q4, image ≤1600 px** (shipped) | **0.0%** | **12/12** | **100%** | 44.3% | 0/12 | 67.9% | 6/12 |
| Q8, image ≤1600 px | 0.0% | 12/12 | 100% | 41.7% | 2/12 | 79.5% | 3/12 |
| Q4, image ≤1280 px | 0.0% | 12/12 | 100% | 44.1% | 0/12 | 68.6% | 6/12 |
| Q8, image ≤1280 px | 0.0% | 12/12 | 100% | 43.8% | 1/12 | 76.3% | 5/12 |
| Q4, image as-is (up to 1985×2808) | 3.1% | 11/12 | 100% | 47.5% | 0/12 | 67.6% | 6/12 |
| Q8, image as-is | 0.0% | 12/12 | 100% | 43.6% | 1/12 | 77.2% | 4/12 |
| Q8 ≤1600 px, loop guard off | — | — | — | 41.7% | 2/12 | 77.2% | 3/12 |

Persian error above 100% means the output was longer than the page because it looped. Persian table pages scored ~44% partly because the model lists right-to-left table cells left to right; reversing them (now done automatically) brings them to ~5–7%, but the wrong maintenance intervals remain.

### Speed and memory (Q4, image ≤1600 px)

| Mode | Seconds per page | GPU memory | RAM | Fits next to a 5.8 GB chat model on 8 GB? |
|---|---|---|---|---|
| GPU, context 6144 | **~2.5 s** | 4.9 GB | 3.6 GB | No |
| Hybrid: image encoder on GPU, text on CPU | ~11–16 s | 2.8 GB | 3.4 GB | No (too tight) |
| **CPU only** (8 threads) — default | **~38 s** (~26 s reading the image, then ~37 tokens/s); after integration, 36 s for a light page and ~2½ min for a dense page with the laptop running slower | — | 5.7 GB | Yes |

Server start-up takes ~3.5 s. Each page at ≤1600 px costs a fixed 908 image tokens; English pages produced at most ~500 output tokens. A 100-page scanned English manual takes about **4 minutes on the GPU** or **1 hour on the CPU**.

## Findings built into the product

1. **Strict prompt.** The model only answers `<image>document parsing.` with nothing in between. The product uses llama-server's `/completion` endpoint with the server's `media_marker`; the chat endpoint inserts a line break and the model then returns nothing.
2. **Page size.** Images are capped at 1600 px on the longer side. Full-resolution renders made the model invent text (one page began with "1. 2. 3. … 99.").
3. **Printed area and tile grid.** Found during integration: the model returns *nothing* for a page that is mostly white paper (a few lines at the top), while the same text cropped to its printed area reads correctly. Cropping alone made a wide strip, which llama.cpp then split into 24 tiles (2,708 image tokens, about 2 minutes of CPU just to read the image). llama.cpp picks the 640 px tile grid whose shape is closest to the image's, so the product crops to the printed area, pads to the nearest small grid (2–6 tiles) and resizes to exactly that grid. Blank pages skip the model. A printed page that still returns nothing (typically a single line of text) is reported as unreadable.
   Checked on generated English pages on the GPU: a few lines at the top, a two-column page and a ruled table all read 100% of words and numbers in 1–8 s. A dense page of 30 near-identical numbered lines read 99% of words, but the model lost its place and re-read some lines, with a few wrong codes. The old full-page approach did worse on that page: it looped to the output limit. The same dense page on the CPU (about 2½ minutes) also re-read lines. Hence the next check.
4. **Repeated long lines.** A page whose OCR text contains the same line of 8 or more words twice is treated as unreliable and not indexed, because that is how losing its place shows up.
5. **Special tokens on.** Table cells and layout boxes are special tokens; the server runs with `--special`, then layout labels are removed and tables become `cell | cell` rows (reversed for right-to-left tables).
6. **Loop guard and failure handling.** The DRY settings recommended by llama.cpp's implementer are kept (turning them off didn't help). Output is capped at 2048 tokens; a page that hits the cap or repeats itself is not indexed and is reported to the admin.
7. **English gate.** Pages whose OCR text is more than 30% Arabic-script letters are not indexed and are reported to the admin.
8. **Model size.** Q4 and Q8 were identical on English, so Q4 ships (2.8 GB with the image encoder).
9. **Attention.** llama.cpp runs this model with full attention; the R-SWA attention it was trained with is still an open PR (#24975). Page-by-page OCR does not need it, but the mismatch may contribute to the Persian failures (untested).

## Not done yet

- **Persian OCR.** Re-test when R-SWA lands in llama.cpp, or test Baidu's reference implementation (PyTorch + CUDA, 6.7 GB BF16 weights) on the same pages to tell model limits from port limits. Otherwise evaluate a Persian-specific OCR engine.
- **Real customer scans.** Run 30–50 real pilot pages before relying on English OCR for a customer.
- **OCR preview before publishing.** Admins see skipped pages after indexing; a preview of OCR text inside the watched-folder approval step would be a further safeguard.

The evaluation scripts, test pages and the unused Q8 model were deleted after the test to free disk space. `tools/smoke_ocr.py` re-checks English OCR end to end on generated pages.
