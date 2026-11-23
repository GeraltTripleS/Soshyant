import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from expert.config import ROOT
from expert.process_owner import ProcessOwner


@unittest.skipUnless(os.name == 'nt', 'Windows process ownership')
class ProcessOwnerTests(unittest.TestCase):
    def test_closing_job_kills_only_its_attached_child(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        owner = ProcessOwner()
        try:
            owner.attach(child)
            owner.close()
            child.wait(timeout=5)
            self.assertIsNone(unrelated.poll())
            owner.close()  # idempotent
        finally:
            owner.close()
            for process in (child, unrelated):
                if process.poll() is None: process.kill()
                process.wait(timeout=5)

    def test_abrupt_parent_exit_releases_child_port(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'ready.txt'
            script = '''
import os,subprocess,sys,time
from pathlib import Path
from expert.process_owner import ProcessOwner
owner=ProcessOwner()
child=subprocess.Popen([sys.executable,'-c',"import socket,sys,time; from pathlib import Path; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); Path(sys.argv[1]).write_text(str(s.getsockname()[1])); time.sleep(60)",sys.argv[1]])
owner.attach(child)
while not Path(sys.argv[1]).exists(): time.sleep(.01)
os._exit(0)
'''
            parent = subprocess.Popen([sys.executable, '-c', script, str(marker)], cwd=ROOT)
            try:
                self.assertEqual(parent.wait(timeout=10), 0)
                port = int(marker.read_text())
                import socket
                deadline = time.monotonic()+5
                while time.monotonic()<deadline:
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1',port)) != 0: break
                    time.sleep(.05)
                else: self.fail('Owned child kept its port after parent exit')
            finally:
                if parent.poll() is None: parent.kill(); parent.wait(timeout=5)
