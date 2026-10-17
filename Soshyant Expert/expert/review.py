"""Administrator triage of saved answers; never changes model or knowledge."""
import json
import time


def listing(store, query):
    kind = query.get('kind', ['attention'])[0]
    state = query.get('state', ['open'])[0]
    if kind not in ('attention', 'insufficient', 'clarify', 'incorrect', 'helpful', 'all') or state not in ('open', 'resolved', 'all'):
        raise ValueError('Unknown review filter.')
    before = int(query.get('before', [str(2**63-1)])[0])
    conditions = ["m.role='assistant'", 'm.id<?']
    params = [before]
    if kind in ('insufficient', 'clarify'):
        conditions.append("json_extract(m.result,'$.status')=?")
        params.append(kind)
    elif kind in ('incorrect', 'helpful'):
        conditions.append('EXISTS(SELECT 1 FROM feedback f WHERE f.message_id=m.id AND f.rating=?)')
        params.append(kind)
    else:
        rating = " AND f.rating='incorrect'" if kind == 'attention' else ''
        conditions.append("(json_extract(m.result,'$.status') IN ('insufficient','clarify') OR EXISTS(SELECT 1 FROM feedback f WHERE f.message_id=m.id" + rating + '))')
    resolved = "(r.status='resolved' AND r.updated>=coalesce((SELECT max(f.created) FROM feedback f WHERE f.message_id=m.id),0))"
    if state != 'all':
        conditions.append('coalesce(' + resolved + ',0)=' + ('1' if state == 'resolved' else '0'))
    rows = store.rows("SELECT m.id,m.content,m.result,m.created,c.title,u.username,"
        "(SELECT q.content FROM messages q WHERE q.conversation_id=m.conversation_id AND q.role='user' AND q.id<m.id ORDER BY q.id DESC LIMIT 1) AS question,"
        "r.note AS review_note,r.updated AS reviewed_at,coalesce(" + resolved + ",0) AS resolved "
        "FROM messages m JOIN conversations c ON c.id=m.conversation_id JOIN users u ON u.id=c.user_id "
        "LEFT JOIN answer_reviews r ON r.message_id=m.id WHERE " + ' AND '.join(conditions) + ' ORDER BY m.id DESC LIMIT 51', tuple(params))
    more = len(rows) > 50
    rows = rows[:50]
    for row in rows:
        row['result'] = json.loads(row['result']) if row['result'] else {}
        row['feedback'] = store.rows('SELECT rating,note,created FROM feedback WHERE message_id=? ORDER BY created DESC LIMIT 20', (row['id'],))
    return {'items': rows, 'next': rows[-1]['id'] if more else None}


def save(store, identity, owner, data):
    status = data.get('status')
    note = data.get('note', '')
    if status not in ('open', 'resolved') or not isinstance(note, str) or len(note) > 2000:
        raise ValueError('Use a valid review status and a note of up to 2,000 characters.')
    with store.connect() as db:
        if not db.execute("SELECT id FROM messages WHERE id=? AND role='assistant'", (identity,)).fetchone():
            raise ValueError('Answer no longer exists.')
        db.execute('INSERT INTO answer_reviews VALUES(?,?,?,?,?) ON CONFLICT(message_id) DO UPDATE SET '
                   'status=excluded.status,note=excluded.note,reviewer=excluded.reviewer,updated=excluded.updated',
                   (identity, status, note.strip(), owner, time.time()))
