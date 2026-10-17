"""Hidden launcher-owned server, with bounded diagnostic logs."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
data = ROOT / 'data'
data.mkdir(exist_ok=True)
log = data / 'desktop-server.log'
if log.exists() and log.stat().st_size > 2 * 1024 * 1024:
    log.replace(data / 'desktop-server.previous.log')
with log.open('a', encoding='utf-8', buffering=1) as stream:
    sys.stdout = sys.stderr = stream
    try:
        runpy.run_path(str(ROOT / 'start.py'), run_name='__main__')
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(1)
