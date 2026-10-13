# Soshyant Assistant

A **fully local, private AI assistant** for company wikis, manuals, and documents:
voice + text chat with **retrieval-grounded answers** (RAG) that cite their sources —
everything runs on your own machine. No cloud, no API keys, no data leaving the building.

![stack](https://img.shields.io/badge/stack-llama.cpp%20%7C%20Kokoro%20%7C%20Whisper%20%7C%20fastembed-blue)

## What it does

- **Ask your documents** — flip the 📚 *docs* toggle and the assistant answers
  strictly from an indexed document folder (TXT, MD, PDF, DOCX, XLSX, HTML),
  citing the file and page/sheet for every claim. When the documents don't
  contain the answer, it says so instead of guessing.
- **Talk to it** — 🎤 microphone button (speech-to-text, English) and every
  answer is spoken aloud (28 English voices).
- **Swap brains** — four local LLMs in a dropdown; only one fits in an 8 GB GPU
  at a time and the app switches them automatically.

## Quick start (Windows, NVIDIA GPU)

```powershell
git clone <this-repo> Soshyant
cd Soshyant
powershell -ExecutionPolicy Bypass -File setup.ps1
start-soshyant.bat
```

Then open **http://127.0.0.1:8091**. The first sync downloads ~4.5 GB
(llama.cpp runtime, Kokoro TTS, Whisper STT, and the default LLM
**Bonsai-2-27B** — a 27B ternary model at ~19 tokens/s on an RTX 3070).

### Optional models

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1 -Models huihui4b,ornith,gemma4
```

| Model | Size | Why pick it |
|---|---|---|
| 🌱 **Bonsai-2-27B** *(default)* | 5.6 GB | Best quality; strictest document grounding |
| 🐰 Huihui-4B · light | 2.5 GB | Fastest answers; uncensored |
| 🐦 Ornith-1.5-9B | 5.4 GB | Fast + image input (vision) |
| 🧩 Gemma4-26B MoE | 15.6 GB | 26B MoE with vision; GPU+RAM hybrid |

Only one LLM fits in an 8 GB GPU at a time — the app stops/starts them
automatically when you switch. All of them are abliterated/uncensored community models.

## Using your own documents

1. Flip **📚 docs** on in the header.
2. Paste your document folder path into the second bar and press **🔄 sync** —
   the app chunks, embeds (local, private), and indexes it (progress bar included).
3. Ask questions. Answers cite `[1] [2]` with the file and page/sheet shown
   under the reply. Questions the documents can't answer get an honest
   *"I don't find that in the documents I have."*

Keep the folder in sync: re-press 🔄 sync (incremental — only new/changed files
are re-embedded), or run `start-rag-watch.bat` to auto-index changes every 30 s.

## Architecture

```
browser ──SSE──> bonsai_web.py (Python stdlib server)
                   ├─ llama.cpp (Prism build, CUDA)  ← 27B/9B/26B GGUF models
                   ├─ faster-whisper base.en          ← microphone (STT)
                   ├─ Kokoro-82M ONNX                 ← spoken answers (TTS)
                   └─ rag_store (fastembed + numpy)   ← document index (RAG)
```

No framework, no vector-database server: the RAG index is transparent
(`rag_db/` — JSONL chunks + numpy matrices) so you can inspect exactly what
the assistant knows.

| File | Role |
|---|---|
| `bonsai_web.py` | web server, chat, voice, RAG wiring (port 8091) |
| `bonsai_voice.py` | speech normalizer (markdown → natural prose), TTS speaker, server manager |
| `rag_store.py` / `rag_ingest.py` / `rag_watch.py` | document index + incremental sync + folder watcher |
| `setup.ps1` | one-command install of everything this repo doesn't ship |

## Requirements

- Windows + NVIDIA GPU (8 GB VRAM tested; models run CPU+RAM hybrid on bigger jobs)
- Python 3.11+
- ~10 GB disk for the default install (more for optional models)

## License & model notices

Application code: Apache-2.0. The downloaded models carry their own licenses
(Bonsai/Ornith/Huihui/Gemma community releases — all uncensored variants; use
responsibly and check each model card before commercial deployment).
