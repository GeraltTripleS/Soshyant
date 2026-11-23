"""Run with runtime/python.exe; no installation or network is required."""
import os
from pathlib import Path
import sys
import subprocess

# File associations and `python start.py` can select an unrelated system Python.
# Delegate before importing application dependencies; never install into that Python.
_root = Path(__file__).resolve().parent
_bundled = _root / 'runtime' / ('pythonw.exe' if Path(sys.executable).name.lower() == 'pythonw.exe' else 'python.exe')
if _bundled.is_file() and Path(sys.executable).resolve() != _bundled.resolve():
    # subprocess handles Windows command-line quoting, including spaces in the path.
    try:
        raise SystemExit(subprocess.call([str(_bundled), str(_root / 'start.py'), *sys.argv[1:]]))
    except KeyboardInterrupt:
        raise SystemExit(130)

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"

from expert.server import main

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print("Soshyant Expert could not start:", exc)
        raise SystemExit(1)
