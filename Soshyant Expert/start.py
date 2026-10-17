"""Run with runtime/python.exe; no installation or network is required."""
import os
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
