# Windows launcher and knowledge overview

Double-click **Soshyant Expert.exe** in this folder. No command window is required. The executable is a small Windows launcher; keep the full application folder, including `runtime`, `assets`, `config` and `data`, together.

## Daily use

1. Choose **Start server**, then **Open application**. Opening the application also starts the server if needed. The authenticated interface opens in your default browser.
2. Closing the launcher window leaves it in the system tray. Double-click the tray icon to show it again. **Exit** in its menu offers to stop a server started by the launcher before closing.
3. **Stop server** sends a local shutdown request and waits for cleanup. It controls only the child process started by this launcher. If the server was started with `START.bat`, stop it in that original window first; the launcher reports that state and leaves it alone.
4. **Phone / Wi-Fi access** opens the existing interactive Wi-Fi gateway launcher. That gateway remains a separate process/window. **Phone connection details** opens its generated connection file. A running gateway cannot serve answers while the main server is stopped.
5. **View server log** opens `data/desktop-server.log` for the launcher-owned server. Logs roll over at the next launch once they exceed 2 MiB. The first-admin code shortcut works only before initial account setup.

After updating from the command-window version, stop the main server in its existing window and use the new launcher. Refresh the browser to load the new interface. Your existing accounts, documents and configured model are preserved.

## Administrator overview

Administrators land on **Overview** after signing in. It shows active/indexed/archived documents, searchable passages, queued and running work, active accounts, knowledge version, the selected model, local backup count and the latest backup time. Failed and pending documents appear in an attention list. Links open the existing document/model/backup screens.

The overview refreshes every 20 seconds while visible, or manually with **Refresh overview**. Model availability reflects the local file or configured API connection; it does not make a paid provider request or verify answer quality. Backup times reflect files present in this installation's backup folder. The administrative API is authenticated, role-restricted and excluded from the phone gateway.

## Conversations

Search conversation titles from the sidebar. Rename or delete from each row or the current chat toolbar. Permanent deletion requires confirmation and is blocked while the conversation has pending generation. It removes owned messages, feedback and saved answer-job copies; pre-existing backups and exported/shared copies remain. Copy, feedback and text export remain available on the desktop. Message times follow your browser's locale/time zone.

## Build and verification

`desktop/BUILD-LAUNCHER.ps1` compiles the C# source using the Windows .NET Framework compiler. No external launcher dependency is downloaded. The current executable is a locally built, unsigned pilot application, not a signed Windows installer.

The server tests include a real isolated hidden-host startup, health check and graceful shutdown. The dashboard's authentication, role boundary and actual document/job counts are tested. The native launcher window and English/Persian web interface were inspected. No production chat or document was deleted for testing.

## Remaining roadmap

This is the first desktop usability milestone. Watched folders with approved updates and answer-quality review are now implemented; see [WATCHED-AND-REVIEWS.md](WATCHED-AND-REVIEWS.md). Document/group permissions are now implemented; see [ACCESS-CONTROL.md](ACCESS-CONTROL.md). Scheduled backups and graphical restore, measured hardware telemetry, and a distributable offline installer/update bundle remain separate work. The library now supports document access groups; administrators retain access to every document.
