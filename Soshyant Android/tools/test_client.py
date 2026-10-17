"""Run the APK's Java API client against an isolated real HTTPS gateway."""
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request

ROOT=Path(__file__).resolve().parents[1];SERVER=ROOT.parent/'Soshyant Expert'
sys.path.insert(0,str(SERVER))
from expert.config import Config
from expert.server import Application,Handler,ThreadingHTTPServer
from expert.storage import Store
from expert.mobile_gateway import create_gateway
from tools.prepare_mobile_tls import prepare


class Model:
    state='ready'
    def available(self):return True
    def close(self):pass
    def generate(self,messages,canceled=lambda:False):return {'status':'answered','answer':'The warranty is 36 months. [1]','citations':[1]}


def main():
    tools=ROOT/'.tools';tools.mkdir(exist_ok=True)
    jar=tools/'json-20250517.jar'
    base='https://repo.maven.apache.org/maven2/org/json/json/20250517/json-20250517.jar'
    if not jar.exists():
        with urllib.request.urlopen(base,timeout=30) as response:jar.write_bytes(response.read())
    expected=urllib.request.urlopen(base+'.sha1',timeout=30).read().decode().strip()
    assert hashlib.sha1(jar.read_bytes()).hexdigest()==expected,'Test dependency checksum mismatch'
    classes=ROOT/'build/client-tests';classes.mkdir(parents=True,exist_ok=True)
    subprocess.run(['javac','--release','8','-encoding','UTF-8','-cp',str(jar),'-d',str(classes),
                    str(ROOT/'app/src/main/java/com/soshyant/expert/ApiClient.java'),str(ROOT/'tests/ClientContractTest.java')],check=True)
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary);(root/'config').mkdir()
        settings=json.loads((SERVER/'config/server.json').read_text(encoding='utf-8'));settings.pop('cloud_model_id',None);settings['embedding_mode']='lexical'
        (root/'config/server.json').write_text(json.dumps(settings),encoding='utf-8')
        for name in ('domain.json','capacity-models.json'):shutil.copy2(SERVER/'config'/name,root/'config'/name)
        config=Config(root);store=Store(config.data);store.create_user('phone-user','phone-test-password')
        app=Application(config,store,Model())
        identity=app.engine.knowledge.add('warranty.txt',b'The warranty is 36 months from installation.');app.engine.knowledge.index(identity)
        backend=ThreadingHTTPServer(('127.0.0.1',0),Handler);backend.app=app
        tls=prepare('127.0.0.1',root/'tls')
        gateway=create_gateway('127.0.0.1',0,tls['certificate'],tls['private_key'],'http://127.0.0.1:'+str(backend.server_port))
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (backend,gateway)]
        for thread in threads:thread.start()
        try:
            subprocess.run(['java','-cp',str(classes)+';'+str(jar),'ClientContractTest',
                            'https://127.0.0.1:'+str(gateway.server_port),tls['ca_file']],check=True)
            context=ssl.create_default_context(cafile=tls['ca_file'])
            for headers in ({'Host':'wrong.example'},{'Origin':'https://wrong.example'}):
                connection=http.client.HTTPSConnection('127.0.0.1',gateway.server_port,context=context)
                connection.request('GET','/healthz',headers=headers);response=connection.getresponse()
                assert response.status==403;response.read();connection.close()
            print('PASS: gateway Host/Origin restrictions; temporary test data only.',flush=True)
        finally:
            for server in (gateway,backend):server.shutdown();server.server_close()
            app.close()


if __name__=='__main__':main()
