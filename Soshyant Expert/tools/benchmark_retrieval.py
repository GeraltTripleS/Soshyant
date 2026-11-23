"""Compare checked-in retrieval with current retrieval on a disposable lexical corpus."""
import ast
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_engine import Fixture
import expert.knowledge as knowledge_module


def main():
    baseline = subprocess.check_output(['git', 'show', 'HEAD:Soshyant Expert/expert/knowledge.py'], cwd=ROOT.parent, text=True)
    tree = ast.parse(baseline)
    klass = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Knowledge')
    method = next(node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name == 'search')
    namespace = dict(vars(knowledge_module))
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<baseline-search>', 'exec'), namespace)
    fixture = Fixture(); fixture.setUp()
    try:
        identity = fixture.index()
        with fixture.store.connect() as db:
            db.execute('DELETE FROM chunks')
            db.executemany('INSERT INTO chunks(id,document_id,document_version,location,text) VALUES(?,?,1,?,?)', [
                (f'benchmark-{i}', identity, f'page {i+1}',
                 f'Unit X{i:04} maintenance: inspect the pressure valve every {30+i%100} days. '
                 f'Warranty duration is {12+i%36} months. Keep the inspection record. ' * 3)
                for i in range(2000)])
            fixture.store.version(db)
        knowledge = fixture.engine.knowledge
        old = types.MethodType(namespace['search'], knowledge)
        queries = ['X0042 maintenance pressure', 'X1032 warranty duration', 'inspection records valve'] * 10
        timings = {}
        for label, search in [('baseline', old), ('current', knowledge.search)]:
            values = []
            for question in queries:
                start = time.perf_counter(); search(question, owner=fixture.owner)
                values.append((time.perf_counter()-start)*1000)
            timings[label] = {'cold_ms': round(values[0], 2), 'warm_median_ms': round(statistics.median(values[1:]), 2),
                              'warm_p95_ms': round(sorted(values[1:])[int(.95*(len(values)-2))], 2)}
        timings['warm_speedup'] = round(timings['baseline']['warm_median_ms']/timings['current']['warm_median_ms'], 2)
        timings['scope'] = '2000 synthetic passages; lexical retrieval only; 30 sequential queries; no LLM generation or concurrent load'
        report = ROOT / 'qa/redesign-2026-11-19/retrieval-benchmark.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(timings, indent=2), encoding='utf-8')
        print(json.dumps(timings, indent=2))
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    main()
