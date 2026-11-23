# Optional local voice input for the web application

Administrators: open **Maintenance & account → Local speech input**, enable voice input, and save. If the module is not installed, run **SETUP-SPEECH.bat** on the server first; this one-time setup requires internet. Restart an already running application after updating its code. Dictation supports **English only**, independently of whether the interface is English or Persian.

In Chat, press the **microphone icon beside Send** and start speaking. Recording progress, **Stop recording**, and **Cancel** appear inside the same composer. Stop when finished; the transcript is appended directly to the existing question. Review/edit it there and press Send normally. There is no dialog, separate editor, file picker, or Insert step. Existing draft text is preserved. Nothing is submitted to the answering model automatically. Recordings are limited to 30 seconds; the recording timer stops slightly earlier to allow for browser timing/encoding overhead.

Microphone recording requires a browser secure context: `http://localhost:8095`, `http://127.0.0.1:8095`, or a correctly configured HTTPS deployment. Plain HTTP on a LAN IP does not grant microphone access. Microphone permission is requested only when the mic icon is pressed. Canceling, switching chats/sections, or leaving the page stops recording and prevents a late transcript from appearing in another chat. There is no browser/cloud speech recognition service. Sending is temporarily blocked during recording/transcription.

## Local processing and privacy

The browser converts the recording to mono 16 kHz PCM16 WAV and submits it to the authenticated local server. The server validates the format, duration and size before inference. Audio is held in memory, not written to application files or the database. Transcripts are held in memory for at most five minutes after the job finishes; retrieving them into the editor consumes/deletes the server copy. Cancellation removes the result and terminates a running child process. A transcript only becomes ordinary chat data if the user sends it as a question.

The feature has a separate queue: one running transcription and up to two waiting. A user can have one pending transcription. Jobs/results/cancellation are restricted to their owner; writes require the existing CSRF token. No audio or transcript is included in server diagnostic messages. All model files and NVIDIA processor/generation configuration are loaded from explicit local paths with offline mode enabled; the isolated speech process also rejects Python socket connection/DNS/send events. This is not an OS firewall boundary. This does not turn an API-backed answering model into an offline model: sending the final question still follows the selected LLM provider policy.

## Installation and hardware

`speech-runtime/` is separate from the existing RAG Python runtime. The setup tool copies the local Python standard library and installs the repository's dependencies plus a CPU PyTorch wheel into that separate folder. `assets/speech/` contains the pinned Bark weights/loader, attribution, local NVIDIA processor files, and `READY.json` recording source revisions and SHA-256 hashes. Existing LLM, OCR, accounts and documents are not replaced. Keep the runtime and assets together when copying this installation.

The supplied setup installs **CPU support**. CUDA selection requires provisioning a compatible CUDA-enabled PyTorch installation in the separate speech runtime first. Selecting CUDA on a CPU-only installation fails explicitly; it does not silently use another device. CPU is the initial default so speech does not compete for the laptop's limited GPU memory with the chat/OCR models. Speech adds RAM/CPU load and is **not included in the existing hardware planner**. The 163 MB model download is not a memory requirement; the Windows loader expands weights to FP32. Measure performance under the actual workload before promising concurrent-user capacity.

For the first version, a separate inference process loads the model for each transcription and exits afterwards, releasing memory. Cold-loading is slower than a persistent service but avoids retaining several GB alongside the LLM/OCR. A job has a 180-second processing timeout. This is short-recording dictation, not a live streaming call or text-to-speech.

## API

- `GET /api/speech`: signed-in availability, enabled/device/language/limit.
- `POST /api/speech/settings`: administrator + CSRF; `{ "enabled": true, "device": "cpu" }`.
- `POST /api/speech/transcribe`: signed-in + CSRF, raw mono 16 kHz PCM16 WAV; returns a job ID.
- `GET /api/speech/jobs/{id}`: owner-only status and completed transcript.
- `POST /api/speech/jobs/{id}/cancel`: owner + CSRF, `{}`; cancels/discards the result.
- `POST /api/speech/jobs/{id}/consume`: owner + CSRF, `{}`; deletes a finished result.

The Android/Wi-Fi gateway has not been expanded; this feature is for the web application.

## Model attribution

Underdog Bark 3.0 by ConwayResearch, derived from NVIDIA Parakeet through moondream/parakeet-ultra. The model is published under CC-BY-4.0. Preserve `assets/speech/NOTICE` and the model attribution with distributions. Source: https://huggingface.co/ConwayResearch/Underdog-Bark-3.0 . Dependency licences remain applicable separately.

Validation uses synthetic audio and disposable application data. Physical microphone behavior depends on the user's browser/device and still requires a user acceptance recording; synthetic audio is not proof of accent/noise/domain vocabulary accuracy.

### Validation on 23 October 2026

All 111 regression tests passed; the six focused speech tests passed again after the retention correction. Real CPU inference with Python network events blocked transcribed the synthetic question as `how long is the warranty for the aurora pump` in **47.23 seconds including cold loading**. In the disposable web preview, selecting that recording returned the real transcript, editing/inserting preserved an existing draft, and no question was sent until an explicit Send. The subsequent RAG answer in that preview used its simulated answering model and real sample retrieval. English/Persian labels and saving speech settings were checked in the browser. No user's microphone or production documents were accessed. Evidence: `qa/speech-2026-10-23/validation.json` and screenshots. These measurements are not a concurrent-user capacity guarantee.

The later composer-only revision removes the dialog/file editor described in the initial validation. Four JavaScript interaction tests cover inline recording → transcript, late microphone permission after cancellation, late transcription after cancellation, and preserving overlong text with a validation error. Those tests use simulated browser audio APIs; physical microphone acceptance is still separate.
