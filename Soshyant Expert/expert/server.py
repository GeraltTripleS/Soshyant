import argparse
import base64
from collections import defaultdict
import hmac
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import signal
import ssl
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import __version__
from . import backup
from .dashboard import overview
from .watched import WatchedFolders
from . import review
from . import permissions
from .config import Config
from .capacity import CapacityPlanner
from .model_library import ModelLibrary
from .knowledge import EXTENSIONS
from .engine import Engine
from .storage import Store, instance_lock
from .speech import Speech, MAX_BYTES


class Application:
    def __init__(self, config, store=None, model=None):
        self.config = config
        self.store = store or Store(config.data)
        self.store.recover_interrupted()
        self.engine = Engine(self.store, config, model)
        self.capacity = CapacityPlanner(config)
        self.models = ModelLibrary(config, self.engine)
        self.speech = Speech(config)
        self.import_lock = threading.Lock()
        self.setup_lock = threading.Lock()
        self.login_lock = threading.Lock()
        self.attempts = defaultdict(list)
        self.bootstrap_path = config.data / "FIRST-ADMIN-CODE.txt"
        if not self.store.one("SELECT id FROM users LIMIT 1") and not self.bootstrap_path.exists():
            self.bootstrap_path.write_text(secrets.token_urlsafe(24), encoding="utf-8")
        self.allowed_hosts = {"127.0.0.1", "localhost", "::1"}
        self.secure = False
        self.watched = WatchedFolders(self)
        self.engine.watched = self.watched
        self.watched.start()

    def close(self):
        self.watched.close()
        self.speech.close()
        self.engine.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SoshyantExpert"

    @property
    def app(self):
        return self.server.app

    def log_message(self, *args):
        # Do not persist URLs, document text, questions or account names.
        pass

    def send(self, status, data=None, content_type="application/json; charset=utf-8", headers=None):
        body = json.dumps(data, ensure_ascii=False).encode() if content_type.startswith("application/json") else data
        body = body or b""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def body(self, maximum=100000):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid request length.") from exc
        if length < 0 or length > maximum:
            self.close_connection = True
            raise ValueError("Request exceeds the size limit.")
        return self.rfile.read(length)

    def json_body(self):
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Expected a JSON request.")
        value = json.loads(self.body() or b"{}")
        if not isinstance(value, dict):
            raise ValueError("Expected an object.")
        return value

    def account(self, write=False, admin=False):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        token = cookie.get("soshyant_session")
        self.session_token = token.value if token else ""
        account = self.app.store.session(self.session_token)
        if not account:
            raise PermissionError("Sign in to continue.")
        if admin and account["role"] != "admin":
            raise PermissionError("Administrator access is required.")
        if write and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), account["csrf"]):
            raise PermissionError("The request could not be verified. Refresh and retry.")
        return account

    def valid_origin(self):
        host = self.headers.get("Host", "")
        if urlsplit("//" + host).hostname not in self.app.allowed_hosts:
            raise PermissionError("Host is not allowed.")
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc.lower() != host.lower():
            raise PermissionError("Cross-origin requests are not allowed.")

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, write):
        try:
            self.valid_origin()
            if write:
                self.post()
            else:
                self.get()
        except PermissionError as exc:
            self.close_connection = True
            self.send(403, {"error": str(exc)})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.close_connection = True
            self.send(400, {"error": str(exc)[:400] or "Invalid request."})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception:
            self.close_connection = True
            self.send(500, {"error": "The operation failed. Your previous saved data is retained."})

    def get(self):
        parsed = urlsplit(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
                 "/capacity.js": ("capacity.js", "text/javascript; charset=utf-8"),
                 "/library.js": ("library.js", "text/javascript; charset=utf-8"),
                 "/speech.js": ("speech.js", "text/javascript; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                 "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path in files:
            name, mime = files[path]
            return self.send(200, (self.app.config.root / "web" / name).read_bytes(), mime)
        if path == "/healthz":
            return self.send(200, {"status": "ok", "version": __version__})
        if path == "/api/bootstrap":
            return self.send(200, {"setup_required": not bool(self.app.store.one("SELECT id FROM users LIMIT 1"))})
        account = self.account()
        store, engine = self.app.store, self.app.engine
        if path == '/api/speech':
            return self.send(200, self.app.speech.status())
        match = re.fullmatch(r'/api/speech/jobs/([a-f0-9]{32})', path)
        if match:
            return self.send(200, self.app.speech.get(match[1], account['id']))
        if path == "/api/me":
            return self.send(200, account)
        if path == '/api/dashboard':
            self.account(admin=True)
            return self.send(200, overview(self.app))
        if path == '/api/watched-folders':
            self.account(admin=True)
            return self.send(200, self.app.watched.catalog())
        if path == '/api/reviews':
            self.account(admin=True)
            return self.send(200, review.listing(store, query))
        if path == '/api/groups':
            self.account(admin=True)
            return self.send(200, permissions.groups(store))
        match = re.fullmatch(r'/api/documents/([a-f0-9]+)/access', path)
        if match:
            self.account(admin=True)
            return self.send(200, permissions.document(store, match[1]))
        if path == "/api/capacity/catalog":
            return self.send(200, self.app.capacity.models())
        if path == '/api/models':
            self.account(admin=True)
            return self.send(200, self.app.models.catalog())
        if path == '/api/models/folders':
            self.account(admin=True)
            return self.send(200, self.app.models.folders(query.get('path',[None])[0]))
        if path == "/api/status":
            return self.send(200, {"version": __version__, "domain": self.app.config.domain(),
                "knowledge_version": store.version(), "model": {"installed": engine.model.available(), "state": engine.model.state, 'selection_id':engine.selection_id(), **self.app.models.active_info()},
                "search": {"mode": self.app.config.settings["embedding_mode"], "installed": engine.knowledge.embeddings.ready()},
                "ocr": engine.knowledge.ocr.status(),
                "queues": {kind: q.qsize() for kind, q in engine.queues.items()}, "secure": self.app.secure,
                "upload_limit_mb": self.app.config.settings["max_document_mb"]})
        if path == "/api/conversations":
            return self.send(200, store.rows("SELECT id,title,created,updated FROM conversations WHERE user_id=? ORDER BY updated DESC", (account["id"],)))
        match = re.fullmatch(r"/api/conversations/([a-f0-9]+)/messages", path)
        if match:
            return self.send(200, store.messages(match[1], account["id"]))
        match = re.fullmatch(r"/api/jobs/([a-f0-9]+)", path)
        if match:
            job = store.job(match[1], account["id"])
            if not job:
                raise PermissionError("Job not found.")
            return self.send(200, job)
        if path == "/api/documents":
            archived = account["role"] == "admin" and query.get("archived") == ["1"]
            return self.send(200, engine.knowledge.list_documents(archived, owner=account['id']))
        match = re.fullmatch(r"/api/documents/([a-f0-9]+)/download", path)
        if match:
            if not permissions.visible(store, account['id'], [match[1]]):
                raise PermissionError('Document not found.')
            doc = store.one("SELECT filename,content,version FROM documents WHERE id=? AND active=1", (match[1],))
            if not doc:
                raise PermissionError("Document not found.")
            requested_version = int(query.get("version", [str(doc["version"])])[0])
            if requested_version != doc["version"]:
                doc = store.one("SELECT filename,content FROM document_revisions WHERE document_id=? AND version=?",
                                (match[1], requested_version))
                if not doc:
                    raise ValueError("The requested document version is unavailable.")
            return self.send(200, doc["content"], "application/octet-stream",
                             {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(doc["filename"])})
        if path == "/api/users":
            self.account(admin=True)
            return self.send(200, store.rows("SELECT id,username,role,active,created FROM users ORDER BY created"))
        match = re.fullmatch(r"/api/backups/(backup-[a-zA-Z0-9-]+\.zip)", path)
        if match:
            self.account(admin=True)
            file = self.app.config.data / "backups" / match[1]
            if not file.is_file():
                raise ValueError("Backup not found.")
            return self.send(200, file.read_bytes(), "application/zip", {"Content-Disposition": f'attachment; filename="{file.name}"'})
        self.send(404, {"error": "Not found."})

    def post(self):
        path = urlsplit(self.path).path
        query = parse_qs(urlsplit(self.path).query)
        store, engine = self.app.store, self.app.engine
        if path == '/api/speech/settings':
            self.account(write=True, admin=True)
            return self.send(200, self.app.speech.settings(self.json_body()))
        if path == '/api/speech/transcribe':
            account = self.account(write=True)
            if self.headers.get_content_type() not in ('audio/wav', 'application/octet-stream'):
                raise ValueError('Expected WAV audio.')
            identity = self.app.speech.submit(account['id'], self.body(MAX_BYTES))
            return self.send(202, {'job_id': identity})
        match = re.fullmatch(r'/api/speech/jobs/([a-f0-9]{32})/(cancel|consume)', path)
        if match:
            account = self.account(write=True)
            self.json_body()
            if match[2] == 'cancel':
                self.app.speech.cancel(match[1], account['id'])
            else:
                self.app.speech.get(match[1], account['id'], consume=True)
            return self.send(200, {'ok': True})
        if path == "/api/setup":
            data = self.json_body()
            with self.app.setup_lock:
                if store.one("SELECT id FROM users LIMIT 1"):
                    raise PermissionError("Initial setup is already complete.")
                if not self.app.bootstrap_path.exists() or not hmac.compare_digest(
                        str(data.get("code", "")), self.app.bootstrap_path.read_text(encoding="utf-8").strip()):
                    raise PermissionError("Enter the first-admin code from the server's local data folder.")
                identity = store.create_user(data.get("username", ""), data.get("password", ""), "admin")
                store.audit(identity, "initial_setup")
                self.app.bootstrap_path.unlink()
            return self.send(201, {"ok": True})
        if path == "/api/login":
            data = self.json_body()
            ip, now = self.client_address[0], time.time()
            with self.app.login_lock:
                attempts = [value for value in self.app.attempts[ip] if now - value < 300]
                self.app.attempts[ip] = attempts
                if len(attempts) >= 10:
                    return self.send(429, {"error": "Too many sign-in attempts. Wait five minutes."})
                attempts.append(now)
            credentials = store.login(str(data.get("username", "")), str(data.get("password", "")), self.app.config.settings["session_hours"])
            if not credentials:
                raise PermissionError("Incorrect username or password.")
            # Successful mobile logins may share a loopback gateway address;
            # only failed attempts should consume the brute-force budget.
            with self.app.login_lock:
                if now in self.app.attempts[ip]:self.app.attempts[ip].remove(now)
            token, csrf = credentials
            cookie = f"soshyant_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={int(self.app.config.settings['session_hours'] * 3600)}"
            if self.app.secure:
                cookie += "; Secure"
            return self.send(200, {"csrf": csrf}, headers={"Set-Cookie": cookie})
        account = self.account(write=True)
        if path == "/api/capacity/estimate":
            return self.send(200, self.app.capacity.estimate(self.json_body()))
        if path == "/api/logout":
            self.body()
            store.execute("DELETE FROM sessions WHERE token=?", (store.token_hash(self.session_token),))
            return self.send(200, {"ok": True}, headers={"Set-Cookie": "soshyant_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
        if path == "/api/conversations":
            self.json_body()
            return self.send(201, {"id": store.new_conversation(account["id"])})
        match = re.fullmatch(r"/api/conversations/([a-f0-9]+)/(rename|delete)", path)
        if match:
            data = self.json_body()
            if match[2] == "rename":
                store.rename_conversation(match[1], account["id"], data.get("title"))
            else:
                if data.get("confirm") is not True:
                    raise ValueError("Confirm permanent chat deletion.")
                engine.delete_conversation(match[1], account["id"])
                store.audit(account["id"], "conversation_delete", match[1])
            return self.send(200, {"ok": True})
        if path == "/api/ask":
            data = self.json_body()
            identity = str(data.get("conversation_id", ""))
            if not store.conversation(identity, account["id"]):
                raise PermissionError("Conversation not found.")
            question = data.get("question", "")
            if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
                raise ValueError("Ask a question between 1 and 4,000 characters.")
            language = data.get("response_language")
            if language not in (None, "en", "fa"):
                raise ValueError("Choose English or Persian as the response language.")
            job = engine.submit(account["id"], "answer", {"conversation_id": identity, "question": question,
                                                       "response_language": language,'model_selection':data.get('model_selection')})
            return self.send(202, {"job_id": job})
        match = re.fullmatch(r"/api/jobs/([a-f0-9]+)/cancel", path)
        if match:
            self.json_body()
            if not store.job(match[1], account["id"]):
                raise PermissionError("Job not found.")
            store.job_update(match[1], canceled=1)
            return self.send(200, {"ok": True})
        if path == "/api/feedback":
            data = self.json_body()
            message = store.one("SELECT m.id FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=? AND c.user_id=? AND m.role='assistant'",
                                (int(data.get("message_id", 0)), account["id"]))
            if not message or data.get("rating") not in ("helpful", "incorrect"):
                raise ValueError("Invalid feedback.")
            with store.connect() as db:
                db.execute("INSERT INTO feedback(user_id,message_id,rating,note,created) VALUES(?,?,?,?,?)",
                           (account["id"], message["id"], data["rating"], str(data.get("note", ""))[:1000], time.time()))
                # Reopen atomically, including submissions within one clock tick.
                db.execute("UPDATE answer_reviews SET status='open' WHERE message_id=?", (message['id'],))
            return self.send(200, {"ok": True})
        if path == "/api/password":
            data = self.json_body()
            user = store.one("SELECT password FROM users WHERE id=?", (account["id"],))
            if not store.check_password(str(data.get("current", "")), user["password"]):
                raise PermissionError("The current password is incorrect.")
            encoded = store.password_hash(data.get("password", ""))
            with store.connect() as db:
                db.execute("UPDATE users SET password=? WHERE id=?", (encoded, account["id"]))
                db.execute("DELETE FROM sessions WHERE user_id=?", (account["id"],))
            return self.send(200, {"ok": True})
        self.account(admin=True)
        match = re.fullmatch(r'/api/groups/([a-f0-9]+)/delete', path)
        if match:
            if self.json_body().get('confirm') is not True:
                raise ValueError('Confirm removing this access group.')
            permissions.delete_group(self.app, match[1])
            store.audit(account['id'], 'group_delete', match[1])
            return self.send(200, {'ok': True})
        match = re.fullmatch(r'/api/groups/([a-f0-9]+)', path)
        if path == '/api/groups' or match:
            if match and not store.one('SELECT id FROM access_groups WHERE id=?', (match[1],)):
                raise ValueError('Group not found.')
            identity = permissions.save_group(self.app, match[1] if match else None, self.json_body())
            store.audit(account['id'], 'group_save', identity)
            return self.send(200 if match else 201, {'id': identity})
        match = re.fullmatch(r'/api/documents/([a-f0-9]+)/access', path)
        if match:
            permissions.save_document(self.app, match[1], self.json_body())
            store.audit(account['id'], 'document_access', match[1])
            return self.send(200, {'ok': True})
        match = re.fullmatch(r'/api/reviews/([0-9]+)', path)
        if match:
            review.save(store, int(match[1]), account['id'], self.json_body())
            store.audit(account['id'], 'answer_review', match[1])
            return self.send(200, {'ok': True})
        if path == '/api/watched-folders':
            identity = self.app.watched.add(self.json_body())
            store.audit(account['id'], 'watched_folder_add', identity)
            return self.send(201, {'id': identity})
        match = re.fullmatch(r'/api/watched-folders/([a-f0-9]+)/(scan|enabled|access)', path)
        if match:
            data = self.json_body()
            if match[2] == 'scan':
                return self.send(200, self.app.watched.scan(match[1]))
            if match[2] == 'access':
                if not isinstance(data.get('restricted'), bool):
                    raise ValueError('Choose the initial document access.')
                with self.app.watched.lock:
                    if not store.one('SELECT id FROM watched_folders WHERE id=?', (match[1],)):
                        raise ValueError('Watched folder not found.')
                    store.execute('UPDATE watched_folders SET restricted=? WHERE id=?', (int(data['restricted']), match[1]))
                store.audit(account['id'], 'watched_folder_access', match[1])
                return self.send(200, {'ok': True})
            if not isinstance(data.get('enabled'), bool):
                raise ValueError('Choose whether monitoring is enabled.')
            with self.app.watched.lock:
                if not store.one('SELECT id FROM watched_folders WHERE id=?', (match[1],)):
                    raise ValueError('Watched folder not found.')
                store.execute('UPDATE watched_folders SET enabled=? WHERE id=?', (int(data['enabled']), match[1]))
            return self.send(200, {'ok': True})
        match = re.fullmatch(r'/api/watched-changes/([a-f0-9]+)/(approve|ignore)', path)
        if match:
            data = self.json_body()
            if match[2] == 'approve':
                result = self.app.watched.approve(match[1], account['id'], data.get('sha'), data.get('confirm_archive') is True)
                store.audit(account['id'], 'watched_change_approve', match[1])
                return self.send(202, result)
            with self.app.watched.lock:
                row = store.one('SELECT * FROM watched_files WHERE id=?', (match[1],))
                if not row or row['stage_id']:
                    raise ValueError('Change is missing or processing.')
                token = row['sha'] if row['present'] else 'missing'
                if data.get('sha') != token:
                    raise ValueError('Change was updated. Refresh the list.')
                store.execute('UPDATE watched_files SET ignored_sha=? WHERE id=?', (token, match[1]))
            return self.send(200, {'ok': True})
        if path == '/api/models/cloud':
            profile=self.app.models.clouds.add(self.json_body())
            store.audit(account['id'],'cloud_model_add',profile['id'])
            return self.send(201,{'profile':profile,'catalog':self.app.models.catalog()})
        if path == '/api/models/scan':
            data=self.json_body()
            result=self.app.models.scan_folder(data.get('path'),data.get('recursive',True))
            store.audit(account['id'],'model_folder_scan')
            return self.send(200,result)
        if path == '/api/models/register':
            result = self.app.models.register(self.json_body().get('path'))
            store.audit(account['id'], 'model_register')
            return self.send(200, result)
        if path == '/api/models/activate':
            data=self.json_body()
            result = self.app.models.activate(data.get('model_id'),data.get('confirm_cloud',False))
            store.audit(account['id'], 'model_activate')
            return self.send(200, result)
        if path == '/api/ocr':
            enabled = self.json_body().get('enabled')
            if not isinstance(enabled, bool):
                raise ValueError('Choose whether OCR is on or off.')
            self.app.config.save_setting('ocr_enabled', enabled)
            if not enabled:
                engine.knowledge.ocr.close()
            store.audit(account['id'], 'ocr_' + ('enable' if enabled else 'disable'))
            return self.send(200, engine.knowledge.ocr.status())
        if path == '/api/documents/import':
            restricted = query.get('restricted', ['0'])[0]
            if restricted not in ('0','1'):
                raise ValueError('Choose the initial document access.')
            filename = query.get('filename', [''])[0]
            if not filename or Path(filename).name != filename or '\\' in filename or Path(filename).suffix.lower() not in EXTENSIONS:
                raise ValueError('Choose a supported document with a simple filename.')
            body = self.body(self.app.config.settings['max_document_mb'] * 1024 * 1024)
            with self.app.import_lock:
                existing = store.one('SELECT id,status FROM documents d WHERE sha256=? AND active=1 AND coalesce('
                    '(SELECT restricted FROM document_access WHERE document_id=d.id),0)=? AND '
                    '(?=0 OR NOT EXISTS(SELECT 1 FROM document_groups WHERE document_id=d.id)) ORDER BY created LIMIT 1',
                    (hashlib.sha256(body).hexdigest(), int(restricted), int(restricted)))
                if existing and existing['status'] == 'indexed':
                    return self.send(200, {'skipped': True, 'document_id': existing['id']})
                if existing and existing['status'] == 'indexing':
                    raise ValueError('An identical document is already being indexed. Retry this file later.')
                identity = existing['id'] if existing else engine.knowledge.add(filename, body, query.get('title', [''])[0], restricted=restricted=='1')
                job = engine.submit(account['id'], 'index', {'document_id': identity})
            store.audit(account['id'], 'folder_document_import', identity)
            return self.send(202, {'document_id': identity, 'job_id': job, 'skipped': False})
        if path == "/api/documents" or re.fullmatch(r"/api/documents/[a-f0-9]+/replace", path):
            filename = query.get("filename", [""])[0]
            body = self.body(self.app.config.settings["max_document_mb"] * 1024 * 1024)
            if path == "/api/documents":
                restricted = query.get('restricted', ['0'])[0]
                if restricted not in ('0','1'):
                    raise ValueError('Choose the initial document access.')
                identity = engine.knowledge.add(filename, body, query.get("title", [""])[0], int(query.get("priority", ["0"])[0]), restricted=restricted=='1')
            else:
                identity = path.split("/")[3]
                engine.knowledge.replace(identity, filename, body)
            job = engine.submit(account["id"], "index", {"document_id": identity})
            store.audit(account["id"], "document_upload", identity)
            return self.send(202, {"document_id": identity, "job_id": job})
        match = re.fullmatch(r"/api/documents/([a-f0-9]+)/(index|archive|restore|delete)", path)
        if match:
            data = self.json_body()
            identity, action = match.groups()
            if action == 'delete':
                if data.get('confirm') is not True:
                    raise ValueError('Confirm permanent deletion of this archived document.')
                engine.knowledge.delete_archived(identity)
                store.audit(account['id'], 'document_delete', identity)
                return self.send(200, {'ok': True})
            if action == "index":
                job = engine.submit(account["id"], "index", {"document_id": identity})
                return self.send(202, {"job_id": job})
            engine.knowledge.archive(identity, action == "archive")
            store.audit(account["id"], "document_" + action, identity)
            return self.send(200, {"ok": True})
        if path == "/api/domain":
            data = self.json_body()
            with engine.knowledge.publication_lock:
                domain = self.app.config.save_domain(data)
            store.audit(account["id"], "domain_update")
            return self.send(200, domain)
        if path == "/api/users":
            data = self.json_body()
            identity = store.create_user(data.get("username", ""), data.get("password", ""), data.get("role", "user"))
            store.audit(account["id"], "user_create", identity)
            return self.send(201, {"id": identity})
        match = re.fullmatch(r"/api/users/([a-f0-9]+)/active", path)
        if match:
            data = self.json_body()
            if match[1] == account["id"]:
                raise ValueError("You cannot disable your own account.")
            active = bool(data.get("active"))
            with store.connect() as db:
                db.execute("UPDATE users SET active=? WHERE id=?", (int(active), match[1]))
                if not active:
                    db.execute("DELETE FROM sessions WHERE user_id=?", (match[1],))
            store.audit(account["id"], "user_access_update", match[1])
            return self.send(200, {"ok": True})
        if path == "/api/backups":
            self.json_body()
            with engine.knowledge.publication_lock:
                file = backup.create(store, self.app.config)
            store.audit(account["id"], "backup_create", file.name)
            return self.send(201, {"filename": file.name, "url": "/api/backups/" + file.name})
        self.send(404, {"error": "Not found."})


def main():
    parser = argparse.ArgumentParser(description="Soshyant Expert local document server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--allowed-host", action="append", default=[])
    parser.add_argument("--desktop-stop-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1") and not (args.cert and args.key and args.allowed_host):
        parser.error("LAN access requires a TLS certificate, key, and explicit --allowed-host values.")
    config = Config()
    if args.desktop_stop_file and (args.desktop_stop_file.resolve().parent != config.data.resolve() or
            not re.fullmatch(r'launcher-stop-[a-f0-9]{32}', args.desktop_stop_file.name)):
        parser.error('Invalid launcher control file.')
    with instance_lock(config.data):
        app = Application(config)
        server = ThreadingHTTPServer((args.host, args.port or config.settings["port"]), Handler)
        server.app = app
        app.allowed_hosts.update(args.allowed_host)
        if args.cert and args.key:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(args.cert, args.key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            app.secure = True
        print(f"Soshyant Expert is ready: {'https' if app.secure else 'http'}://{args.host}:{server.server_port}", flush=True)
        if app.bootstrap_path.exists():
            print("First launch: open data/FIRST-ADMIN-CODE.txt and enter its code in the setup screen.", flush=True)
        monitor_done = threading.Event()
        if args.desktop_stop_file:
            def monitor():
                while not monitor_done.wait(.5):
                    if args.desktop_stop_file.exists():
                        args.desktop_stop_file.unlink(missing_ok=True)
                        server.shutdown()
                        return
            threading.Thread(target=monitor, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            monitor_done.set()
            server.server_close()
            app.close()


if __name__ == "__main__":
    main()
