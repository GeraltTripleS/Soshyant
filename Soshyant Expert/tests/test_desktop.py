"""Exercise the launcher's real hidden host in a disposable installation."""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import uuid

from expert.config import ROOT


class DesktopHostTests(unittest.TestCase):
    def test_hidden_host_starts_and_stops_without_touching_existing_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            shutil.copytree(ROOT/'expert',root/'expert',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT/'config',root/'config')
            (root/'tools').mkdir();shutil.copy2(ROOT/'tools/desktop_host.py',root/'tools/desktop_host.py')
            shutil.copy2(ROOT/'start.py',root/'start.py')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            settings=json.loads((root/'config/server.json').read_text(encoding='utf-8'))
            settings['port']=port;settings['embedding_mode']='lexical';settings.pop('cloud_model_id',None)
            (root/'config/server.json').write_text(json.dumps(settings),encoding='utf-8')
            stop=root/'data'/('launcher-stop-'+uuid.uuid4().hex)
            process=subprocess.Popen([sys.executable,str(root/'tools/desktop_host.py'),'--desktop-stop-file',str(stop)],cwd=root)
            try:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                deadline=time.monotonic()+20
                while True:
                    try:
                        with opener.open('http://127.0.0.1:'+str(port)+'/healthz',timeout=1) as response:
                            self.assertEqual(json.load(response)['status'],'ok')
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic()>deadline:
                            self.fail((root/'data/desktop-server.log').read_text(encoding='utf-8'))
                        time.sleep(.2)
                stop.write_text('')
                self.assertEqual(process.wait(timeout=15),0)
                self.assertFalse(stop.exists())
                self.assertTrue((root/'data/desktop-server.log').exists())
            finally:
                if process.poll() is None:
                    stop.parent.mkdir(exist_ok=True);stop.write_text('')
                    process.wait(timeout=20)
