import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import threading
import unittest

from expert.model_library import ModelLibrary
from expert.config import Config, ROOT


class ModelLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        (self.root/'config').mkdir()
        (self.root/'config/server.json').write_bytes((ROOT/'config/server.json').read_bytes())
        self.config=Config(self.root)
        class Model:
            state='stopped'
            fail=False
            def close(inner):inner.state='stopped'
            def ensure(inner):
                if inner.fail: raise RuntimeError('incompatible model')
                inner.state='ready'
        self.model=Model()
        self.engine=SimpleNamespace(model=self.model,model_changing=False,inflight=set(),inflight_lock=threading.Lock())
        self.library=ModelLibrary(self.config,self.engine)
        self.first=self.library.directory/'first.gguf'
        self.second=self.library.directory/'second.gguf'
        for path in (self.first,self.second):path.write_bytes(b'GGUF'+struct.pack('<IQQ',3,1,0)+b'test-only-model')

    def test_scan_register_and_reject_invalid_models(self):
        self.assertEqual(len(self.library.catalog()['models']),3)
        external=self.root/'external.gguf';external.write_bytes(self.first.read_bytes())
        self.library.register(str(external));self.library.register(str(external))
        self.assertEqual(len(self.library.registered()),1)
        invalid=self.root/'broken.gguf';invalid.write_bytes(b'not-a-model')
        for value in (str(invalid),'missing.gguf','config/server.json','\\\\server\\share\\model.gguf'):
            with self.subTest(value=value),self.assertRaises(ValueError):self.library.register(value)

    def test_successful_activation_persists_and_next_start_uses_it(self):
        self.library.activate(self.library.identify(self.first))
        self.assertEqual(self.model.state,'ready')
        self.assertFalse(self.engine.model_changing)
        self.assertEqual(Config(self.root).settings['model_file'],str(self.first))

    def test_model_can_stay_outside_application_in_any_local_folder(self):
        with tempfile.TemporaryDirectory() as external_folder:
            path=Path(external_folder)/'my external model.gguf'
            path.write_bytes(self.first.read_bytes())
            self.library.register(str(path))
            self.library.activate(self.library.identify(path))
            self.assertEqual(Config(self.root).settings['model_file'],str(path))
            self.assertTrue(path.is_file())
            self.assertFalse((self.library.directory/path.name).exists())

    def test_switching_from_cloud_to_local_restores_offline_selection(self):
        profile=self.library.clouds.add({'name':'Test API','provider':'openai','model':'test-model','api_key':'test-only-not-real-key'})
        with self.assertRaises(ValueError):self.library.activate(profile['id'])
        self.library.activate(profile['id'],True)
        self.assertEqual(self.config.settings['cloud_model_id'],profile['id'])
        self.library.activate(self.library.identify(self.first))
        self.assertFalse(self.config.settings.get('cloud_model_id'))
        self.assertFalse(Config(self.root).settings.get('cloud_model_id'))
        self.assertEqual(self.library.active_info()['kind'],'local')

    def test_failed_activation_retains_previous_selection(self):
        self.library.activate(self.library.identify(self.first))
        before=(self.root/'config/server.json').read_bytes()
        self.model.fail=True
        with self.assertRaises(ValueError):self.library.activate(self.library.identify(self.second))
        self.assertEqual(self.config.settings['model_file'],str(self.first))
        self.assertEqual((self.root/'config/server.json').read_bytes(),before)
        self.assertFalse(self.engine.model_changing)

    def test_busy_answers_block_switching(self):
        self.engine.inflight.add('a-pending-conversation')
        with self.assertRaises(ValueError):self.library.activate(self.library.identify(self.first))
        self.assertFalse(self.engine.model_changing)

    def test_scan_folder_recursion_validation_and_persistence(self):
        nested=self.library.directory/'nested';nested.mkdir()
        child=nested/'third.gguf';child.write_bytes(self.first.read_bytes())
        (nested/'broken.gguf').write_bytes(b'not a real model')
        flat=self.library.scan_folder('"'+str(self.library.directory)+'"',False)
        self.assertEqual(flat['scan']['found'],2)
        result=self.library.scan_folder(str(self.library.directory),True)
        self.assertEqual(result['scan']['found'],3)
        self.assertEqual(result['scan']['invalid'],1)
        reloaded=ModelLibrary(self.config,self.engine)
        self.assertEqual(reloaded.folder()['path'],str(self.library.directory))
        self.assertIn(str(child),reloaded.folder()['files'])
        self.assertTrue(any(row['path']==str(child) for row in reloaded.catalog()['models']))
        self.assertFalse(any(row['name']=='broken.gguf' for row in reloaded.catalog()['models']))

    def test_folder_browser_and_empty_folder(self):
        outside=self.root/'outside';outside.mkdir()
        nested=outside/'nested';nested.mkdir()
        listing=self.library.folders(str(outside))
        self.assertEqual(listing['path'],str(outside))
        self.assertEqual(listing['directories'],[{'name':'nested','path':str(nested)}])
        self.assertTrue(listing['roots'])
        result=self.library.scan_folder(str(outside))
        self.assertEqual(result['scan']['found'],0)
        for value in (str(self.first),str(outside/'missing'),'\\\\server\\share'):
            with self.subTest(value=value),self.assertRaises(ValueError):self.library.scan_folder(value)
