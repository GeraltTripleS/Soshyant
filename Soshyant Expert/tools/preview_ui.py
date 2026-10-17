"""Disposable UI test workspace. Does not touch the real installation's data."""
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from expert.config import Config
from expert.server import Application, Handler, ThreadingHTTPServer
from expert.storage import Store


class PreviewModel:
    state = "ready"

    def available(self):
        return True

    def generate(self, messages, canceled=lambda: False):
        if "REQUIRED RESPONSE LANGUAGE: English" in messages[0]["content"]:
            return {"status": "answered", "answer": "The sample handbook gives a warranty of 36 months from installation. [1]", "citations": [1]}
        return {"status": "answered", "answer": "طبق راهنمای نمونه، مدت گارانتی ۳۶ ماه از تاریخ نصب است. [1]\nبرای درخواست گارانتی، گزارش نصب و شماره سریال دستگاه لازم است. [1]", "citations": [1]}

    def close(self):
        pass


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "config").mkdir()
        shutil.copy2(ROOT / "config/capacity-models.json", root / "config/capacity-models.json")
        settings = json.loads((ROOT / "config/server.json").read_text())
        for key in ("model_file", "llama_executable", "embedding_directory"):
            settings[key] = str(ROOT / settings[key])
        (root / "config/server.json").write_text(json.dumps(settings))
        domain = json.loads((ROOT / "examples/domain-support.json").read_text())
        domain["name"] = "نمایش آزمایشی · اسناد ساختگی"
        (root / "config/domain.json").write_text(json.dumps(domain, ensure_ascii=False), encoding="utf-8")
        shutil.copytree(ROOT / "web", root / "web")
        config = Config(root)
        store = Store(config.data)
        owner = store.create_user("preview-admin", "preview-only-password", "admin")
        app = Application(config, store, PreviewModel())
        chat = store.new_conversation(owner)
        app.engine.answer(owner, chat, 'What information is missing from the current knowledge?')
        incoming = root / 'incoming'
        incoming.mkdir()
        (incoming / 'watch-example.txt').write_text('The new maintenance interval is six months.', encoding='utf-8')
        watched = app.watched.add({'path': str(incoming), 'recursive': True})
        app.watched.scan(watched)
        identity = app.engine.knowledge.add("sample-handbook.txt", (ROOT / "examples/sample-handbook.txt").read_bytes())
        app.engine.knowledge.index(identity)
        server = ThreadingHTTPServer(("127.0.0.1", 8097), Handler)
        server.app = app
        print("Disposable UI preview ready on port 8097", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            app.close()


if __name__ == "__main__":
    main()
