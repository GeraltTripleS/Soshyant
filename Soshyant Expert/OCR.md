# English OCR for scanned documents

Soshyant Expert can read **scanned English pages**: PDF pages without a text layer, and image files (PNG, JPG, TIFF including multi-page TIFF). The text is then indexed like any other document. Each passage's location is marked as OCR, for example `page 4 (OCR)`, so users can see where the text came from.

OCR runs **entirely on this server**, using Baidu's Unlimited-OCR model (MIT licence) through the bundled llama.cpp runtime. Nothing is downloaded and nothing is sent to the internet. Restart the server and refresh the browser after updating.

## Turning it on or off

Administrators: open **Documents**. In the upload card, tick or untick **Read scanned English pages with local OCR**. The line below it shows whether OCR is on, off or not installed, and where it runs. The **Overview** shows the same status. The choice is saved in `config/server.json` (`ocr_enabled`) and applies to documents indexed afterwards; use **Reindex** to read an existing scanned document again.

When OCR is off, scanned pages are not indexed. A PDF with no readable text at all fails with a message explaining how to turn OCR on.

## What gets read

- **PDF pages** are read normally when they have a text layer. Only pages with almost no extractable text (under 40 characters) go to OCR, so mixed PDFs work.
- **Image files** are always read with OCR. Phone photos are turned upright using their orientation tag.
- **Blank pages** are skipped without running the model.
- Each page is cropped to its printed area and shaped to a small grid of image tiles before reading. The model reads best this way, and it keeps CPU time down.
- Tables come out as rows of `cell | cell` text.

## English only

OCR is enabled for **English only**. In testing, the model sometimes changed numbers on Persian pages without any sign of error. A wrong number in a cited answer is worse than no answer, so:

- A page whose OCR text is mostly Persian or Arabic script is **not indexed**.
- A page where the model gets stuck repeating itself, re-reads the same long line twice, hits its output limit, or returns nothing for a printed page is **not indexed**. On very dense pages of near-identical lines, the model can lose its place; this check catches that instead of indexing misread numbers. A page with only a single line of text usually comes back empty and is reported the same way.
- The document is still published with its other pages. The document card shows a note naming the skipped pages, for example *"OCR skipped page 2: OCR supports English only, so that page was not indexed."* Upload a text version of those pages if they matter.

For Persian scans, use a text-based PDF or DOCX. Details are in [OCR-EVALUATION.md](OCR-EVALUATION.md).

## Speed and hardware

| Where OCR runs | Time per page (measured on an 8-core laptop) | Memory |
|---|---|---|
| CPU (default) | about 35 seconds for a page with a few paragraphs, up to about 2½ minutes for a dense full page | about 5–6 GB RAM while reading |
| GPU (`ocr_gpu_layers` set to 99) | about 1–8 seconds | about 5 GB of GPU memory |

OCR runs on the **CPU by default**, because on an 8 GB GPU it cannot fit next to the chat model. If the GPU has room (16 GB or more, or a cloud chat model), set `"ocr_gpu_layers": 99` in `config/server.json` and restart.

Indexing shows progress per page ("Reading scanned page 3 of 40 with OCR"), and you can stop it between pages. The OCR runtime starts when it is first needed (a few seconds) and stops itself after two minutes without work, which frees its memory. It runs as its own process on `127.0.0.1:18196` and logs to `data/ocr-runtime.log`.

## Settings (`config/server.json`)

| Key | Default | Meaning |
|---|---|---|
| `ocr_enabled` | `true` | OCR on or off (also set from Documents) |
| `ocr_gpu_layers` | `0` | `0` = CPU; `99` = GPU |
| `ocr_threads` | `0` | CPU threads; `0` = about half the logical cores, at most 8 |
| `ocr_max_pages` | `200` | Most scanned pages read per document; split larger files |
| `ocr_max_side` | `1600` | Rendering size for PDF pages before they are cropped and tiled |
| `ocr_max_tokens` | `2048` | Output limit per page; a page that reaches it is treated as unreadable |
| `ocr_page_seconds` | `300` | Time limit per page |
| `ocr_idle_seconds` | `120` | Stop the OCR runtime after this much idle time |
| `ocr_port` | `18196` | Loopback port of the OCR runtime |
| `ocr_model`, `ocr_projector` | `assets/ocr/…` | Model files |

Restart the server after changing these values.

## Files and checks

- Model files: `assets/ocr/unlimited-ocr-Q4_K_M.gguf` (1.95 GB) and `assets/ocr/mmproj-unlimited-ocr-bf16.gguf` (0.83 GB). Their source revision and checksums are in `assets/ocr/provenance.json` and `assets-manifest.json`. If they are missing, OCR shows as not installed and everything else works as before.
- `CHECK-INSTALL.bat` reports whether the OCR model is present and verifies its checksums.
- `runtime\python.exe tools\smoke_ocr.py` (add `--gpu` to use the GPU) runs a real OCR check on generated English pages in a temporary copy. Customer documents are not touched.
- PDF pages are rendered with pypdfium2 (PDFium, BSD/Apache licences) and images are handled with Pillow. Both are included in `runtime`.

## Limits

- Accuracy was measured on synthetic English pages: clean text, simulated scans and phone photos. Check a sample of your own scans before relying on OCR. Handwriting, stamps and very poor copies were not tested.
- OCR text is only as good as the scan. Citations always point to the original page, so a reader can open it and check.
- One page is read at a time, alongside answering. On the CPU, heavy OCR can slow answers slightly.
