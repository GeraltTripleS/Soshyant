import contextlib
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, data):
        self.data = Path(data)
        self.path = self.data / "expert.sqlite"
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO meta VALUES ('schema','1');
                INSERT OR IGNORE INTO meta VALUES ('knowledge_version','0');
                INSERT OR IGNORE INTO meta VALUES ('access_version','0');
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE,
                    password TEXT NOT NULL, role TEXT NOT NULL, active INTEGER DEFAULT 1,
                    created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, title TEXT NOT NULL,
                    content BLOB NOT NULL, sha256 TEXT NOT NULL, version INTEGER DEFAULT 1,
                    priority INTEGER DEFAULT 0, status TEXT NOT NULL, error TEXT DEFAULT '',
                    active INTEGER DEFAULT 1, created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id),
                    document_version INTEGER NOT NULL, location TEXT NOT NULL,
                    text TEXT NOT NULL, vector BLOB);
                CREATE TABLE IF NOT EXISTS document_revisions (
                    document_id TEXT NOT NULL, version INTEGER NOT NULL,
                    filename TEXT NOT NULL, content BLOB NOT NULL, sha256 TEXT NOT NULL,
                    created REAL NOT NULL, PRIMARY KEY(document_id,version));
                CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    role TEXT NOT NULL, content TEXT NOT NULL, result TEXT, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    kind TEXT NOT NULL, status TEXT NOT NULL, phase TEXT DEFAULT '',
                    result TEXT, error TEXT DEFAULT '', canceled INTEGER DEFAULT 0,
                    created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL REFERENCES messages(id),
                    rating TEXT NOT NULL, note TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT,
                    action TEXT NOT NULL, object_id TEXT, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS watched_folders (
                    id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, recursive INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, scanned REAL, error TEXT DEFAULT '');
                CREATE TABLE IF NOT EXISTS watched_files (
                    id TEXT PRIMARY KEY, folder_id TEXT NOT NULL REFERENCES watched_folders(id),
                    relative TEXT NOT NULL, sha TEXT DEFAULT '', present INTEGER DEFAULT 1,
                    approved_sha TEXT DEFAULT '', ignored_sha TEXT DEFAULT '', document_id TEXT,
                    stage_id TEXT, job_id TEXT, error TEXT DEFAULT '', UNIQUE(folder_id,relative));
                CREATE TABLE IF NOT EXISTS answer_reviews (
                    message_id INTEGER PRIMARY KEY REFERENCES messages(id), status TEXT NOT NULL,
                    note TEXT NOT NULL, reviewer TEXT NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS access_groups (
                    id TEXT PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE NOT NULL);
                CREATE TABLE IF NOT EXISTS group_members (
                    group_id TEXT NOT NULL REFERENCES access_groups(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    PRIMARY KEY(group_id,user_id));
                CREATE TABLE IF NOT EXISTS document_access (
                    document_id TEXT PRIMARY KEY, restricted INTEGER NOT NULL CHECK(restricted IN (0,1)));
                CREATE TABLE IF NOT EXISTS document_groups (
                    document_id TEXT NOT NULL REFERENCES document_access(document_id) ON DELETE CASCADE,
                    group_id TEXT NOT NULL REFERENCES access_groups(id) ON DELETE CASCADE,
                    PRIMARY KEY(document_id,group_id));
            ''')
            if 'restricted' not in {row[1] for row in db.execute('PRAGMA table_info(watched_folders)')}:
                db.execute('ALTER TABLE watched_folders ADD COLUMN restricted INTEGER NOT NULL DEFAULT 0')

    def recover_interrupted(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='failed',error='Service restarted; please retry.',updated=? "
                       "WHERE status IN ('queued','running')", (time.time(),))
            db.execute("UPDATE documents SET status='failed',error='Indexing interrupted; retry this document.' "
                       "WHERE status='indexing'")

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, query, params=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(query, params)]

    def one(self, query, params=()):
        rows = self.rows(query, params)
        return rows[0] if rows else None

    def execute(self, query, params=()):
        with self.connect() as db:
            return db.execute(query, params).lastrowid

    def audit(self, user_id, action, object_id=""):
        self.execute("INSERT INTO audit(user_id,action,object_id,created) VALUES(?,?,?,?)",
                     (user_id, action, object_id, time.time()))

    @staticmethod
    def password_hash(password):
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError("Use a password of 12 to 256 characters.")
        salt = secrets.token_hex(16)
        value = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000).hex()
        return f"310000${salt}${value}"

    @staticmethod
    def check_password(password, stored):
        try:
            rounds, salt, expected = stored.split("$")
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
            return hmac.compare_digest(expected, actual)
        except (ValueError, AttributeError):
            return False

    def create_user(self, username, password, role="user"):
        if not isinstance(username, str) or not 3 <= len(username.strip()) <= 60:
            raise ValueError("Use a username of 3 to 60 characters.")
        if role not in ("admin", "user"):
            raise ValueError("Unknown role.")
        identity = uuid.uuid4().hex
        encoded = self.password_hash(password)
        try:
            self.execute("INSERT INTO users(id,username,password,role,created) VALUES(?,?,?,?,?)",
                         (identity, username.strip(), encoded, role, time.time()))
        except sqlite3.IntegrityError as exc:
            raise ValueError("That username is already in use.") from exc
        return identity

    def login(self, username, password, hours=8):
        row = self.one("SELECT * FROM users WHERE username=? AND active=1", (username,))
        # Do comparable work for unknown users to reduce username enumeration.
        encoded = row["password"] if row else "310000$" + "00" * 16 + "$" + "00" * 32
        if not self.check_password(password, encoded) or not row:
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (self.token_hash(token), row["id"], csrf,
                                                               time.time() + hours * 3600))
        return token, csrf

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def session(self, token):
        return self.one("SELECT u.id,u.username,u.role,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id "
                        "WHERE s.token=? AND s.expires>? AND u.active=1", (self.token_hash(token), time.time()))

    def version(self, db=None):
        if db is None:
            return self.one("SELECT value FROM meta WHERE key='knowledge_version'")["value"]
        value = int(db.execute("SELECT value FROM meta WHERE key='knowledge_version'").fetchone()[0]) + 1
        db.execute("UPDATE meta SET value=? WHERE key='knowledge_version'", (str(value),))
        return str(value)

    def conversation(self, identity, owner):
        return self.one("SELECT * FROM conversations WHERE id=? AND user_id=?", (identity, owner))

    def new_conversation(self, owner, title="New conversation"):
        identity, now = uuid.uuid4().hex, time.time()
        self.execute("INSERT INTO conversations VALUES(?,?,?,?,?)", (identity, owner, title[:100], now, now))
        return identity

    def messages(self, identity, owner):
        if not self.conversation(identity, owner):
            raise PermissionError("Conversation not found.")
        rows = self.rows("SELECT id,role,content,result,created FROM messages WHERE conversation_id=? ORDER BY id", (identity,))
        for row in rows:
            row["result"] = json.loads(row["result"]) if row["result"] else None
            if row['result'] and row['role'] == 'assistant':
                from .permissions import filter_result
                row['result'] = filter_result(self, owner, row['result'])
                if row['result'].get('restricted'):
                    row['content'] = row['result']['answer']
        return rows

    def rename_conversation(self, identity, owner, title):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            raise ValueError("Use a chat title of 1 to 100 characters.")
        with self.connect() as db:
            cursor = db.execute("UPDATE conversations SET title=? WHERE id=? AND user_id=?",
                                (title.strip(), identity, owner))
            if not cursor.rowcount:
                raise PermissionError("Conversation not found.")

    def delete_conversation(self, identity, owner):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT id FROM conversations WHERE id=? AND user_id=?", (identity, owner)).fetchone():
                raise PermissionError("Conversation not found.")
            message_ids = {row[0] for row in db.execute("SELECT id FROM messages WHERE conversation_id=?", (identity,))}
            # Completed answer jobs also hold a copy of the answer and evidence.
            for row in db.execute("SELECT id,result FROM jobs WHERE user_id=? AND kind='answer' AND result IS NOT NULL", (owner,)).fetchall():
                result = json.loads(row['result'])
                if isinstance(result, dict) and (result.get('message_id') in message_ids or result.get('conversation_id') == identity):
                    db.execute("DELETE FROM jobs WHERE id=?", (row['id'],))
            db.execute("DELETE FROM feedback WHERE message_id IN (SELECT id FROM messages WHERE conversation_id=?)", (identity,))
            db.execute("DELETE FROM answer_reviews WHERE message_id IN (SELECT id FROM messages WHERE conversation_id=?)", (identity,))
            db.execute("DELETE FROM messages WHERE conversation_id=?", (identity,))
            db.execute("DELETE FROM conversations WHERE id=?", (identity,))

    def new_job(self, owner, kind):
        identity, now = uuid.uuid4().hex, time.time()
        self.execute("INSERT INTO jobs(id,user_id,kind,status,created,updated) VALUES(?,?,?,'queued',?,?)",
                     (identity, owner, kind, now, now))
        return identity

    def job(self, identity, owner):
        row = self.one("SELECT * FROM jobs WHERE id=? AND user_id=?", (identity, owner))
        if row:
            row["result"] = json.loads(row["result"]) if row["result"] else None
            if row['kind'] == 'answer' and row['result']:
                from .permissions import filter_result
                row['result'] = filter_result(self, owner, row['result'])
        return row

    def job_update(self, identity, **fields):
        allowed = {"status", "phase", "result", "error", "canceled"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if "result" in fields:
            fields["result"] = json.dumps(fields["result"], ensure_ascii=False)
        fields["updated"] = time.time()
        self.execute("UPDATE jobs SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                     tuple(fields.values()) + (identity,))


@contextlib.contextmanager
def instance_lock(data):
    path = Path(data) / "server.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("The server is running. Stop it before this operation.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
