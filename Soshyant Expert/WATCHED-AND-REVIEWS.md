# Watched folders and answer quality review

Restart the existing server once and refresh the browser. Sign in as an administrator to see **Watched folders** and **Answer review**. Existing accounts, documents, conversations and model settings are retained. The database adds tables automatically; older backups still open through the current application.

## Watched document folders

Choose a folder using the built-in server folder browser, or enter its path. This is a folder on the computer running Soshyant, even when you use a browser on another computer. Choose whether to include subfolders and select **Add folder & scan**.

The server checks enabled folders every minute while it is running. **Scan now** checks immediately; **Pause** stops automatic monitoring, while manual scanning remains available. There is no Windows scheduled task or cloud monitoring service.

Scanning discovers supported documents and their changes. It does not import text into the knowledge library or call a language model. Changes appear for administrator review. **Ignore this version** suppresses the current file fingerprint until the file changes again.

**Review & approve** asks for confirmation before copying and indexing that exact file version. A file changed since the scan is rejected until scanned again. Replacement content is indexed privately first, then published in one transaction under the same document identity with an increased version. The previous file is retained as a revision for existing citations. Indexing failure or cancellation before publication preserves the previously published document and its searchable passages. Temporary indexing documents are excluded from the library and archive list.

Missing source files stay in the knowledge library. The administrator can explicitly approve **Archive document**, or ignore that missing-file notice. Archiving is reversible through Documents. An incomplete scan or an unreadable source folder does not infer that documents were deleted. Manually modified, archived or deleted library documents are not automatically overwritten or restored by monitoring.

Monitoring supports local PDF, DOCX, XLSX, TXT, Markdown and HTML files, plus scanned images (PNG, JPG, TIFF). When OCR is on, scanned English pages are read after you approve a file ([OCR.md](OCR.md)); scanned Persian pages are not indexed. Linked files/directories and network shares are excluded. Choose a dedicated document folder outside the application's data directory and its ancestors. Limits are 20 registered folders, 1,000 supported files / 20,000 entries / 256 MiB read per folder scan, and the configured per-document upload limit. A limited scan records an error and does not infer missing files; use smaller folders.

Folder registrations, fingerprints and approved source mappings are in the local database and included in database backups. Source folders themselves are not copied by backup: only documents explicitly approved into the library are included. Restoring on another computer may leave folder paths unavailable; monitoring records the error rather than removing knowledge.

## Answer quality review

Administrators can review saved answers with insufficient evidence, clarification requests and feedback from users. The screen shows the original question, answer, supporting citations if present, feedback notes, account name and date. It does not grant access to arbitrary whole conversations. Normal users cannot access the review API, and the phone gateway does not expose these administrative endpoints.

Filter by answer category and **Open**, **Resolved** or all review statuses. Record a resolution note and save the decision. For example, note which document needs updating or which topic needs a new authoritative source. A new feedback submission reopens a resolved item. The page loads up to 50 answers at a time, with **Load more** for older items. Draft notes survive language changes and in-app navigation in browser memory; save them before reloading or signing out.

Resolving an item does not train the model, change prompts or publish knowledge. Make actual knowledge changes through Documents or approve a watched-folder change. Deleting a conversation removes its review records together with its messages and feedback. Existing backups can still contain those records.

The desktop chat explains that administrators can review answers needing attention and submitted feedback. Companies should account for this administrator visibility when setting their internal data-retention and access policies. Document/group permissions now apply to the library; administrators retain access to all documents. See ACCESS-CONTROL.md.
