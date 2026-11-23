# Product reality check — 18 October 2026

**Verdict: NEEDS WORK before general customer deployment.** The product has demonstrably working application flows and automated protections. This assessment supports continuing a controlled pilot; it does not certify production readiness, domain expertise, offline installation on another computer, or a concurrent-user capacity.

## Scope and method

Applied the user-supplied `C:/Users/asus/Desktop/testing-reality-checker.md`. Reviewed the current standalone Windows server and Android client, reran checks, inspected a disposable browser preview, and ran two additional isolated probes. No production account, document, model selection, or application source was changed. This folder contains assessment artifacts only.

The skill's Laravel/Linux commands were adapted to this Windows/Python application: inspected `web/index.html` and CSS; searched HTML/CSS for luxury/premium/glass/morphism claims (none found); inspected existing verification documents; used the supported browser automation to exercise the current UI and capture three viewport sizes. The prescribed `qa-playwright-capture.sh` and pre-existing `test-results.json` were not found in the product directories. No claim is made that that script ran. The JSON in this folder records this assessment's actual results.

## Fresh verification

| Check | Result | What it proves / does not prove |
|---|---|---|
| `runtime/python.exe -m unittest discover -s tests -v` | **105 passed**, 129.982 seconds | Includes authentication, CSRF, ownership, permissions/revocation, document revisions, queues, cloud stubs, model activation, OCR extraction guards, watched folders and review workflows. Most generation tests use simulated models. |
| `runtime/python.exe manage.py check --full` | **Passed** | Bundled dependencies, 384-dimensional local embeddings, OCR assets and manifest checksums work on this laptop. Does not prove another machine or physical network isolation. |
| Android `tools/test_client.py` | **Passed** | Exact Java API transport exercised against temporary HTTPS gateway: certificate/hostname checks, cookies, CSRF, questions, jobs, citations, history, rename/delete, feedback, logout and gateway boundaries. Does not exercise Android screens or lifecycle. |
| Browser sign-in → new chat → question → source expansion → rename | **Passed in preview** | Real interface/server/retrieval with synthetic documents and a simulated answer model. Source text and versioned download link displayed. Download click itself was not tested. |
| English → Persian | **Passed for interface switching** | RTL and translated controls observed. Existing answers are retained in their original language. Not a Persian model-quality test. |
| Browser console | No captured warnings/errors during tested journey | Limited to this browser and these actions. |
| Local static HTTP responses | 1.78–27.49 ms across 15 requests | Response-body transfer on localhost only; not page rendering, Wi-Fi, cold start, model response time, or a load benchmark. |

The earlier claim of 105 passing tests was independently reproduced. Prior real-model and OCR quality claims were **not** re-certified by those tests.

## Findings, in priority order

### 1. High: a valid citation does not establish that the answer is supported

**Reproduced limitation.** The source said the warranty was **36 months**. An injected simulated model response said **999 months [1]** and supplied citation `[1]`. The actual Engine accepted and saved it with status `answered`, alongside the contradictory source text. See `probe-results.json` and reproducible `probe.py`.

This was a deliberately bad model stub, **not evidence that the selected Ornith model produced this error**. It establishes that the publication checks validate citation structure and source identity but do not independently validate factual support. Relevant code: `expert/engine.py`, response checks around lines 191–218.

**Impact:** the UI's “Grounded answer” label can appear on a false claim if the LLM supplies a syntactically valid reference. Existing citation tests do not demonstrate factual accuracy.

**Next action:** build an expert-reviewed acceptance set for each installation, including missing evidence, conflicting versions, numerical contradictions and adversarial document text. Add targeted consistency checks and review/abstention rules for important claims. Adjust the label/help text to avoid implying that citation presence certifies correctness. Neither another LLM checker nor a numeric heuristic alone guarantees truth.

### 2. High: the backup is a data backup, not complete server recovery

**Reproduced scope gap.** A newly generated backup contained exactly `expert.sqlite`, `domain.json`, and `manifest.json`. It omitted server configuration and saved API-model connections; model files, model inventory and phone TLS material are also outside that archive. See `expert/backup.py:20` and `probe-results.json`.

The existing database restore test passed. This finding does **not** mean document backups are broken. It means the archive alone cannot reconstruct the configured service after laptop loss. Scheduled backups and graphical restore are explicitly still on the desktop roadmap.

**Next action:** define a complete recovery package and separate credential recovery/re-entry policy; add scheduled backups, a guided restore, and a fresh-machine restore drill. Do not assume Windows account-bound encrypted API keys become portable by copying them.

### 3. High for a multi-user sale: capacity is unproven and serving is serial

**Confirmed implementation limit.** `expert/engine.py:28` creates one answer queue and one answer worker. The configured queue holds eight waiting jobs. Multiple users can connect, but this does not mean multiple answers generate concurrently. The planner itself declares `current_generation_slots: 1` and `speed_guaranteed: false`.

The hardware planner uses a fixed Bonsai/Qwen catalog. The configured local model is **Ornith-1.5-9B-Q4_K_M.gguf**, which is not represented by that catalog. Its formulas have no explicit OCR workload input/reservation, while OCR is now part of the product. It is not a validated sizing tool for this complete current deployment.

**Next action:** benchmark the selected model at representative prompt lengths and simultaneous requests, including OCR ingestion. Record queue time, first-token/total latency, throughput and peak RAM/VRAM. Connect planning to supported model metadata and ingestion assumptions. Add controlled parallel inference only if measured demand warrants it; buying additional GPUs does not change the current worker design.

### 4. Medium: the English mobile web header overflows

**Reproduced at 375 × 667.** The content viewport was 360 px wide after its scrollbar; document scroll width was 367 px. Header controls reached x=366.625, beyond the header's right edge at 360. The header grew to about 204 px, wrapping the title into short lines and clipping the sign-out area. The initial screen devoted most of its height to navigation and the header. See `responsive-mobile.png`, `rename-after-mobile.png`, and `browser-results.json`.

The 768 × 1024 and 1920 × 1080 tested views had no whole-document horizontal overflow. Persian mobile had no whole-document overflow in the measured state. **This is a browser layout finding, not an Android native UI finding.**

**Next action:** use a compact small-screen header, wrap or collapse account controls, and reduce navigation height. Recheck at 375 px with long usernames and both languages.

### 5. Deployment acceptance is still missing

**Evidence gaps, not reproduced runtime failures:**

- No fresh-machine, physically disconnected installation was performed. The current selected model exists outside the product folder at an absolute path; simply copying the folder will not carry that selected model/configuration to another laptop. See `http-results.json`.
- The latest Android 1.1 UI has no fresh physical-device acceptance evidence in this assessment. Host-side transport tests do not prove rotation, app backgrounding, reconnection, keyboard behavior or accessible layout.
- Real provider requests were not made. API integration passed stubs, not a paid live-provider acceptance test.
- The selected real LLM was not run against a scored domain evaluation in this assessment. There is no basis here to certify it as a domain expert.
- OCR assets and unit tests passed. Actual customer scan accuracy, mixed languages, handwriting and concurrent ingestion/answer latency were not measured. Persian scan rejection is a documented intentional limitation.
- The launcher remains an unsigned pilot; the Android APK uses a pilot signing identity. The offline installer/update bundle remains unfinished.

**Next action:** require a repeatable customer acceptance checklist: clean offline install, complete restore, real-device Android journey, representative scanned documents, and the chosen model's scored questions. Test an actual API provider separately only when that mode is required and approved data/key are available.

## Visual evidence and its limits

- `responsive-desktop.png`: overview at requested viewport 1920 × 1080.
- `documents-desktop.png`: indexed sample library and upload controls.
- `chat-before.png` / `chat-after.png`: empty chat versus answer with expanded evidence.
- `responsive-tablet.png`: chat at 768 × 1024.
- `responsive-mobile.png`: English chat at 375 × 667, including header problem.
- `rename-after-mobile.png`: renamed test conversation and crowded English header.
- `persian-mobile.png`: translated RTL interface.

All screenshots show the **temporary preview**, not customer data. Large images are softened by the screenshot tooling, so they are insufficient to judge typography sharpness. These are viewport captures, not full-page captures. Requested viewport dimensions were independently checked in the DOM; the screenshot tool returned image files at **1905 × 1072**, **753 × 1004**, and **360 × 640**, respectively, rather than exact full-viewport pixel dimensions. That limits compliance with the skill's exact screenshot requirements. `login-before.png` was blank because of capture timing and is excluded from valid evidence. The preview does not remap OCR asset paths, so its missing-OCR message is a preview limitation; the actual installation asset check passed. Only one browser was tested. Browser page-load/paint time was not measured, so the skill's three-second browser-load target remains unverified. Slow OCR/generation is not treated as a page-load failure.

## Recommendation

Continue the pilot with a defined user group and measurable acceptance criteria. Before general customer rollout, prioritize (1) factual-answer evaluation and honest labels, (2) complete recovery and offline deployment, (3) measured capacity for the actual configured model and ingestion workload, then (4) mobile layout and latest Android device acceptance. These are release gates, not an assertion that every existing feature is broken.

No numerical quality score, completeness percentage, or completion date is assigned: the available evidence does not support one. Reassess after the fixes and acceptance drills.
