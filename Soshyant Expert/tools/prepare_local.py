"""Build-time only: copy installed local assets into an independent folder.

Network is used only with --download-embeddings, never by the running app.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def copy_tree(source, target):
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "site-packages", "test", "tests", "idlelib"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--download-embeddings", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    runtime = ROOT / "runtime"
    print("Copying an independent Python runtime...", flush=True)
    copy_tree(Path(sys.base_prefix), runtime)
    site = runtime / "Lib/site-packages"
    site.mkdir(parents=True, exist_ok=True)
    names = ["numpy", "onnxruntime", "tokenizers", "pypdf", "openpyxl", "et_xmlfile",
             "flatbuffers", "packaging"]
    site_source = None
    for name in names:
        spec = importlib.util.find_spec(name)
        if spec is None:
            raise RuntimeError("Missing installed dependency: " + name)
        origin = Path(spec.origin)
        site_source = origin.parent.parent if spec.submodule_search_locations else origin.parent
        if spec.submodule_search_locations:
            copy_tree(origin.parent, site / name)
        else:
            shutil.copy2(origin, site / origin.name)
        for path in site_source.glob(name.replace("_", "-") + "-*.dist-info"):
            copy_tree(path, site / path.name)
        for path in site_source.glob(name + "-*.dist-info"):
            copy_tree(path, site / path.name)
        for path in site_source.glob(name + ".libs"):
            copy_tree(path, site / path.name)
    (ROOT / "assets/llama").mkdir(parents=True, exist_ok=True)
    for path in (source / "bin/cuda").iterdir():
        if path.suffix.lower() == ".dll" or path.name == "llama-server.exe":
            target = ROOT / "assets/llama" / path.name
            if not target.exists() or target.stat().st_size != path.stat().st_size:
                shutil.copy2(path, target)
    target = ROOT / "assets/model.gguf"
    model = source / "models/Ternary-Bonsai-2-27B-Abliterated-PTQ1_0.gguf"
    if not target.exists() or target.stat().st_size != model.stat().st_size:
        print("Copying the installed language model...", flush=True)
        shutil.copy2(model, target)
    if args.download_embeddings:
        repository = "Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
        opener = urllib.request.build_opener()
        with opener.open("https://huggingface.co/api/models/" + repository, timeout=60) as response:
            metadata = json.load(response)
        revision = metadata["sha"]
        names = {item["rfilename"] for item in metadata["siblings"]}
        folder = ROOT / "assets/embeddings"
        folder.mkdir(exist_ok=True)
        for name in ["model_optimized.onnx", "tokenizer.json", "config.json", "tokenizer_config.json", "special_tokens_map.json"]:
            if name not in names:
                if name in ("model_optimized.onnx", "tokenizer.json"):
                    raise RuntimeError("Required embedding asset not found: " + name)
                continue
            path = folder / name
            if path.exists():
                continue
            print("Downloading public embedding asset: " + name, flush=True)
            with opener.open(f"https://huggingface.co/{repository}/resolve/{revision}/{name}", timeout=120) as response:
                with path.with_suffix(path.suffix + ".part").open("wb") as stream:
                    shutil.copyfileobj(response, stream)
            path.with_suffix(path.suffix + ".part").replace(path)
        (folder / "provenance.json").write_text(json.dumps({"repository": repository, "revision": revision}, indent=2), encoding="utf-8")
    print("Writing asset checksums...", flush=True)
    manifest = {}
    for path in (ROOT / "assets").rglob("*"):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                    digest.update(block)
            manifest[path.relative_to(ROOT).as_posix()] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    (ROOT / "assets-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Local runtime and assets prepared.", flush=True)


if __name__ == "__main__":
    main()
