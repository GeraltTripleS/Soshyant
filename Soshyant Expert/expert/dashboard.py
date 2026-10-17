"""Read-only administrator overview; never exposes questions or credentials."""
import time


def overview(app):
    store = app.store
    counts = {row['status']: row['count'] for row in store.rows(
        'SELECT status,count(*) AS count FROM documents WHERE active=1 GROUP BY status')}
    backups = list((app.config.data / 'backups').glob('backup-*.zip'))
    latest = max((p.stat().st_mtime for p in backups if p.is_file()), default=None)
    return {
        'checked_at': time.time(),
        'documents': {'active': sum(counts.values()), 'by_status': counts,
                      'archived': store.one('SELECT count(*) AS n FROM documents d WHERE active=0 AND NOT EXISTS(SELECT 1 FROM watched_files w WHERE w.stage_id=d.id)')['n'],
                      'passages': store.one("SELECT count(*) AS n FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.active=1 AND d.status='indexed'")["n"]},
        'jobs': store.rows("SELECT kind,status,count(*) AS count FROM jobs WHERE status IN ('queued','running') GROUP BY kind,status"),
        'users': store.one('SELECT count(*) AS total,coalesce(sum(active),0) AS active FROM users'),
        'backup': {'count': len(backups), 'latest': latest},
        'attention': store.rows("SELECT id,title,filename,status,error,updated FROM documents WHERE active=1 AND status IN ('failed','pending') ORDER BY updated DESC LIMIT 10"),
    }
