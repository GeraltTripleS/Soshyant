import argparse
import json
from pathlib import Path
import sys

from expert import backup
from expert.config import Config, ROOT
from expert.storage import Store, instance_lock


def check(full=False):
    config = Config()
    required = ["runtime/python.exe", "assets/model.gguf", "assets/llama/llama-server.exe",
                "assets/embeddings/model_optimized.onnx", "assets/embeddings/tokenizer.json"]
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError("Missing local files: " + ", ".join(missing))
    import numpy
    import onnxruntime
    import tokenizers
    import pypdf
    import openpyxl
    from expert.knowledge import LocalEmbeddings
    vector = LocalEmbeddings(config.settings).encode(["A local document search check."])[0]
    print(f"Independent runtime: {sys.prefix}")
    print(f"Local embedding model: OK ({len(vector)} dimensions)")
    if full:
        manifest = json.loads((ROOT / "assets-manifest.json").read_text(encoding="utf-8"))
        for name, expected in manifest.items():
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file() or backup.checksum(path) != expected["sha256"]:
                raise RuntimeError("Asset checksum mismatch: " + name)
        print("Asset checksums: OK")
    print("Local installation checks passed. Fresh-machine, network-isolation and expert-domain acceptance are separate tests.")


def main():
    parser = argparse.ArgumentParser(description="Local administration and offline maintenance")
    sub = parser.add_subparsers(dest="action", required=True)
    checker = sub.add_parser("check")
    checker.add_argument("--full", action="store_true")
    sub.add_parser("backup")
    restorer = sub.add_parser("restore")
    restorer.add_argument("file", type=Path)
    args = parser.parse_args()
    config = Config()
    if args.action == "check":
        check(args.full)
    elif args.action == "backup":
        print("Backup saved:", backup.create(Store(config.data), config))
    elif args.action == "restore":
        with instance_lock(config.data):
            backup.restore(args.file, config)
        print("Restore completed. Existing sessions were revoked. Sign in again.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc)
        sys.exit(1)
