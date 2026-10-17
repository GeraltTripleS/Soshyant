"""Bounded local folder discovery and explicit, staged document publication."""
import hashlib
import os
from pathlib import Path
import threading
import time
import uuid

from .knowledge import EXTENSIONS


class WatchedFolders:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        # A previous process cannot still own these staging documents (instance lock).
        for row in self.store.rows('SELECT id,stage_id FROM watched_files WHERE stage_id IS NOT NULL'):
            self.cleanup(row['id'], row['stage_id'], 'Interrupted update. Scan and approve again.')

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)

    def loop(self):
        while not self.stop.wait(60):
            for folder in self.store.rows('SELECT id FROM watched_folders WHERE enabled=1'):
                if self.stop.is_set():
                    return
                try:
                    self.scan(folder['id'])
                except (ValueError, OSError):
                    pass  # Error is retained on the folder, without document content.
                except Exception:
                    self.store.execute('UPDATE watched_folders SET error=? WHERE id=?',
                                       ('Automatic scan failed. Try Scan now.', folder['id']))

    def path(self, value):
        path = self.app.models.local_path(value)
        if not path.is_dir():
            raise ValueError('Choose an existing local folder on the server.')
        data = self.app.config.data.resolve()
        if path == data or path in data.parents or data in path.parents:
            raise ValueError('Choose a document folder outside the application data directory and its parents.')
        for part in (path, *path.parents):
            if part.is_symlink() or getattr(part.stat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Choose a folder without linked directory components.')
        return path

    @staticmethod
    def checked(root, relative):
        candidate = root / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Invalid document path.')
        for part in (candidate, *candidate.parents):
            if part.is_symlink() or (part.exists() and getattr(part.stat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError('Linked folders and files are not monitored.')
            if part == root:
                break
        if not candidate.resolve().is_relative_to(root.resolve()):
            raise ValueError('Document is outside the watched folder.')
        return candidate

    def read(self, root, relative):
        file = self.checked(root, relative)
        limit = self.app.config.settings['max_document_mb'] * 1024 * 1024
        before = file.stat()
        if not file.is_file() or not 0 < before.st_size <= limit:
            raise ValueError('Document is empty or exceeds the upload limit.')
        with file.open('rb') as stream:
            body = stream.read(limit + 1)
        after = file.stat()
        if len(body) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Document changed while reading. Scan again after saving it.')
        return body, hashlib.sha256(body).hexdigest()

    def add(self, data):
        if not isinstance(data.get('recursive', True), bool):
            raise ValueError('Choose whether to include subfolders.')
        if not isinstance(data.get('restricted', False), bool):
            raise ValueError('Choose the initial document access.')
        path = self.path(data.get('path'))
        identity = uuid.uuid4().hex
        with self.lock:
            if self.store.one('SELECT count(*) AS n FROM watched_folders')['n'] >= 20:
                raise ValueError('Up to 20 watched folders are supported. Use dedicated document folders.')
            if self.store.one('SELECT id FROM watched_folders WHERE path=?' + (' COLLATE NOCASE' if os.name == 'nt' else ''), (str(path),)):
                raise ValueError('This folder is already watched.')
            self.store.execute('INSERT INTO watched_folders(id,path,recursive,restricted) VALUES(?,?,?,?)',
                               (identity, str(path), int(data.get('recursive', True)), int(data.get('restricted', False))))
        return identity

    def scan(self, identity):
        with self.lock:
            folder = self.store.one('SELECT * FROM watched_folders WHERE id=?', (identity,))
            if not folder:
                raise ValueError('Watched folder not found.')
            found, errors, pending, visited, total = [], [], [], 0, 0
            try:
                root = self.path(folder['path'])
                pending = [root]
                while pending and not self.stop.is_set():
                    directory = pending.pop()
                    # Revalidate directories as well as individual files before opening.
                    self.checked(root, str(directory.relative_to(root)))
                    try:
                        with os.scandir(directory) as entries:
                            for entry in entries:
                                visited += 1
                                if visited > 20000 or len(found) >= 1000 or total > 256 * 1024 * 1024:
                                    raise ValueError('Scan limit reached (1,000 documents / 20,000 entries / 256 MiB). Choose a smaller folder.')
                                if entry.is_symlink() or getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400:
                                    continue
                                if entry.is_dir(follow_symlinks=False):
                                    if folder['recursive']:
                                        pending.append(Path(entry.path))
                                elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in EXTENSIONS:
                                    relative = str(Path(entry.path).relative_to(root))
                                    try:
                                        body, sha = self.read(root, relative)
                                        total += len(body)
                                        found.append((relative, sha, ''))
                                    except (OSError, ValueError) as exc:
                                        errors.append(relative + ': ' + str(exc)[:150])
                                        found.append((relative, '', 'File could not be read. Check size, permissions and whether it is still being saved.'))
                    except OSError:
                        errors.append('A subfolder could not be read. Missing-file detection was skipped.')
                if self.stop.is_set():
                    raise ValueError('Monitoring is stopping.')
            except (OSError, ValueError) as exc:
                self.store.execute('UPDATE watched_folders SET scanned=?,error=? WHERE id=?',
                                   (time.time(), str(exc)[:500], identity))
                raise ValueError(str(exc)) from exc
            with self.store.connect() as db:
                if not errors:
                    db.execute('UPDATE watched_files SET present=0 WHERE folder_id=?', (identity,))
                for relative, sha, error in found:
                    db.execute("INSERT INTO watched_files(id,folder_id,relative,sha,error) VALUES(?,?,?,?,?) "
                               "ON CONFLICT(folder_id,relative) DO UPDATE SET sha=excluded.sha,present=1,error=excluded.error",
                               (uuid.uuid4().hex, identity, relative, sha, error))
                db.execute('UPDATE watched_folders SET scanned=?,error=? WHERE id=?',
                           (time.time(), '\n'.join(errors)[:1000], identity))
            return self.catalog()

    def catalog(self):
        rows = self.store.rows('SELECT w.*,f.path,f.enabled,d.status AS document_status,d.active AS document_active,d.sha256 AS document_sha '
                               'FROM watched_files w JOIN watched_folders f ON f.id=w.folder_id LEFT JOIN documents d ON d.id=w.document_id ORDER BY f.path,w.relative')
        changes = []
        for row in rows:
            token = row['sha'] if row['present'] else 'missing'
            if row['stage_id']:
                kind = 'indexing'
            elif row['ignored_sha'] and row['ignored_sha'] == token:
                continue
            elif row['error']:
                kind = 'unreadable'
            elif not row['present']:
                if not row['document_active']:
                    continue
                kind = 'missing'
            elif row['document_id'] and row['document_sha'] is None:
                kind = 'deleted'
            elif not row['document_id']:
                kind = 'new'
            elif not row['document_active']:
                kind = 'archived'
            elif row['sha'] != row['approved_sha']:
                kind = 'conflict' if row['document_sha'] != row['approved_sha'] else 'changed'
            else:
                continue
            row['kind'] = kind
            changes.append(row)
        return {'folders': self.store.rows('SELECT * FROM watched_folders ORDER BY path'), 'changes': changes}

    def approve(self, identity, owner, sha, archive=False):
        with self.lock, self.app.import_lock:
            row = self.store.one('SELECT w.*,f.path,f.restricted FROM watched_files w JOIN watched_folders f ON f.id=w.folder_id WHERE w.id=?', (identity,))
            if not row or row['stage_id']:
                raise ValueError('Change is missing or already processing.')
            root = self.path(row['path'])
            file = self.checked(root, row['relative'])
            knowledge = self.app.engine.knowledge
            if not row['present']:
                if not archive or file.exists() or sha != 'missing':
                    raise ValueError('Confirm archiving a missing file, or scan again.')
                with knowledge.publication_lock:
                    target = self.store.one('SELECT * FROM documents WHERE id=?', (row['document_id'],))
                    if not target or not target['active'] or target['status'] != 'indexed' or target['sha256'] != row['approved_sha']:
                        raise ValueError('The published document changed. Review it in Documents before archiving.')
                    knowledge.archive(row['document_id'])
                return {'archived': True}
            try:
                body, actual = self.read(root, row['relative'])
            except OSError as exc:
                raise ValueError('The source file cannot be read. Check access and scan again.') from exc
            if sha != row['sha'] or actual != sha:
                raise ValueError('File changed since the scan. Scan again before approving.')
            if row['document_id']:
                target = self.store.one('SELECT * FROM documents WHERE id=?', (row['document_id'],))
                if not target:
                    raise ValueError('The published document was deleted. Ignore this change or add the file manually.')
                if not target['active'] or target['status'] != 'indexed' or target['sha256'] != row['approved_sha']:
                    raise ValueError('The library document changed or is unavailable. Resolve it in Documents before approving.')
                if actual == row['approved_sha']:
                    raise ValueError('This version is already published.')
            if file.suffix.lower() not in EXTENSIONS:
                raise ValueError('Choose a supported document.')
            stage, now = uuid.uuid4().hex, time.time()
            # The draft and its recovery link must enter the database together.
            # Backups must never capture an untracked, partially created draft.
            with knowledge.publication_lock, self.store.connect() as db:
                db.execute("INSERT INTO documents(id,filename,title,content,sha256,status,active,created,updated) "
                           "VALUES(?,?,?,?,?,'pending',0,?,?)", (stage, file.name, row['relative'][:200], body, actual, now, now))
                db.execute("UPDATE watched_files SET stage_id=?,error='' WHERE id=?", (stage, identity))
                if not row['document_id'] and row['restricted']:
                    db.execute('INSERT INTO document_access VALUES(?,1)', (stage,))
            try:
                job = self.app.engine.submit(owner, 'index', {'document_id': stage, 'watch_file': identity,
                    'target': row['document_id'], 'expected_sha': row['approved_sha'], 'approved_sha': actual})
                self.store.execute('UPDATE watched_files SET job_id=? WHERE id=?', (job, identity))
                return {'job_id': job}
            except Exception:
                self.cleanup(identity, stage, 'Could not queue indexing. Scan and approve again.')
                raise

    def publish(self, payload):
        with self.lock, self.app.engine.knowledge.publication_lock, self.store.connect() as db:
            stage = db.execute('SELECT * FROM documents WHERE id=?', (payload['document_id'],)).fetchone()
            if not stage or stage['status'] != 'indexed':
                raise ValueError('The staged document was not indexed.')
            target_id = payload['target'] or stage['id']
            if payload['target']:
                target = db.execute('SELECT * FROM documents WHERE id=?', (target_id,)).fetchone()
                if not target or not target['active'] or target['status'] != 'indexed' or target['sha256'] != payload['expected_sha']:
                    raise ValueError('The published document changed during indexing. Scan and review again.')
                db.execute('INSERT INTO document_revisions VALUES(?,?,?,?,?,?)', (target_id, target['version'], target['filename'], target['content'], target['sha256'], time.time()))
                db.execute("UPDATE documents SET filename=?,content=?,sha256=?,version=version+1,status='indexed',error='',updated=? WHERE id=?",
                           (stage['filename'], stage['content'], stage['sha256'], time.time(), target_id))
                db.execute('DELETE FROM chunks WHERE document_id=?', (target_id,))
                db.execute('UPDATE chunks SET document_id=?,document_version=? WHERE document_id=?', (target_id, target['version']+1, stage['id']))
                db.execute('DELETE FROM documents WHERE id=?', (stage['id'],))
            else:
                db.execute('UPDATE documents SET active=1 WHERE id=?', (stage['id'],))
            db.execute("UPDATE watched_files SET document_id=?,approved_sha=?,stage_id=NULL,job_id=NULL,error='',ignored_sha='' WHERE id=?",
                       (target_id, payload['approved_sha'], payload['watch_file']))
            version = self.store.version(db)
            return {'document_id': target_id, 'knowledge_version': version}

    def cleanup(self, identity, stage, error):
        with self.lock, self.app.engine.knowledge.publication_lock, self.store.connect() as db:
            if not db.execute('SELECT id FROM watched_files WHERE id=? AND stage_id=?', (identity, stage)).fetchone():
                return
            db.execute('DELETE FROM chunks WHERE document_id=?', (stage,))
            db.execute('DELETE FROM documents WHERE id=? AND active=0', (stage,))
            db.execute('DELETE FROM document_access WHERE document_id=?', (stage,))
            db.execute('UPDATE watched_files SET stage_id=NULL,job_id=NULL,error=? WHERE id=?', (error[:500], identity))
