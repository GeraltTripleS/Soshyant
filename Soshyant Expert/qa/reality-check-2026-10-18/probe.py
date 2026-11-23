"""Isolated assessment probes. Uses temporary test fixtures, never production data."""
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_engine import Fixture, DOCUMENT
from expert import backup

fixture = Fixture()
fixture.setUp()
try:
    fixture.index()
    fixture.model.generate = lambda *args, **kwargs: {
        'status': 'answered',
        'answer': 'The Aurora X200 warranty is 999 months. [1]',
        'citations': [1],
    }
    chat = fixture.store.new_conversation(fixture.owner)
    result = fixture.engine.answer(fixture.owner, chat, 'How many months is the Aurora X200 warranty?', response_language='en')
    backup_path = backup.create(fixture.store, fixture.config)
    with zipfile.ZipFile(backup_path) as archive:
        entries = archive.namelist()
    report = {
        'scope': 'Synthetic bad model output injected into real Engine validation; NOT a real LLM accuracy test.',
        'source': DOCUMENT.decode(),
        'injected_answer': result['answer'],
        'saved_status': result['status'],
        'returned_citation_text': result['citations'][0]['text'],
        'unsupported_number_accepted': result['status'] == 'answered' and '999' in result['answer'],
        'backup_archive_entries': entries,
        'server_config_in_backup': 'config/server.json' in entries,
        'cloud_profiles_in_backup': any('cloud' in entry for entry in entries),
        'queue_settings': {'answer_workers': 1, 'queue_size': fixture.config.settings['queue_size']},
    }
    target = Path(__file__).with_name('probe-results.json')
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
finally:
    fixture.doCleanups()
