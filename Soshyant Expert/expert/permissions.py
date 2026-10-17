"""Server-side document grants, including historical-answer revocation."""
import uuid


def clause(alias='d'):
    # Alias is an internal SQL identifier, never a request parameter.
    return ("EXISTS(SELECT 1 FROM users au WHERE au.id=? AND au.active=1 AND (au.role='admin' OR "
            f"NOT EXISTS(SELECT 1 FROM document_access ac WHERE ac.document_id={alias}.id AND ac.restricted=1) OR "
            f"EXISTS(SELECT 1 FROM document_groups dg JOIN group_members gm ON gm.group_id=dg.group_id WHERE dg.document_id={alias}.id AND gm.user_id=au.id)))")


def visible(store, owner, identities, db=None):
    if db is None:
        with store.connect() as connection:
            return visible(store, owner, identities, connection)
    account = db.execute('SELECT role FROM users WHERE id=? AND active=1', (owner,)).fetchone()
    if not account:
        return False
    if account['role'] == 'admin':
        return True
    ids = list(set(identities))
    for offset in range(0, len(ids), 400):
        part = ids[offset:offset+400]
        denied = db.execute('SELECT a.document_id FROM document_access a WHERE a.restricted=1 AND '
            'a.document_id IN (' + ','.join('?' for _ in part) + ') AND NOT EXISTS('
            'SELECT 1 FROM document_groups dg JOIN group_members gm ON gm.group_id=dg.group_id '
            'WHERE dg.document_id=a.document_id AND gm.user_id=?) LIMIT 1', (*part, owner)).fetchone()
        if denied:
            return False
    return True


def dependencies(result):
    return set(result.get('access_documents', [row['document_id'] for row in result.get('citations', []) if row.get('document_id')]))


def filter_result(store, owner, result):
    allowed = visible(store, owner, dependencies(result))
    if allowed and 'access_documents' not in result:
        # Older responses did not retain all retrieved/history dependencies.
        # Do not assume that their selected citations describe every exposure.
        restricted = [row['document_id'] for row in store.rows('SELECT document_id FROM document_access WHERE restricted=1')]
        allowed = visible(store, owner, restricted)
    if allowed:
        return result
    persian = result.get('response_language') in ('fa', 'Persian')
    return {'status': 'restricted', 'restricted': True, 'citations': [],
            'answer': 'دسترسی شما به منابع این پاسخ تغییر کرده است. برای پاسخ بر پایه منابع مجاز، دوباره سؤال کنید.' if persian else
            'Your access to this answer\'s sources has changed. Ask again to get an answer from your permitted documents.',
            **{key: result[key] for key in ('conversation_id', 'message_id', 'response_language') if key in result}}


def version(store):
    return store.one("SELECT value FROM meta WHERE key='access_version'")['value']


def changed(store, db):
    db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='access_version'")
    store.version(db)
    db.execute("UPDATE jobs SET canceled=1 WHERE kind='answer' AND status IN ('queued','running')")


def groups(store):
    rows = store.rows('SELECT id,name FROM access_groups ORDER BY name COLLATE NOCASE')
    for row in rows:
        row['members'] = [entry['user_id'] for entry in store.rows('SELECT user_id FROM group_members WHERE group_id=?', (row['id'],))]
    return rows


def save_group(app, identity, data):
    name, members = data.get('name'), data.get('members', [])
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError('Use a group name of 1 to 80 characters.')
    if not isinstance(members, list) or len(members) > 2000 or not all(isinstance(value, str) for value in members):
        raise ValueError('Choose valid group members (up to 2,000).')
    members = set(members)
    updating = identity is not None
    identity = identity or uuid.uuid4().hex
    with app.engine.knowledge.publication_lock, app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT id FROM access_groups WHERE id=?', (identity,)).fetchone()
        if updating and not current:
            raise ValueError('Group no longer exists.')
        if not current and db.execute('SELECT count(*) FROM access_groups').fetchone()[0] >= 100:
            raise ValueError('Up to 100 access groups are supported.')
        if db.execute('SELECT id FROM access_groups WHERE name=? COLLATE NOCASE AND id<>?', (name.strip(), identity)).fetchone():
            raise ValueError('This group name is already in use.')
        for member in members:
            if not db.execute('SELECT id FROM users WHERE id=?', (member,)).fetchone():
                raise ValueError('A selected user no longer exists.')
        previous = {row[0] for row in db.execute('SELECT user_id FROM group_members WHERE group_id=?', (identity,))}
        db.execute('INSERT INTO access_groups VALUES(?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name', (identity, name.strip()))
        if previous != members:
            db.execute('DELETE FROM group_members WHERE group_id=?', (identity,))
            db.executemany('INSERT INTO group_members VALUES(?,?)', [(identity, member) for member in members])
            changed(app.store, db)
    return identity


def delete_group(app, identity):
    with app.engine.knowledge.publication_lock, app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT id FROM access_groups WHERE id=?', (identity,)).fetchone():
            raise ValueError('Group no longer exists.')
        db.execute('DELETE FROM access_groups WHERE id=?', (identity,))
        changed(app.store, db)


def document(store, identity):
    if not store.one('SELECT id FROM documents WHERE id=?', (identity,)):
        raise ValueError('Document not found.')
    row = store.one('SELECT restricted FROM document_access WHERE document_id=?', (identity,))
    return {'restricted': bool(row and row['restricted']), 'groups': [entry['group_id'] for entry in store.rows(
        'SELECT group_id FROM document_groups WHERE document_id=?', (identity,))]}


def save_document(app, identity, data):
    restricted, granted = data.get('restricted'), data.get('groups', [])
    if not isinstance(restricted, bool) or not isinstance(granted, list) or len(granted) > 100 or not all(isinstance(value, str) for value in granted):
        raise ValueError('Choose document access and up to 100 groups.')
    granted = set(granted) if restricted else set()
    with app.engine.knowledge.publication_lock, app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT id FROM documents WHERE id=?', (identity,)).fetchone():
            raise ValueError('Document not found.')
        for group in granted:
            if not db.execute('SELECT id FROM access_groups WHERE id=?', (group,)).fetchone():
                raise ValueError('An access group no longer exists.')
        old = db.execute('SELECT restricted FROM document_access WHERE document_id=?', (identity,)).fetchone()
        previous = {row[0] for row in db.execute('SELECT group_id FROM document_groups WHERE document_id=?', (identity,))}
        if bool(old and old[0]) != restricted or previous != granted:
            db.execute('INSERT INTO document_access VALUES(?,?) ON CONFLICT(document_id) DO UPDATE SET restricted=excluded.restricted', (identity, int(restricted)))
            db.execute('DELETE FROM document_groups WHERE document_id=?', (identity,))
            db.executemany('INSERT INTO document_groups VALUES(?,?)', [(identity, group) for group in granted])
            changed(app.store, db)
