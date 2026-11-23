import numpy as np
from test_engine import Fixture, DOCUMENT
from expert import permissions


class RetrievalTests(Fixture):
    def test_warm_corpus_reuses_tokens_and_invalidates_on_new_knowledge(self):
        self.index()
        first, version = self.engine.knowledge.search('warranty', owner=self.owner)
        cache = next(iter(self.engine.knowledge.retrieval_cache.values()))
        again, _ = self.engine.knowledge.search('warranty', owner=self.owner)
        self.assertEqual(first, again)
        self.assertIs(cache, next(iter(self.engine.knowledge.retrieval_cache.values())))
        self.index(b'The Aurora X300 warranty is 48 months from installation.', 'new.txt')
        result, updated = self.engine.knowledge.search('X300 warranty', owner=self.owner)
        self.assertNotEqual(version, updated)
        self.assertEqual(result[0]['filename'], 'new.txt')

    def test_cache_scopes_and_active_users_never_share_private_passages(self):
        identity = self.index()
        self.engine.knowledge.search('warranty', owner=self.other)
        with self.store.connect() as db:
            db.execute('INSERT INTO document_access VALUES(?,1)', (identity,))
            permissions.changed(self.store, db)
        self.assertEqual(self.engine.knowledge.search('warranty', owner=self.other)[0], [])
        self.assertTrue(self.engine.knowledge.search('warranty', owner=self.owner)[0])
        self.store.execute('UPDATE users SET active=0 WHERE id=?', (self.owner,))
        self.assertEqual(self.engine.knowledge.search('warranty', owner=self.owner)[0], [])

    def test_duplicates_do_not_consume_evidence_slots(self):
        self.index()
        self.index(DOCUMENT, 'duplicate.txt')
        self.index(b'Warranty claims must include a signed inspection certificate.', 'claims.txt')
        result, _ = self.engine.knowledge.search('warranty claims', owner=self.owner)
        self.assertEqual(len(result), 2)
        self.assertEqual(self.engine.knowledge.search('warranty', limit=0)[0], [])

    def test_vectorized_search_and_bounded_query_embedding_cache(self):
        identity = self.index()
        knowledge = self.engine.knowledge
        self.config.settings['embedding_mode'] = 'hybrid'
        self.store.execute('UPDATE chunks SET vector=? WHERE document_id=?',
                           (np.array([1., 0.], dtype=np.float32).tobytes(), identity))
        calls = []
        def encode(texts):
            calls.append(texts); return [np.array([1., 0.], dtype=np.float32)]
        knowledge.embeddings.encode = encode
        self.assertTrue(knowledge.search('unrelated paraphrase', owner=self.owner)[0])
        knowledge.search('unrelated paraphrase', owner=self.owner)
        self.assertEqual(len(calls), 1)
        for i in range(35): knowledge.search('paraphrase ' + str(i), owner=self.owner)
        self.assertLessEqual(len(knowledge.query_cache), 32)
        self.assertNotIn('vector', knowledge.search('warranty', owner=self.owner)[0][0])
