"""Real local retrieval + generation on disposable example data, never customer data."""
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from expert.config import Config
from expert.engine import Engine
from expert.storage import Store


def main():
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "config").mkdir()
        settings = json.loads((ROOT / "config/server.json").read_text())
        for key in ("model_file", "llama_executable", "embedding_directory"):
            settings[key] = str(ROOT / settings[key])
        settings["model_port"] = 18196
        (root / "config/server.json").write_text(json.dumps(settings))
        shutil.copy2(ROOT / "examples/domain-support.json", root / "config/domain.json")
        config, connections = Config(root), []
        original_connect = socket.socket.connect

        def local_only(sock, address):
            connections.append(address[0])
            if address[0] not in ("127.0.0.1", "::1"):
                raise RuntimeError("Outbound Python connection blocked by smoke test.")
            return original_connect(sock, address)

        socket.socket.connect = local_only
        engine = None
        try:
            store = Store(config.data)
            owner = store.create_user("smoke-user", "disposable-test-password", "admin")
            engine = Engine(store, config)
            original_generate = engine.model.generate
            def diagnostic_generate(*args, **kwargs):
                result = original_generate(*args, **kwargs)
                print("MODEL CONTRACT:", json.dumps(result, ensure_ascii=False), flush=True)
                return result
            engine.model.generate = diagnostic_generate
            identity = engine.knowledge.add("sample-handbook.txt", (ROOT / "examples/sample-handbook.txt").read_bytes())
            print("Building a real local semantic index...", flush=True)
            engine.knowledge.index(identity)
            conversation = store.new_conversation(owner)
            print("Loading the real language model and asking a grounded question...", flush=True)
            result = engine.answer(owner, conversation, "How long is the Aurora X200 warranty, and what is needed for a claim?")
            assert result["status"] == "answered", result
            assert result["citations"], result
            assert "36" in result["answer"], result
            print("REAL ANSWER:", result["answer"], flush=True)
            print("CITED FILE:", result["citations"][0]["filename"], flush=True)
            print("Testing a Persian follow-up...", flush=True)
            persian = engine.answer(owner, conversation, "برای استفاده از گارانتی آن چه مدارکی لازم است؟")
            print("PERSIAN STATUS:", persian["status"], flush=True)
            print("PERSIAN ANSWER:", persian["answer"], flush=True)
            print("Testing explicit English selection for a Persian question...", flush=True)
            english_override = engine.answer(owner, conversation, "مدت گارانتی Aurora X200 چقدر است؟", response_language="en")
            assert english_override["response_language"] == "English", english_override
            assert english_override["status"] == "answered", english_override
            assert "36" in english_override["answer"], english_override
            assert not any("\u0600" <= char <= "\u06ff" for char in english_override["answer"]), english_override
            print("ENGLISH OVERRIDE:", english_override["answer"], flush=True)
            report = {"real_english_grounded_answer": True, "english_language_override_verified": True, "persian_status": persian["status"],
                      "persian_answer": persian["answer"], "citations": len(result["citations"]),
                      "python_connections_loopback_only": all(host in ("127.0.0.1", "::1") for host in connections),
                      "elapsed_seconds": round(time.monotonic() - started, 1),
                      "limitations": "This guards Python socket connections only; clean-machine and OS-level egress isolation are not certified."}
            (ROOT / "VALIDATION-real.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Real local smoke test passed.", flush=True)
        finally:
            if engine:
                engine.close()
            socket.socket.connect = original_connect


if __name__ == "__main__":
    main()
