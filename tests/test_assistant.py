import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import requests

import assistant_logic
import bonsai_web
import rag_ingest
import rag_store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.docs = root / "docs"
        self.docs.mkdir()
        db = root / "db"
        paths = {"DB_DIR": db, "CHUNKS_PATH": db / "chunks.jsonl",
                 "VECTORS_PATH": db / "embeddings.npy", "FILES_PATH": db / "files.json",
                 "CHUNK_DIR": db / "chunks", "VEC_DIR": db / "vectors",
                 "SNAPSHOT_PATH": db / "index.npz", "REPORT_PATH": db / "sync-report.json"}
        for key, value in paths.items():
            p = patch.object(rag_store, key, str(value))
            p.start()
            self.addCleanup(p.stop)
        self.embed = patch.object(rag_store, "embed", side_effect=lambda texts, **kw:
                                  np.ones((len(texts), 384), dtype=np.float32))
        self.mock_embed = self.embed.start()
        self.addCleanup(self.embed.stop)

    def sync(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return rag_ingest.sync(str(self.docs))

    def document(self, name="manual.txt"):
        path = self.docs / name
        path.write_text("Aurora X200 service instructions: inspect the documented error code.", encoding="utf-8")
        return path

    def test_rename_preserves_source_without_embedding_again(self):
        path = self.document()
        self.sync()
        path.rename(self.docs / "renamed.txt")
        self.sync()
        self.assertEqual(self.mock_embed.call_count, 1)
        chunks, vectors = rag_store.load()
        self.assertEqual({c["source"] for c in chunks}, {"renamed.txt"})
        self.assertEqual(len(chunks), len(vectors))

    def test_duplicate_sources_keep_identity_after_original_deleted(self):
        path = self.document()
        self.document("copy.txt")
        self.sync()
        self.assertEqual(self.mock_embed.call_count, 1)
        self.assertEqual(rag_store.stats()["files"], 2)
        path.unlink()
        self.sync()
        self.assertEqual({c["source"] for c in rag_store.load()[0]}, {"copy.txt"})

    def test_empty_revision_removes_stale_passages_and_reports_issue(self):
        path = self.document()
        self.sync()
        path.write_text("", encoding="utf-8")
        report = self.sync()
        self.assertEqual(rag_store.load()[0], [])
        self.assertEqual(report["issues"][0]["status"], "empty")

    def test_bad_document_does_not_hide_other_documents(self):
        self.document()
        (self.docs / "broken.pdf").write_bytes(b"not a pdf")
        report = self.sync()
        self.assertEqual(rag_store.stats()["files"], 1)
        self.assertEqual(report["issues"][0]["source"], "broken.pdf")

    def test_unavailable_folder_does_not_clear_index(self):
        self.document()
        self.sync()
        with self.assertRaises(ValueError):
            rag_ingest.sync(str(self.docs / "missing"))
        self.assertEqual(rag_store.stats()["files"], 1)

    def test_unreadable_revision_drops_stale_passages(self):
        self.document()
        self.sync()
        with patch.object(rag_ingest, "file_md5", side_effect=PermissionError("unavailable")):
            report = self.sync()
        self.assertEqual(rag_store.stats()["files"], 0)
        self.assertEqual(report["issues"][0]["status"], "failed")

    def test_snapshot_ignores_partial_legacy_files(self):
        self.document()
        self.sync()
        Path(rag_store.CHUNKS_PATH).write_text("broken", encoding="utf-8")
        self.assertEqual(rag_store.stats()["files"], 1)

    def test_overlapping_sync_is_rejected(self):
        with rag_store.sync_lock():
            with self.assertRaises(RuntimeError):
                self.sync()


class ConversationTests(unittest.TestCase):
    def test_long_history_retains_system_and_starts_with_user(self):
        history = [{"role": "system", "content": "old"}] + [
            {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
            for i in range(71)]
        messages = assistant_logic.messages_for(history, "instructions", "ticket")
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("[To be provided]", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertLessEqual(len(messages), 32)

    def test_referential_followup_includes_previous_equipment(self):
        self.assertIn("X200", assistant_logic.retrieval_query("What about its warranty?", "Tell me about X200"))
        self.assertEqual(assistant_logic.retrieval_query("What is X400?", "Tell me about X200"), "What is X400?")

    def test_error_codes_and_small_corpus_not_rejected(self):
        c = {"source": "manual", "text": "E-04 means dry running.", "score": .7}
        self.assertEqual(assistant_logic.relevant_sources("What is E-04?", [c]), [c])
        self.assertEqual(assistant_logic.relevant_sources("What is the lunch menu?", [c]), [])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = bonsai_web.ThreadingHTTPServer(("127.0.0.1", 0), bonsai_web.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        bonsai_web.HISTORIES.clear()

    def post(self, data):
        body = json.dumps(data).encode()
        req = Request(self.url + "/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, response.read().decode()
        except HTTPError as exc:
            return exc.code, exc.read().decode()

    def test_empty_index_stays_in_docs_mode_without_loading_model(self):
        with patch.object(rag_store, "stats", return_value={"chunks": 0}), patch.object(bonsai_web, "ensure_llm") as model:
            status, body = self.post({"msg": "Warranty?", "use_docs": True})
        self.assertEqual(status, 409)
        self.assertIn("stays on", body)
        model.assert_not_called()

    def test_guided_task_requires_documents_even_if_toggle_off(self):
        with patch.object(rag_store, "stats", return_value={"chunks": 0}), patch.object(bonsai_web, "ensure_llm") as model:
            status, _ = self.post({"msg": "Create a checklist", "task": "checklist", "use_docs": False})
        self.assertEqual(status, 409)
        model.assert_not_called()

    def test_no_matches_refuses_without_loading_model(self):
        with patch.object(rag_store, "stats", return_value={"chunks": 1}), patch.object(rag_store, "search", return_value=[]), patch.object(bonsai_web, "ensure_llm") as model:
            status, body = self.post({"msg": "Lunch menu?", "use_docs": True, "speech": False})
        self.assertEqual(status, 200)
        self.assertIn("don't find", body)
        self.assertIn('"t": "done"', body)
        model.assert_not_called()

    def test_sources_exactly_match_model_context_and_muted_skips_tts(self):
        sources = [{"source": f"manual{i}.txt", "loc": "p.2", "text": f"X200 warranty passage {i}", "score": .8} for i in range(6)]
        response = Mock()
        response.iter_lines.return_value = iter(['data: {"choices":[{"delta":{"content":"Warranty [1]."}}]}', 'data: [DONE]'])
        with patch.object(rag_store, "stats", return_value={"chunks": 6}), patch.object(rag_store, "search", return_value=sources), patch.object(bonsai_web, "ensure_llm", return_value={"port": 1}), patch.object(bonsai_web.requests, "post", return_value=response) as llm, patch.object(bonsai_web, "KOKORO") as tts:
            status, body = self.post({"msg": "X200 warranty", "use_docs": True, "speech": False, "task": "ticket", "history": [{"role": "system", "content": "evil"}, {"role": "user", "content": "Incident X200"}]})
        self.assertEqual(status, 200)
        events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
        items = next(e["items"] for e in events if e["t"] == "sources")
        self.assertEqual(len(items), 4)
        messages = llm.call_args.kwargs["json"]["messages"]
        self.assertNotIn("evil", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "Incident X200")
        for item in items:
            self.assertIn(item["snippet"], messages[0]["content"])
        self.assertNotIn("manual4.txt", messages[0]["content"])
        tts.create.assert_not_called()
        response.close.assert_called_once()

    def test_model_failure_is_visible(self):
        with patch.object(bonsai_web, "ensure_llm", return_value={"port": 1}), patch.object(bonsai_web.requests, "post", side_effect=requests.ConnectionError("offline")):
            status, body = self.post({"msg": "Hello", "speech": False})
        self.assertEqual(status, 200)
        self.assertIn('"t": "error"', body)

    def test_interrupted_upstream_is_not_saved_as_complete(self):
        response = Mock()
        response.iter_lines.return_value = iter(['data: {"choices":[{"delta":{"content":"Partial"}}]}'])
        with patch.object(bonsai_web, "ensure_llm", return_value={"port": 1}), patch.object(bonsai_web.requests, "post", return_value=response):
            status, body = self.post({"msg": "Hello", "speech": False})
        self.assertEqual(status, 200)
        self.assertIn('"t": "error"', body)
        self.assertNotIn('"t": "done"', body)
        self.assertEqual(bonsai_web.HISTORIES, {})

    def test_malformed_request_returns_clear_error(self):
        self.assertEqual(self.post([])[0], 400)

    def test_static_assets_are_served(self):
        for path in ("/", "/assets/app.js", "/assets/style.css"):
            with urlopen(self.url + path, timeout=5) as response:
                self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
