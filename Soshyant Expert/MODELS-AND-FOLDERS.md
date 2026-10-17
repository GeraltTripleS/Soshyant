# Local model selection and folder imports

## Choose the actual answering model

Sign in as an administrator and open **Language models**. One panel contains the folder selector, discovery results, model dropdown, active model, and activation feedback.

1. Press **Choose folder…**. The built-in folder browser lets you select a local drive, enter subfolders, or move up to a parent. These are folders on the server computer. Alternatively enter a folder's full path in the same panel; pasted paths surrounded by quotes are accepted.
2. Press **Use this folder & scan**, or **Scan folder** after entering a path. Subfolders are included by default and can be disabled. Model files remain in place; nothing is copied or downloaded.
3. The page displays discovered model count, invalid GGUF count, inaccessible subfolders, and scan limits. Empty or incorrect paths get an explicit result or error next to these controls. Choose a discovered model in the dropdown.
4. Press **Activate selected model**. The runtime must successfully load the model before the selection is saved. The service rejects switching while answers are pending and rejects new questions while activation runs. Only its own model process is stopped.

The active model always remains listed, including if it is outside the chosen folder. Previously registered individual models remain accessible for compatibility. The latest scanned folder and discovered paths are saved in `data/model-folder.json`; scan again after adding files. A scan inspects at most 20,000 directory entries and discovers at most 200 models; it reports truncation so you can choose a smaller folder. Symlinks, Windows reparse points and network shares are skipped/rejected. Only local drives are offered in the browser. File-header validation identifies GGUF candidates, not runtime compatibility.

Activation can take up to three minutes. On success `model_file` is persisted atomically in `config/server.json` and survives restart. On failure the previous selection remains and reloads on the next question. GPU/context settings and the retrieval model do not change. Existing conversations and indexed documents remain available. The runtime log is in `data/model-runtime.log`.

A health check proves loading, not answer quality. Architecture, quantization, memory, chat-template support, and the application's citation/language requirements still need verification for a newly supplied model. Model weights, folder selection, legacy registrations, and server settings are not included in data backups; preserve them separately.

## Import a folder into the knowledge library

Open **Documents → Add a document folder** as an administrator and select a folder through the browser. This selects a folder on the **browser computer**, even when the server is another machine on the LAN. Supported file contents are copied to this installation, like individual uploads. Files are never uploaded to an internet service. A browser may show its standard confirmation for a folder selection.

Subfolders are included by default; uncheck **Include subfolders** to use only files directly in the chosen folder. The page shows selected and supported counts before import. Start with **Import & index folder**. Each file uploads and finishes indexing before the next begins, so a large collection does not fill the bounded indexing queue. Relative names are preserved as source titles; original filenames remain simple filenames.

- PDF, DOCX, XLSX, TXT, Markdown, HTML and scanned images (PNG, JPG, TIFF) are accepted. Scanned English pages are read with local OCR when it is on; see [OCR.md](OCR.md).
- At most 1,000 selected files are accepted per import. The configured per-file size limit and global knowledge chunk limit still apply.
- Identical content already indexed in an active document is skipped using a SHA-256 comparison. A changed file is added as a new source; folder import does not infer document revisions from filenames. Use **New version** for deliberate replacement.
- A failed file does not stop the remaining collection. The per-file report shows successful, duplicate, unsupported, and failed entries.
- **Stop after current file** retains completed work and stops before starting another file. It does not delete imported sources or cancel the current server-side indexing job.
- Reimporting the same folder skips indexed content and can retry pending/failed content. Interrupted network requests may leave a pending source; the library's **Reindex** action can recover it.
- This is an explicit one-time import, not a folder watcher or bidirectional sync. The browser page must remain open. Original local files are not changed.

The illustrative folder in `examples/import-folder` contains deliberately fictional test data, a duplicate, a nested document, and an unsupported format. It is never imported automatically into the real installation.

## Verification

Automated tests cover administrative access, rejection of new answers during activation, local registration and GGUF validation, busy-state checks, successful persistence, rollback, folder ingestion, and deduplication. `tools/smoke_model_selection.py` additionally activates the real bundled model using temporary configuration, verifies rollback after an invalid model, and confirms that the previous model reloads. This does not modify the real installation's selected model or knowledge.


## Delete an archived document

Administrators can enable **Show archived** in Documents and choose **Delete permanently** beside an archived source. A confirmation dialog names the document and explains the scope; Cancel and Escape leave it intact. The server requires an administrator session, CSRF token, explicit confirmation, and an archived document, even if a client bypasses the UI.

Deletion transactionally removes the document blob, all stored file revisions, and its index chunks, then advances the knowledge version. It cannot be undone through Restore. Saved answers may retain source excerpts and previous backups retain their historical copies. This is logical deletion from the application, not a guarantee of secure erasure from SQLite free pages, storage media, or backups. No existing user document is automatically deleted by this update.

Models can remain in any local directory or drive on the server: choose their folder in **Language models** and scan it. No fixed model directory is required and scanning does not copy or move the model. If browser and server are different machines, the path refers to the server.
