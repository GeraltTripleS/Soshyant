import json
import time
from unittest.mock import patch

from test_engine import Fixture, DOCUMENT
from expert.server import Application
from expert import permissions


class PermissionTests(Fixture):
    def setUp(self):
        super().setUp()
        self.app=Application(self.config,self.store,self.model)
        self.addCleanup(self.app.close)

    def group(self,members=None):
        return permissions.save_group(self.app,None,{'name':'Engineering','members':members or []})

    def test_groups_filter_library_and_retrieval_before_model_context(self):
        document=self.index()
        group=self.group([self.other])
        permissions.save_document(self.app,document,{'restricted':True,'groups':[]})
        self.assertEqual(self.app.engine.knowledge.list_documents(owner=self.other),[])
        self.assertEqual(self.app.engine.knowledge.search('warranty',owner=self.other)[0],[])
        chat=self.store.new_conversation(self.other)
        calls=self.model.calls
        result=self.app.engine.answer(self.other,chat,'What is the warranty?')
        self.assertEqual(result['status'],'insufficient');self.assertEqual(self.model.calls,calls)
        permissions.save_document(self.app,document,{'restricted':True,'groups':[group]})
        self.assertEqual(len(self.app.engine.knowledge.list_documents(owner=self.other)),1)
        self.assertTrue(self.app.engine.knowledge.search('warranty',owner=self.other)[0])
        self.assertTrue(self.app.engine.knowledge.search('warranty',owner=self.owner)[0])

    def test_revocation_redacts_history_jobs_and_deleted_document_tombstones(self):
        document=self.index();group=self.group([self.other])
        permissions.save_document(self.app,document,{'restricted':True,'groups':[group]})
        chat=self.store.new_conversation(self.other)
        result=self.app.engine.answer(self.other,chat,'What is the warranty?')
        job=self.store.new_job(self.other,'answer');self.store.job_update(job,status='done',result=result)
        permissions.save_group(self.app,group,{'name':'Engineering','members':[]})
        messages=self.store.messages(chat,self.other)
        self.assertTrue(messages[1]['result']['restricted'])
        self.assertNotIn('36 months',json.dumps(messages))
        self.assertNotIn(document,json.dumps(messages))
        self.assertTrue(self.store.job(job,self.other)['result']['restricted'])
        self.app.engine.knowledge.archive(document)
        self.app.engine.knowledge.delete_archived(document)
        self.assertTrue(self.store.messages(chat,self.other)[1]['result']['restricted'])
        self.assertIsNotNone(self.store.one('SELECT * FROM document_access WHERE document_id=?',(document,)))

    def test_revoked_history_is_not_sent_back_to_model(self):
        private=self.index();chat=self.store.new_conversation(self.other)
        self.app.engine.answer(self.other,chat,'What is the warranty?')
        permissions.save_document(self.app,private,{'restricted':True,'groups':[]})
        public=self.index(b'Maintenance requires an approved monthly schedule.','schedule.txt')
        with patch.object(self.model,'generate',return_value={'status':'answered','answer':'Use the monthly maintenance schedule. [1]','citations':[1]}) as generate:
            result=self.app.engine.answer(self.other,chat,'What maintenance schedule is required?')
        prompt=json.dumps(generate.call_args[0][0])
        self.assertNotIn('36 months',prompt)
        self.assertNotIn(private,prompt)
        self.assertIn(public,result['access_documents'])

    def test_history_dependencies_survive_into_followup_answers(self):
        original=self.index();chat=self.store.new_conversation(self.other)
        self.app.engine.answer(self.other,chat,'What is the warranty?')
        second=self.index(b'Maintenance follows a monthly schedule.','schedule.txt')
        with patch.object(self.model,'generate',return_value={'status':'answered','answer':'Use the monthly maintenance schedule. [1]','citations':[1]}):
            result=self.app.engine.answer(self.other,chat,'What maintenance schedule is required?')
        self.assertEqual(set(result['access_documents']),{original,second})
        permissions.save_document(self.app,original,{'restricted':True,'groups':[]})
        messages=self.store.messages(chat,self.other)
        self.assertTrue(messages[-1]['result']['restricted'])

    def test_access_change_during_generation_prevents_publication(self):
        document=self.index();chat=self.store.new_conversation(self.other)
        def generate(*args):
            permissions.save_document(self.app,document,{'restricted':True,'groups':[]})
            return {'status':'answered','answer':'The warranty is 36 months. [1]','citations':[1]}
        with patch.object(self.model,'generate',side_effect=generate):
            with self.assertRaises(InterruptedError):self.app.engine.answer(self.other,chat,'What is the warranty?')
        self.assertEqual(self.store.messages(chat,self.other),[])

    def test_private_creation_is_atomic_and_invalid_members_roll_back(self):
        document=self.app.engine.knowledge.add('private.txt',DOCUMENT,restricted=True)
        self.assertFalse(permissions.visible(self.store,self.other,[document]))
        self.assertTrue(permissions.visible(self.store,self.owner,[document]))
        with self.assertRaises(ValueError):self.group(['missing-user'])
        self.assertEqual(permissions.groups(self.store),[])
        with self.assertRaises(ValueError):permissions.save_document(self.app,document,{'restricted':True,'groups':['missing-group']})
        self.assertEqual(permissions.document(self.store,document),{'restricted':True,'groups':[]})
        job=self.store.new_job(self.other,'answer')
        permissions.save_document(self.app,document,{'restricted':False,'groups':[]})
        self.assertEqual(self.store.job(job,self.other)['canceled'],1)

    def test_legacy_responses_without_full_dependencies_fail_closed(self):
        document=self.index()
        legacy={'status':'answered','answer':'Legacy answer with incomplete provenance','citations':[]}
        self.assertFalse(permissions.filter_result(self.store,self.other,legacy).get('restricted',False))
        permissions.save_document(self.app,document,{'restricted':True,'groups':[]})
        self.assertTrue(permissions.filter_result(self.store,self.other,legacy)['restricted'])
        self.assertFalse(permissions.filter_result(self.store,self.owner,legacy).get('restricted',False))

    def test_watched_private_documents_keep_grants_after_replacement(self):
        folder=self.root/'incoming';folder.mkdir();source=folder/'guide.txt';source.write_bytes(DOCUMENT)
        identity=self.app.watched.add({'path':str(folder),'restricted':True})
        def publish():
            self.app.watched.scan(identity);change=self.app.watched.catalog()['changes'][0]
            job=self.app.watched.approve(change['id'],self.owner,change['sha'])['job_id']
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                result=self.store.job(job,self.owner)
                if result['status'] in ('done','failed','canceled'):
                    self.assertEqual(result['status'],'done',result.get('error'));return result['result']['document_id']
                time.sleep(.03)
            self.fail('Indexing did not finish')
        document=publish()
        self.assertFalse(permissions.visible(self.store,self.other,[document]))
        group=self.group([self.other])
        permissions.save_document(self.app,document,{'restricted':True,'groups':[group]})
        source.write_bytes(b'Aurora warranty is now 48 months.')
        self.assertEqual(publish(),document)
        self.assertEqual(permissions.document(self.store,document),{'restricted':True,'groups':[group]})
        self.assertTrue(permissions.visible(self.store,self.other,[document]))
