"""Real runtime activation/rollback check in disposable configuration and data."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from expert.config import Config
from expert.model import LocalModel
from expert.model_library import ModelLibrary


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);(root/'config').mkdir()
        settings=json.loads((ROOT/'config/server.json').read_text(encoding='utf-8'))
        for key in ('model_file','llama_executable','embedding_directory'):
            settings[key]=str((ROOT/settings[key]).resolve())
        settings['model_port']=18198
        (root/'config/server.json').write_text(json.dumps(settings),encoding='utf-8')
        config=Config(root);model=LocalModel(config)
        engine=SimpleNamespace(model=model,model_changing=False,inflight=set(),inflight_lock=threading.Lock())
        library=ModelLibrary(config,engine)
        previous=config.settings['model_file']
        try:
            library.activate(library.identify(Path(previous)))
            assert model.state=='ready'
            assert Config(root).settings['model_file']==previous
            print('Real bundled model activation and persistence: PASS',flush=True)
            broken=library.directory/'deliberately-incomplete-test-model.gguf'
            broken.write_bytes(b'GGUF'+struct.pack('<IQQ',3,1,0)+b'test-only-invalid-tensors')
            try:library.activate(library.identify(broken))
            except ValueError:pass
            else:raise AssertionError('Invalid model was accepted by runtime')
            assert config.settings['model_file']==previous
            assert Config(root).settings['model_file']==previous
            model.ensure()
            assert model.state=='ready'
            print('Failed activation rollback and previous-model reload: PASS',flush=True)
        finally:model.close()


if __name__=='__main__':main()
