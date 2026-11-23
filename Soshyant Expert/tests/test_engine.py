import copy
import hashlib
import http.cookiejar
import io
import json
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from expert import backup
from expert.config import Config, ROOT
from expert.engine import Engine
from expert.knowledge import Knowledge, LocalEmbeddings, chunk_parts, extract, normalize
from expert.server import Application, Handler, ThreadingHTTPServer
from expert.storage import Store, instance_lock
from expert.model import LocalModel
from test_cloud import ProviderStub


DOCUMENT = b"Aurora X200 warranty is 36 months from installation. Warranty claims require the installation report and serial number."


class FakeModel:
    state = "ready"
    calls = 0

    def available(self):
        return True

    def generate(self, messages, canceled=lambda: False):
        self.calls += 1
        self.messages = messages
        if "REQUIRED RESPONSE LANGUAGE: Persian" in messages[0]["content"]:
            return {"status": "answered", "answer": "مدت گارانتی ۳۶ ماه است. [1]", "citations": [1]}
        return {"status": "answered", "answer": "The warranty is 36 months. [1]", "citations": [1]}

    def close(self):
        pass


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "config").mkdir()
        shutil.copy2(ROOT / "config/capacity-models.json", self.root / "config/capacity-models.json")
        shutil.copy2(ROOT / "config/domain.json", self.root / "config/domain.json")
        settings = json.loads((ROOT / "config/server.json").read_text())
        settings["embedding_mode"] = "lexical"
        (self.root / "config/server.json").write_text(json.dumps(settings))
        self.config = Config(self.root)
        self.store = Store(self.config.data)
        self.owner = self.store.create_user("owner", "test-password-owner", "admin")
        self.other = self.store.create_user("other", "test-password-other")
        self.model = FakeModel()
        self.engine = Engine(self.store, self.config, self.model)
        self.addCleanup(self.engine.close)

    def index(self, body=DOCUMENT, name="manual.txt"):
        identity = self.engine.knowledge.add(name, body)
        self.engine.knowledge.index(identity)
        return identity


class KnowledgeTests(Fixture):
    def test_domain_is_configurable_and_does_not_accept_unbounded_data(self):
        domain = self.config.domain()
        domain["name"] = "A different field"
        self.config.save_domain(domain)
        self.assertEqual(self.config.domain()["name"], "A different field")
        domain["scope"] = "x" * 4000
        with self.assertRaises(ValueError):
            self.config.save_domain(domain)

    def test_extract_html_ignores_script_and_preserves_visible_text(self):
        text = extract("page.html", b"<p>Visible source text for indexing.</p><script>secret code</script>")[0][0]
        self.assertIn("Visible source", text)
        self.assertNotIn("secret code", text)

    def test_chunking_is_bounded_and_has_overlap(self):
        chunks = chunk_parts([("A long document " * 1000, "page 1")])
        self.assertTrue(len(chunks) > 1)
        self.assertLessEqual(max(len(c["text"]) for c in chunks), 650)

    def test_persian_letter_normalization(self):
        self.assertEqual(normalize("كي"), normalize("کی"))

    def test_unsupported_and_path_uploads_rejected(self):
        for filename in ("../file.txt", "folder\\file.txt", "run.exe"):
            with self.assertRaises(ValueError):
                self.engine.knowledge.add(filename, DOCUMENT)

    def test_search_returns_document_identity_version_and_location(self):
        identity = self.index()
        results, version = self.engine.knowledge.search("X200 warranty")
        self.assertEqual(results[0]["document_id"], identity)
        self.assertEqual(results[0]["document_version"], 1)
        self.assertEqual(version, "1")
        self.assertNotIn("vector", results[0])

    def test_archive_and_restore_change_search_visibility(self):
        identity = self.index()
        self.engine.knowledge.archive(identity)
        self.assertEqual(self.engine.knowledge.search("X200 warranty")[0], [])
        self.engine.knowledge.archive(identity, False)
        self.assertTrue(self.engine.knowledge.search("X200 warranty")[0])

    def test_permanent_deletion_requires_archive_and_removes_revisions(self):
        identity=self.index()
        with self.assertRaises(ValueError):self.engine.knowledge.delete_archived(identity)
        self.engine.knowledge.replace(identity,'updated.txt',DOCUMENT.replace(b'36',b'24'))
        self.engine.knowledge.index(identity)
        self.engine.knowledge.archive(identity)
        before=int(self.store.version())
        self.engine.knowledge.delete_archived(identity)
        self.assertGreater(int(self.store.version()),before)
        for table in ('documents','chunks','document_revisions'):
            column='id' if table=='documents' else 'document_id'
            self.assertIsNone(self.store.one(f'SELECT * FROM {table} WHERE {column}=?',(identity,)))
        with self.assertRaises(ValueError):self.engine.knowledge.archive(identity,False)

    def test_revision_keeps_original_and_new_version(self):
        identity = self.index()
        self.engine.knowledge.replace(identity, "revised.txt", DOCUMENT.replace(b"36", b"24"))
        self.assertEqual(self.engine.knowledge.search("warranty")[0], [])
        self.engine.knowledge.index(identity)
        result = self.engine.knowledge.search("warranty")[0][0]
        self.assertIn("24 months", result["text"])
        self.assertEqual(result["document_version"], 2)
        self.assertEqual(self.store.one("SELECT content FROM document_revisions")["content"], DOCUMENT)

    def test_index_failure_does_not_publish_partial_chunks(self):
        identity = self.engine.knowledge.add("scan.txt", b" ")
        with self.assertRaises(ValueError):
            self.engine.knowledge.index(identity)
        self.assertEqual(self.store.version(), "0")
        self.assertEqual(self.store.rows("SELECT * FROM chunks"), [])

    def test_missing_embedding_assets_fail_without_network(self):
        with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            with self.assertRaises(RuntimeError):
                LocalEmbeddings(self.config.settings).encode(["hello"])

    def test_cancel_index_prevents_publication(self):
        identity = self.engine.knowledge.add("manual.txt", DOCUMENT)
        with self.assertRaises(InterruptedError):
            self.engine.knowledge.index(identity, canceled=lambda: True)
        self.assertEqual(self.store.version(), "0")


class AnswerTests(Fixture):
    def test_english_is_default_even_for_persian_question_without_sources(self):
        conversation = self.store.new_conversation(self.owner)
        result = self.engine.answer(self.owner, conversation, "مدارک گارانتی چیست؟")
        self.assertEqual(result["response_language"], "English")
        self.assertIn("I could not find", result["answer"])

    def test_persian_override_applies_to_no_source_response(self):
        conversation = self.store.new_conversation(self.owner)
        result = self.engine.answer(self.owner, conversation, "Warranty?", response_language="fa")
        self.assertEqual(result["response_language"], "Persian")
        self.assertIn("اطلاعات کافی", result["answer"])

    def test_response_language_is_explicit_in_model_instructions(self):
        self.index()
        conversation = self.store.new_conversation(self.owner)
        result = self.engine.answer(self.owner, conversation, "X200 warranty?", response_language="fa")
        self.assertIn("REQUIRED RESPONSE LANGUAGE: Persian", self.model.messages[0]["content"])
        self.assertEqual(result["response_language"], "Persian")

    def test_wrong_language_is_repaired_before_saving(self):
        self.index()
        conversation = self.store.new_conversation(self.owner)
        responses = iter([
            {"status": "answered", "answer": "مدت گارانتی این دستگاه سی و شش ماه است. [1]", "citations": [1]},
            {"status": "answered", "answer": "The warranty is 36 months. [1]", "citations": [1]}])
        self.model.generate = lambda *args: next(responses)
        result = self.engine.answer(self.owner, conversation, "X200 warranty?", response_language="en")
        self.assertEqual(result["answer"], "The warranty is 36 months. [1]")

    def test_wrong_language_after_repair_is_not_published(self):
        self.index()
        conversation = self.store.new_conversation(self.owner)
        self.model.generate = lambda *args: {"status": "answered", "answer": "مدت گارانتی این دستگاه سی و شش ماه است. [1]", "citations": [1]}
        with self.assertRaises(RuntimeError):
            self.engine.answer(self.owner, conversation, "X200 warranty?", response_language="en")
        self.assertEqual(self.store.messages(conversation, self.owner), [])

    def test_empty_knowledge_refuses_without_model(self):
        conversation = self.store.new_conversation(self.owner)
        result = self.engine.answer(self.owner, conversation, "Warranty?")
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(self.model.calls, 0)

    def test_grounded_answer_retains_evidence_and_server_history(self):
        identity = self.index()
        conversation = self.store.new_conversation(self.owner)
        result = self.engine.answer(self.owner, conversation, "X200 warranty?")
        self.assertEqual(result["citations"][0]["document_id"], identity)
        messages = self.store.messages(conversation, self.owner)
        self.assertEqual(len(messages), 2)
        self.assertIn("36 months", result["citations"][0]["text"])
        self.assertNotIn("current-password", json.dumps(result))

    def test_conversations_are_owner_scoped(self):
        conversation = self.store.new_conversation(self.owner)
        with self.assertRaises(PermissionError):
            self.engine.answer(self.other, conversation, "Question?")

    def test_invalid_citations_do_not_save_answer(self):
        self.index()
        conversation = self.store.new_conversation(self.owner)
        self.model.generate = lambda *args: {"status": "answered", "answer": "Invented [99]", "citations": [99]}
        with self.assertRaises(RuntimeError):
            self.engine.answer(self.owner, conversation, "X200 warranty?")
        self.assertEqual(self.store.messages(conversation, self.owner), [])

    def test_no_citation_answer_fails_closed(self):
        self.index()
        conversation = self.store.new_conversation(self.owner)
        self.model.generate = lambda *args: {"status": "answered", "answer": "Unsupported answer", "citations": []}
        with self.assertRaises(RuntimeError):
            self.engine.answer(self.owner, conversation, "X200 warranty?")

    def test_canceled_answer_not_published(self):
        self.index()
        conversation = self.store.new_conversation(self.owner)
        with self.assertRaises(InterruptedError):
            self.engine.answer(self.owner, conversation, "X200 warranty?", canceled=lambda: True)
        self.assertEqual(self.store.messages(conversation, self.owner), [])

    def test_job_completes_and_is_owner_scoped(self):
        conversation = self.store.new_conversation(self.owner)
        identity = self.engine.submit(self.owner, "answer", {"conversation_id": conversation, "question": "Warranty?"})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.store.job(identity, self.owner)["status"] not in ("done", "failed"):
            time.sleep(.02)
        self.assertEqual(self.store.job(identity, self.owner)["status"], "done")
        self.assertIsNone(self.store.job(identity, self.other))


class BackupTests(Fixture):
    def test_backup_restore_preserves_documents_and_revokes_sessions(self):
        self.index()
        token, _ = self.store.login("owner", "test-password-owner")
        path = backup.create(self.store, self.config)
        self.store.execute("UPDATE documents SET active=0")
        backup.restore(path, self.config)
        self.assertEqual(self.store.one("SELECT active FROM documents")["active"], 1)
        self.assertIsNone(self.store.session(token))

    def test_instance_lock_blocks_restore_while_server_runs(self):
        with instance_lock(self.config.data):
            with self.assertRaises(RuntimeError):
                with instance_lock(self.config.data):
                    pass

    def test_password_not_stored_in_plaintext(self):
        self.assertNotIn("test-password", self.store.one("SELECT password FROM users WHERE id=?", (self.owner,))["password"])

    def test_opening_store_for_backup_does_not_reset_live_jobs(self):
        identity = self.store.new_job(self.owner, "answer")
        another = Store(self.config.data)
        self.assertEqual(another.job(identity, self.owner)["status"], "queued")


class HTTPTests(Fixture):
    def setUp(self):
        super().setUp()
        (self.root / "web").mkdir()
        for name in ("index.html", "app.js", "style.css", "i18n.js", "capacity.js", "library.js", "speech.js"):
            shutil.copy2(ROOT / "web" / name, self.root / "web" / name)
        self.application = Application(self.config, self.store, self.model)
        self.addCleanup(self.application.close)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.app = self.application
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ""

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, data=None, headers=None):
        request_headers = {"Content-Type": "application/json"}
        if data is not None:
            request_headers["X-CSRF-Token"] = self.csrf
        request_headers.update(headers or {})
        request = urllib.request.Request(self.base + path,
            data=json.dumps(data).encode() if data is not None else None, headers=request_headers)
        try:
            response = self.client.open(request, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            return response.status, json.loads(body) if response.headers.get_content_type() == "application/json" else body

    def login(self, username="owner", password="test-password-owner"):
        status, result = self.request("/api/login", {"username": username, "password": password})
        self.assertEqual(status, 200)
        self.csrf = result["csrf"]

    def test_anonymous_cannot_read_documents(self):
        self.assertEqual(self.request("/api/documents")[0], 403)

    def test_access_api_enforces_role_csrf_downloads_and_revocation(self):
        doc=self.index()
        self.assertEqual(self.request('/api/groups')[0],403)
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/groups')[0],403)
        self.assertEqual(self.request('/api/documents/'+doc+'/access')[0],403)
        self.assertEqual(self.request('/api/documents/'+doc+'/access',{'restricted':False})[0],403)
        self.login()
        self.assertEqual(self.request('/api/groups',{'name':'Team','members':[]},{'X-CSRF-Token':'wrong'})[0],403)
        status,group=self.request('/api/groups',{'name':'Team','members':[self.other]})
        self.assertEqual(status,201)
        self.assertEqual(self.request('/api/documents/'+doc+'/access',{'restricted':True,'groups':[group['id']]})[0],200)
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/documents')[1][0]['id'],doc)
        self.assertEqual(self.request('/api/documents/'+doc+'/download')[0],200)
        self.login()
        self.assertEqual(self.request('/api/groups/'+group['id']+'/delete',{})[0],400)
        self.assertEqual(self.request('/api/groups/'+group['id']+'/delete',{'confirm':True})[0],200)
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/documents')[1],[])
        self.assertEqual(self.request('/api/documents/'+doc+'/download')[0],403)
        self.login()
        self.assertEqual(self.request('/api/documents/'+doc+'/access')[1],{'restricted':True,'groups':[]})

    def test_private_uploads_are_restricted_before_indexing(self):
        self.login()
        request=urllib.request.Request(self.base+'/api/documents?filename=private.txt&restricted=1',data=DOCUMENT,
            headers={'Content-Type':'application/octet-stream','X-CSRF-Token':self.csrf})
        with self.client.open(request,timeout=10) as response:result=json.load(response)
        identity=result['document_id']
        self.assertEqual(self.store.one('SELECT restricted FROM document_access WHERE document_id=?',(identity,))['restricted'],1)
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/documents')[1],[])
        self.assertEqual(self.request('/api/documents/'+identity+'/download')[0],403)

    def test_workflow_routes_require_admin_and_csrf(self):
        folder=self.root/'incoming';folder.mkdir();(folder/'source.txt').write_bytes(DOCUMENT)
        for path in ('/api/watched-folders','/api/reviews'):
            self.assertEqual(self.request(path)[0],403)
        self.login('other','test-password-other')
        for path in ('/api/watched-folders','/api/reviews'):
            self.assertEqual(self.request(path)[0],403)
        self.assertEqual(self.request('/api/watched-folders',{'path':str(folder)})[0],403)
        self.assertEqual(self.request('/api/reviews/1',{'status':'resolved'})[0],403)
        self.login()
        self.assertEqual(self.request('/api/watched-folders',{'path':str(folder)},{'X-CSRF-Token':'wrong'})[0],403)
        status,result=self.request('/api/watched-folders',{'path':str(folder),'recursive':True})
        self.assertEqual(status,201);identity=result['id']
        self.assertEqual(self.request('/api/watched-folders/'+identity+'/scan',{})[0],200)
        changes=self.request('/api/watched-folders')[1]['changes'];self.assertEqual(changes[0]['kind'],'new')
        route='/api/watched-changes/'+changes[0]['id']+'/ignore'
        self.assertEqual(self.request(route,{'sha':'stale'})[0],400)
        self.assertEqual(self.request(route,{'sha':changes[0]['sha']})[0],200)
        self.assertEqual(self.request('/api/watched-folders')[1]['changes'],[])
        self.assertEqual(self.request('/api/watched-folders/'+identity+'/enabled',{'enabled':'false'})[0],400)
        self.assertEqual(self.request('/api/watched-folders/'+identity+'/enabled',{'enabled':False})[0],200)
        self.assertFalse(self.request('/api/watched-folders')[1]['folders'][0]['enabled'])
        self.assertEqual(self.request('/api/watched-folders/'+identity+'/access',{'restricted':'true'})[0],400)
        self.assertEqual(self.request('/api/watched-folders/'+identity+'/access',{'restricted':True})[0],200)
        self.assertTrue(self.request('/api/watched-folders')[1]['folders'][0]['restricted'])
        self.assertEqual(self.request('/api/reviews?kind=unknown')[0],400)
        self.assertEqual(self.request('/api/reviews?state=unknown')[0],400)
        self.assertEqual(self.request('/api/reviews?before=bad')[0],400)
        chat=self.store.new_conversation(self.other)
        answer=self.application.engine.answer(self.other,chat,'A question without evidence')
        route='/api/reviews/'+str(answer['message_id'])
        self.assertEqual(self.request(route,{'status':'resolved','note':'Need a source'},{'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request(route,{'status':'resolved','note':'Need a source'})[0],200)
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/feedback',{'message_id':answer['message_id'],'rating':'incorrect','note':'Please review again'})[0],200)
        self.login()
        self.assertEqual(self.request('/api/reviews?kind=incorrect')[1]['items'][0]['resolved'],0)

    def test_dashboard_admin_only_and_counts_actual_work(self):
        self.assertEqual(self.request('/api/dashboard')[0],403)
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/dashboard')[0],403)
        identity=self.index()
        failed=self.engine.knowledge.add('bad.txt',b'not yet indexed')
        self.store.execute("UPDATE documents SET status='failed',error='Extraction failed' WHERE id=?",(failed,))
        job=self.store.new_job(self.owner,'answer')
        self.login()
        status,result=self.request('/api/dashboard')
        self.assertEqual(status,200)
        self.assertEqual(result['documents']['active'],2)
        self.assertEqual(result['documents']['by_status'],{'failed':1,'indexed':1})
        self.assertGreater(result['documents']['passages'],0)
        self.assertEqual(result['users']['active'],2)
        self.assertEqual(result['jobs'],[{'kind':'answer','status':'queued','count':1}])
        self.assertEqual(result['attention'][0]['id'],failed)
        self.assertIsNone(result['backup']['latest'])
        self.assertNotIn('password',json.dumps(result))
        self.engine.knowledge.archive(identity)
        result=self.request('/api/dashboard')[1]
        self.assertEqual(result['documents']['active'],1)
        self.assertEqual(result['documents']['archived'],1)
        self.assertEqual(result['documents']['passages'],0)

    def test_chat_management_is_owner_scoped_and_requires_csrf_and_confirmation(self):
        self.login()
        identity = self.request('/api/conversations', {})[1]['id']
        route = '/api/conversations/' + identity
        self.assertEqual(self.request(route+'/rename', {'title':'My research'})[0], 200)
        self.assertEqual(self.store.conversation(identity,self.owner)['title'],'My research')
        for title in ('', ' '*3, 'x'*101, 12):
            self.assertEqual(self.request(route+'/rename', {'title':title})[0], 400)
        self.assertEqual(self.request(route+'/delete', {'confirm':True}, {'X-CSRF-Token':'wrong'})[0],403)
        for confirmation in (None,False,'true'):
            self.assertEqual(self.request(route+'/delete', {'confirm':confirmation})[0],400)
        self.login('other','test-password-other')
        self.assertEqual(self.request(route+'/rename', {'title':'stolen'})[0],403)
        self.assertEqual(self.request(route+'/delete', {'confirm':True})[0],403)
        self.login()
        self.application.engine.inflight.add(identity)
        self.assertEqual(self.request(route+'/delete', {'confirm':True})[0],400)
        self.application.engine.inflight.remove(identity)
        self.assertEqual(self.request(route+'/delete', {'confirm':True})[0],200)
        self.assertEqual(self.request(route+'/delete', {'confirm':True})[0],403)
        with self.assertRaises(PermissionError):
            self.application.engine.submit(self.owner,'answer',{'conversation_id':identity,'question':'hello'})

    def test_chat_delete_removes_answers_feedback_and_job_copies_only_for_that_chat(self):
        self.login()
        self.index()
        identity=self.store.new_conversation(self.owner)
        other_chat=self.store.new_conversation(self.other)
        keep=self.store.new_conversation(self.owner)
        result=self.application.engine.answer(self.owner,identity,'What is the warranty?')
        self.store.execute('INSERT INTO feedback(user_id,message_id,rating,note,created) VALUES(?,?,?,?,?)',
                           (self.owner,result['message_id'],'helpful','',time.time()))
        job=self.store.new_job(self.owner,'answer');self.store.job_update(job,status='done',result=result)
        legacy_job=self.store.new_job(self.owner,'answer');self.store.job_update(legacy_job,status='done',result={'conversation_id':identity,'answer':'saved copy'})
        keep_job=self.store.new_job(self.owner,'answer');self.store.job_update(keep_job,status='done',result={'message_id':999999})
        self.assertEqual(self.request('/api/conversations/'+identity+'/delete',{'confirm':True})[0],200)
        self.assertIsNone(self.store.conversation(identity,self.owner))
        self.assertFalse(self.store.rows('SELECT id FROM messages WHERE conversation_id=?',(identity,)))
        self.assertFalse(self.store.rows('SELECT id FROM feedback WHERE message_id=?',(result['message_id'],)))
        self.assertIsNone(self.store.job(job,self.owner))
        self.assertIsNone(self.store.job(legacy_job,self.owner))
        self.assertIsNotNone(self.store.job(keep_job,self.owner))
        self.assertIsNotNone(self.store.conversation(other_chat,self.other))
        self.assertIsNotNone(self.store.conversation(keep,self.owner))

    def test_successful_shared_gateway_logins_do_not_consume_failure_budget(self):
        for _ in range(12):self.login()
        self.assertEqual(self.application.attempts['127.0.0.1'],[])
        for _ in range(10):self.assertEqual(self.request('/api/login',{'username':'owner','password':'wrong-password'})[0],403)
        self.assertEqual(self.request('/api/login',{'username':'owner','password':'wrong-password'})[0],429)

    def test_archived_delete_requires_admin_csrf_and_confirmation(self):
        identity=self.index();route=f'/api/documents/{identity}/delete'
        self.login('other','test-password-other')
        self.assertEqual(self.request(route,{'confirm':True})[0],403)
        self.login()
        self.assertEqual(self.request(route,{'confirm':True})[0],400)
        self.engine.knowledge.archive(identity)
        self.assertEqual(self.request(route,{})[0],400)
        self.assertEqual(self.request(route,{'confirm':'true'})[0],400)
        self.assertEqual(self.request(route,{'confirm':True},{'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request(route,{'confirm':True})[0],200)
        self.assertIsNone(self.store.one('SELECT id FROM documents WHERE id=?',(identity,)))
        self.assertEqual(self.request(f'/api/documents/{identity}/restore',{})[0],400)
        self.assertEqual(self.store.one("SELECT action FROM audit WHERE object_id=? ORDER BY id DESC",(identity,))['action'],'document_delete')

    def test_model_management_requires_admin(self):
        self.assertEqual(self.request('/api/models')[0], 403)
        self.login('other', 'test-password-other')
        self.assertEqual(self.request('/api/models')[0], 403)
        self.assertEqual(self.request('/api/models/register', {'path':'missing.gguf'})[0], 403)
        self.assertEqual(self.request('/api/models/activate', {'model_id':'missing'})[0], 403)
        self.login()
        self.assertEqual(self.request('/api/models')[0], 200)
        self.assertEqual(self.request('/api/models/activate', {'model_id':'missing'})[0], 400)

    def test_api_model_opt_in_and_grounded_answer_without_real_network(self):
        payload={'name':'API test','provider':'openai','model':'test-model','api_key':'test-only-server-key'}
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/models/cloud',payload)[0],403)
        self.login()
        status,result=self.request('/api/models/cloud',payload)
        self.assertEqual(status,201)
        self.assertNotIn(payload['api_key'],json.dumps(result))
        identity=result['profile']['id']
        self.application.engine.model=LocalModel(self.config)
        provider=ProviderStub();self.application.engine.model.cloud.opener=provider
        self.assertEqual(self.request('/api/models/activate',{'model_id':identity})[0],400)
        self.assertFalse(provider.requests)
        self.assertEqual(self.request('/api/models/activate',{'model_id':identity,'confirm_cloud':True})[0],200)
        self.assertEqual(self.request('/api/status')[1]['model']['kind'],'cloud')
        self.assertEqual(self.config.settings['cloud_model_id'],identity)
        conversation=self.request('/api/conversations',{})[1]['id']
        calls=len(provider.requests)
        self.assertEqual(self.request('/api/ask',{'conversation_id':conversation,'question':'Warranty?','model_selection':'stale-selection'})[0],400)
        self.assertEqual(len(provider.requests),calls)
        self.index()
        conversation=self.request('/api/conversations',{})[1]['id']
        _,job=self.request('/api/ask',{'conversation_id':conversation,'question':'Warranty?'})
        for _ in range(100):
            _,outcome=self.request('/api/jobs/'+job['job_id'])
            if outcome['status'] in ('done','failed'):break
            time.sleep(.02)
        self.assertEqual(outcome['status'],'done',outcome)
        self.assertEqual(outcome['result']['citations'][0]['document_version'],1)
        self.assertIn('Aurora',provider.requests[-1].data.decode())
        before=len(provider.requests)
        provider.error=urllib.error.HTTPError('https://api.openai.com',401,'denied',{},None)
        with self.assertRaises(ValueError):self.application.models.activate(identity,True)
        self.assertEqual(self.config.settings['cloud_model_id'],identity)
        self.assertEqual(len(provider.requests),before+1)

    def test_model_folder_scan_and_browser_require_admin(self):
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/models/folders')[0],403)
        self.assertEqual(self.request('/api/models/scan',{'path':str(self.root)})[0],403)
        self.login()
        self.assertEqual(self.request('/api/models/folders')[0],200)
        status,result=self.request('/api/models/scan',{'path':str(self.root/'assets/models'),'recursive':True})
        self.assertEqual(status,200)
        self.assertEqual(result['scan']['found'],0)
        self.assertEqual(self.request('/api/models/scan',{'path':'missing-folder'})[0],400)

    def test_answers_are_rejected_during_model_activation(self):
        self.application.engine.model_changing = True
        self.login()
        conversation = self.request('/api/conversations', {})[1]['id']
        self.assertEqual(self.request('/api/ask', {'conversation_id':conversation,'question':'Warranty?'})[0],400)
        self.application.engine.model_changing = False

    def test_folder_import_deduplicates_indexed_content(self):
        def upload():
            request=urllib.request.Request(self.base+'/api/documents/import?filename=manual.txt', data=DOCUMENT,
                headers={'Content-Type':'application/octet-stream','X-CSRF-Token':self.csrf})
            try: response=self.client.open(request, timeout=10)
            except urllib.error.HTTPError as exc: response=exc
            with response: return response.status,json.loads(response.read())
        self.login('other', 'test-password-other')
        self.assertEqual(upload()[0],403)
        self.login()
        status,result=upload()
        self.assertEqual(status,202)
        for _ in range(100):
            _,job=self.request('/api/jobs/'+result['job_id'])
            if job['status']=='done':break
            time.sleep(.02)
        self.assertEqual(job['status'],'done')
        status,duplicate=upload()
        self.assertEqual(status,200)
        self.assertTrue(duplicate['skipped'])
        self.assertEqual(duplicate['document_id'],result['document_id'])
        self.assertEqual(len(self.request('/api/documents')[1]),1)

    def test_capacity_authentication_and_validation(self):
        self.assertEqual(self.request('/api/capacity/catalog')[0], 403)
        self.login('other', 'test-password-other')
        self.assertEqual(len(self.request('/api/capacity/catalog')[1]['models']), 5)
        status, result = self.request('/api/capacity/estimate', {'users': 10})
        self.assertEqual(status, 200)
        self.assertEqual(result['active_generations'], 10)
        self.assertEqual(self.request('/api/capacity/estimate', {'users': -1})[0], 400)
        self.csrf = 'wrong'
        self.assertEqual(self.request('/api/capacity/estimate', {})[0], 403)

    def test_ocr_setting_requires_admin_and_csrf_and_persists(self):
        self.login("other", "test-password-other")
        self.assertEqual(self.request("/api/ocr", {"enabled": False})[0], 403)
        self.login()
        self.assertEqual(self.request("/api/ocr", {"enabled": False}, {"X-CSRF-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("/api/ocr", {"enabled": "no"})[0], 400)
        status, result = self.request("/api/ocr", {"enabled": False})
        self.assertEqual(status, 200)
        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["languages"], ["en"])
        self.assertFalse(json.loads((self.root / "config/server.json").read_text())["ocr_enabled"])
        self.assertFalse(self.request("/api/status")[1]["ocr"]["enabled"])
        self.assertTrue(self.request("/api/ocr", {"enabled": True})[1]["enabled"])

    def test_csrf_is_required(self):
        self.login()
        self.csrf = "wrong"
        self.assertEqual(self.request("/api/conversations", {})[0], 403)

    def test_cross_origin_request_rejected(self):
        self.assertEqual(self.request("/api/login", {}, {"Origin": "https://other.example"})[0], 403)

    def test_unrecognized_host_rejected(self):
        self.assertEqual(self.request("/healthz", headers={"Host": "other.example"})[0], 403)

    def test_user_cannot_manage_users_or_domain(self):
        self.login("other", "test-password-other")
        self.assertEqual(self.request("/api/users")[0], 403)
        self.assertEqual(self.request("/api/domain", self.config.domain())[0], 403)

    def test_other_user_cannot_access_messages(self):
        conversation = self.store.new_conversation(self.owner)
        self.login("other", "test-password-other")
        self.assertEqual(self.request(f"/api/conversations/{conversation}/messages")[0], 403)

    def test_api_question_job_finishes(self):
        self.login()
        _, conversation = self.request("/api/conversations", {})
        status, job = self.request("/api/ask", {"conversation_id": conversation["id"], "question": "Warranty?"})
        self.assertEqual(status, 202)
        for _ in range(100):
            _, result = self.request("/api/jobs/" + job["job_id"])
            if result["status"] == "done":
                break
            time.sleep(.02)
        self.assertEqual(result["result"]["status"], "insufficient")

    def test_api_rejects_unknown_response_language(self):
        self.login()
        _, conversation = self.request("/api/conversations", {})
        status, _ = self.request("/api/ask", {"conversation_id": conversation["id"], "question": "Warranty?", "response_language": "unknown"})
        self.assertEqual(status, 400)

    def test_historical_source_download_matches_cited_revision(self):
        identity = self.index()
        self.engine.knowledge.replace(identity, "revision.txt", DOCUMENT.replace(b"36", b"24"))
        self.engine.knowledge.index(identity)
        self.login()
        status, content = self.request(f"/api/documents/{identity}/download?version=1")
        self.assertEqual(status, 200)
        self.assertEqual(content, DOCUMENT)

    def test_disabled_user_sessions_are_revoked(self):
        token, csrf = self.store.login("other", "test-password-other")
        self.login()
        self.request(f"/api/users/{self.other}/active", {"active": False})
        self.assertIsNone(self.store.session(token))

    def test_setup_cannot_be_repeated(self):
        self.assertEqual(self.request("/api/setup", {"code": "anything"})[0], 403)

    def test_logout_ends_session(self):
        self.login()
        self.assertEqual(self.request("/api/logout", {})[0], 200)
        self.assertEqual(self.request("/api/me")[0], 403)

    def test_static_assets_local_and_csp_set(self):
        status, content = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b'/app.js', content)
        self.assertNotIn(b'src="https://', content)
        self.assertNotIn(b'href="https://', content)
        with self.client.open(self.base, timeout=5) as response:
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
