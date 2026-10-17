import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create(store, config):
    folder = config.data / "backups"
    folder.mkdir(exist_ok=True)
    name = time.strftime("backup-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ".zip"
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        database = Path(temporary) / "expert.sqlite"
        with store.connect() as source:
            target = sqlite3.connect(database)
            try:
                source.backup(target)
            finally:
                target.close()
        domain = json.dumps(config.domain(), ensure_ascii=False, indent=2).encode()
        manifest = {"schema": 1, "database_sha256": checksum(database),
                    "domain_sha256": hashlib.sha256(domain).hexdigest(), "created": time.time()}
        with zipfile.ZipFile(folder / name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(database, "expert.sqlite")
            archive.writestr("domain.json", domain)
            archive.writestr("manifest.json", json.dumps(manifest))
    return folder / name


def restore(path, config):
    """Called only with the instance lock held and the server stopped."""
    from .config import Config
    with tempfile.TemporaryDirectory(dir=config.data) as temporary:
        target = Path(temporary) / "expert.sqlite"
        with zipfile.ZipFile(path) as archive:
            if set(archive.namelist()) != {"expert.sqlite", "domain.json", "manifest.json"}:
                raise ValueError("Unexpected backup format.")
            if sum(i.file_size for i in archive.infolist()) > 2 * 1024 ** 3:
                raise ValueError("Backup exceeds the restore limit.")
            manifest = json.loads(archive.read("manifest.json"))
            domain_bytes = archive.read("domain.json")
            domain = Config.validate_domain(json.loads(domain_bytes))
            with archive.open("expert.sqlite") as source, target.open("wb") as stream:
                shutil.copyfileobj(source, stream)
        if manifest.get("schema") != 1 or checksum(target) != manifest.get("database_sha256") or hashlib.sha256(domain_bytes).hexdigest() != manifest.get("domain_sha256"):
            raise ValueError("Backup checksums do not match.")
        db = sqlite3.connect(target)
        try:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database is damaged.")
            version = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if not version or version[0] != "1":
                raise ValueError("Unsupported database version.")
            db.execute("DELETE FROM sessions")
            db.commit()
        finally:
            db.close()
        destination = config.data / "expert.sqlite"
        # Preserve the previous database and profile for rollback.
        if destination.exists():
            from .storage import Store
            create(Store(config.data), config)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(destination) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        target.replace(destination)
        config.save_domain(domain)
