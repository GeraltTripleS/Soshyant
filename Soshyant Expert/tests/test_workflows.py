import time
import threading
from unittest.mock import patch

from test_engine import Fixture, DOCUMENT
from expert.server import Application
from expert import review


class WorkflowTests(Fixture):
    def setUp(self):
        super().setUp()
        self.app=Application(self.config,self.store,self.model)
        self.addCleanup(self.app.close)
        self.folder=self.root/'incoming';self.folder.mkdir()
        self.file=self.folder/'guide.txt';self.file.write_bytes(DOCUMENT)
        self.watch=self.app.watched

    def discover(self):
        identity=self.watch.add({'path':str(self.folder),'recursive':True})
        self.watch.scan(identity)
        return identity,self.watch.catalog()['changes'][0]

    def finish(self, change):
        result=self.watch.approve(change['id'],self.owner,change['sha'])
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            job=self.store.job(result['job_id'],self.owner)
            if job['status'] in ('done','failed','canceled'):
                return job
            time.sleep(.03)
        self.fail('Watch job did not finish')

    def test_scan_only_proposes_and_approved_versions_publish_atomically(self):
        folder,change=self.discover()
        self.assertEqual(change['kind'],'new')
        self.assertEqual(self.store.rows('SELECT id FROM documents'),[])
        self.assertEqual(self.finish(change)['status'],'done')
        doc=self.store.one('SELECT * FROM documents WHERE active=1')
        self.assertEqual(doc['version'],1)
        self.assertFalse(self.watch.catalog()['changes'])
        self.config.settings['max_chunks']=self.store.one('SELECT count(*) AS n FROM chunks')['n']
        self.file.write_bytes(b'Aurora X200 warranty is 48 months from installation.')
        self.watch.scan(folder);change=self.watch.catalog()['changes'][0]
        self.assertEqual(change['kind'],'changed')
        self.assertEqual(self.store.one('SELECT version FROM documents WHERE id=?',(doc['id'],))['version'],1)
        self.assertEqual(self.finish(change)['status'],'done')
        current=self.store.one('SELECT * FROM documents WHERE id=?',(doc['id'],))
        self.assertEqual(current['version'],2)
        self.assertIn(b'48 months',current['content'])
        self.assertEqual(self.store.one('SELECT content FROM document_revisions WHERE document_id=? AND version=1',(doc['id'],))['content'],DOCUMENT)
        self.assertEqual(len(self.store.rows('SELECT id FROM documents')),1)

    def test_failed_replacement_preserves_published_document_and_search(self):
        folder,change=self.discover();self.assertEqual(self.finish(change)['status'],'done')
        doc=self.store.one('SELECT * FROM documents WHERE active=1')
        self.file.write_bytes(b'   \n  ');self.watch.scan(folder)
        self.assertEqual(self.finish(self.watch.catalog()['changes'][0])['status'],'failed')
        current=self.store.one('SELECT * FROM documents WHERE id=?',(doc['id'],))
        self.assertEqual((current['version'],current['status'],current['content']),(1,'indexed',DOCUMENT))
        self.assertTrue(self.app.engine.knowledge.search('warranty')[0])
        self.assertFalse(self.store.rows('SELECT id FROM documents WHERE active=0'))

    def test_stale_approval_and_traversal_and_data_folders_rejected(self):
        folder,change=self.discover();self.file.write_bytes(b'Changed after scan')
        with self.assertRaises(ValueError):self.watch.approve(change['id'],self.owner,change['sha'])
        with self.assertRaises(ValueError):self.watch.add({'path':str(self.config.data)})
        with self.assertRaises(ValueError):self.watch.add({'path':str(self.root)})
        with self.assertRaises(ValueError):self.watch.checked(self.folder,'../config/domain.json')
        self.assertFalse(self.store.rows('SELECT id FROM documents'))

    def test_missing_file_requires_explicit_archive_and_failed_scan_never_marks_missing(self):
        folder,change=self.discover();self.assertEqual(self.finish(change)['status'],'done')
        doc=self.store.one('SELECT id FROM documents WHERE active=1')['id']
        with patch.object(self.watch,'path',side_effect=ValueError('Unavailable folder')):
            with self.assertRaises(ValueError):self.watch.scan(folder)
        self.assertEqual(self.store.one('SELECT present FROM watched_files')['present'],1)
        self.file.unlink();self.watch.scan(folder)
        change=self.watch.catalog()['changes'][0];self.assertEqual(change['kind'],'missing')
        with self.assertRaises(ValueError):self.watch.approve(change['id'],self.owner,'missing')
        self.assertEqual(self.store.one('SELECT active FROM documents WHERE id=?',(doc,))['active'],1)
        self.watch.approve(change['id'],self.owner,'missing',True)
        self.assertEqual(self.store.one('SELECT active FROM documents WHERE id=?',(doc,))['active'],0)

    def test_review_filters_resolve_reopen_on_new_feedback_and_chat_cleanup(self):
        chat=self.store.new_conversation(self.other)
        result=self.app.engine.answer(self.other,chat,'No supporting documents yet')
        identity=result['message_id']
        rows=review.listing(self.store,{})['items'];self.assertEqual(rows[0]['id'],identity)
        self.assertEqual(rows[0]['question'],'No supporting documents yet')
        review.save(self.store,identity,self.owner,{'status':'resolved','note':'Added to knowledge backlog'})
        self.assertEqual(review.listing(self.store,{})['items'],[])
        self.assertEqual(review.listing(self.store,{'state':['resolved']})['items'][0]['review_note'],'Added to knowledge backlog')
        self.store.execute('INSERT INTO feedback(user_id,message_id,rating,note,created) VALUES(?,?,?,?,?)',(self.other,identity,'incorrect','Needs a better source',time.time()+.01))
        self.assertEqual(review.listing(self.store,{'kind':['incorrect']})['items'][0]['resolved'],0)
        self.app.engine.delete_conversation(chat,self.other)
        self.assertEqual(review.listing(self.store,{'state':['all']})['items'],[])
        self.assertFalse(self.store.rows('SELECT * FROM answer_reviews'))

    def test_staged_update_is_hidden_and_cancellation_preserves_old_version(self):
        folder,change=self.discover();self.assertEqual(self.finish(change)['status'],'done')
        doc=self.store.one('SELECT * FROM documents WHERE active=1')
        self.file.write_bytes(b'Aurora X200 warranty is 48 months.');self.watch.scan(folder)
        change=self.watch.catalog()['changes'][0]
        staged=threading.Event();release=threading.Event()
        original=self.app.engine.knowledge.index
        def blocked(*args,**kwargs):
            result=original(*args,**kwargs);staged.set();release.wait(5);return result
        with patch.object(self.app.engine.knowledge,'index',side_effect=blocked):
            result=self.watch.approve(change['id'],self.owner,change['sha'])
            try:
                self.assertTrue(staged.wait(5))
                self.assertEqual(self.store.one('SELECT version FROM documents WHERE id=?',(doc['id'],))['version'],1)
                listed=self.app.engine.knowledge.list_documents(True)
                self.assertEqual([row['id'] for row in listed],[doc['id']])
                self.assertIn('36 months',self.app.engine.knowledge.search('warranty')[0][0]['text'])
                self.store.job_update(result['job_id'],canceled=1)
            finally:
                release.set()
            deadline=time.monotonic()+5
            while self.store.job(result['job_id'],self.owner)['status'] not in ('failed','canceled','done') and time.monotonic()<deadline:time.sleep(.03)
        self.assertEqual(self.store.job(result['job_id'],self.owner)['status'],'canceled')
        self.assertEqual(self.store.one('SELECT content FROM documents WHERE id=?',(doc['id'],))['content'],DOCUMENT)
        self.assertEqual(len(self.store.rows('SELECT id FROM documents')),1)

    def test_unreadable_source_is_reported_and_recursive_setting_is_respected(self):
        nested=self.folder/'nested';nested.mkdir();(nested/'sub.txt').write_bytes(DOCUMENT)
        (self.folder/'empty.txt').write_bytes(b'')
        folder=self.watch.add({'path':str(self.folder),'recursive':False})
        self.watch.scan(folder)
        changes=self.watch.catalog()['changes']
        self.assertEqual({row['relative'] for row in changes},{'guide.txt','empty.txt'})
        self.assertEqual(next(row for row in changes if row['relative']=='empty.txt')['kind'],'unreadable')

    def test_review_pagination_does_not_repeat_or_omit_items(self):
        chat=self.store.new_conversation(self.other)
        import json
        with self.store.connect() as db:
            for n in range(52):
                db.execute("INSERT INTO messages(conversation_id,role,content,created) VALUES(?,'user',?,?)",(chat,str(n),time.time()))
                db.execute("INSERT INTO messages(conversation_id,role,content,result,created) VALUES(?,'assistant',?,?,?)",(chat,'Missing evidence',json.dumps({'status':'insufficient'}),time.time()))
        first=review.listing(self.store,{})
        second=review.listing(self.store,{'before':[str(first['next'])]})
        self.assertEqual(len(first['items']),50);self.assertEqual(len(second['items']),2)
        self.assertEqual(len({row['id'] for row in first['items']+second['items']}),52)
        self.assertIsNone(second['next'])
