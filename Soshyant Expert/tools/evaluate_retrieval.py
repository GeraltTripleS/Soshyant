"""Small reproducible retrieval acceptance set, synthetic documents and real local embeddings."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_engine import Fixture


def main():
    fixture = Fixture(); fixture.setUp()
    try:
        knowledge = fixture.engine.knowledge
        fixture.config.settings['embedding_mode'] = 'hybrid'
        knowledge.embeddings.directory = ROOT / 'assets/embeddings'
        documents = {
            'warranty.txt': 'The Aurora X200 pump warranty lasts 36 months from installation. Warranty claims require the installation report and serial number.',
            'reset.txt': 'Error E-04 indicates a dry-run condition in the Aurora X200 pump. Restore inlet pressure and hold the reset button for 3 seconds.',
            'escalation.txt': 'An unresolved Aurora X200 incident after two site visits must be escalated to the regional engineering manager.',
            'shipping.txt': 'Shipping orders leave the warehouse on Tuesday. Delivery charges depend on destination and package weight.',
            'leave.txt': 'Employees submit annual leave requests to human resources ten days before planned absence.',
            'gardening.txt': 'Water tomato seedlings at soil level in the early morning. Avoid keeping the leaves wet overnight.'}
        for name, body in documents.items(): fixture.index(body.encode(), name)
        cases = [('Aurora X200 warranty duration', 'warranty.txt'),
                 ('What paperwork do I need to claim the pump guarantee?', 'warranty.txt'),
                 ('How do I clear error E-04?', 'reset.txt'),
                 ('Who handles an unresolved pump issue after two visits?', 'escalation.txt'),
                 ('When should I water tomato seedlings?', 'gardening.txt'),
                 ('What day do orders ship from the warehouse?', 'shipping.txt')]
        results = []
        for query, expected in cases:
            started = time.perf_counter()
            sources, _ = knowledge.search(query, owner=fixture.owner)
            names = [row['filename'] for row in sources]
            results.append({'query':query, 'expected':expected, 'rank':names.index(expected)+1 if expected in names else None,
                            'elapsed_ms':round((time.perf_counter()-started)*1000,2)})
        report = {'scope':'Six synthetic document/query pairs, real local embedding model, no generated answers or customer data',
                  'top_1':sum(row['rank']==1 for row in results), 'top_5':sum(row['rank'] is not None for row in results),
                  'cases':results}
        target = ROOT / 'qa/redesign-2026-11-19/retrieval-quality.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally: fixture.doCleanups()


if __name__ == '__main__': main()
