# Bundled asset provenance

The language model and llama.cpp runtime were copied from the existing local Soshyant installation, without modifying their contents. The language model is `Ternary-Bonsai-2-27B-Abliterated-PTQ1_0.gguf` from the original project's configured BoldingBuilds distribution. Consult the original model distribution for all model and base-model terms:

- https://huggingface.co/BoldingBuilds/Ternary-Bonsai-2-27B-Abliterated-PTQ1_0-GGUF
- https://github.com/PrismML-Eng/llama.cpp

The multilingual embedding assets were downloaded at preparation time from:

- https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q

The downloaded model revision is recorded in `assets/embeddings/provenance.json`.

The English OCR model (`assets/ocr`) is Baidu's Unlimited-OCR (MIT licence), in the GGUF conversion published for llama.cpp's Unlimited-OCR support. Source revision and checksums are in `assets/ocr/provenance.json`:

- https://huggingface.co/baidu/Unlimited-OCR
- https://huggingface.co/sabafallah/Unlimited-OCR-GGUF

PDF pages are rendered for OCR with pypdfium2 and the PDFium library it bundles (Apache-2.0/BSD-3-Clause), and images are handled with Pillow (MIT-CMU). Both are in `runtime/Lib/site-packages` with their licence files. Installed Python distributions retain their bundled license files and copied distribution metadata under `runtime/Lib/site-packages`. The Python runtime includes its original license. This project does not grant additional rights to third-party models, runtimes, dependencies or customer documents. Original asset SHA-256 checksums are in `assets-manifest.json`.
