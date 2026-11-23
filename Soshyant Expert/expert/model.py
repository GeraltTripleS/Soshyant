"""Local inference by default; explicit saved cloud selection uses its API."""
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from .cloud import CloudClient
from .process_owner import ProcessOwner


class LocalModel:
    def __init__(self, config):
        self.config = config
        self.settings = config.settings
        self.url = f"http://127.0.0.1:{self.settings['model_port']}"
        self.process = None
        self.lock = threading.Lock()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.log = None
        self.state = "stopped"
        self.cloud = CloudClient(config)
        self.process_owner = None

    def available(self):
        if self.settings.get('cloud_model_id'):
            try:self.cloud.profiles.get(self.settings['cloud_model_id']);return True
            except ValueError:return False
        return all(Path(self.settings[key]).is_file() for key in ("model_file", "llama_executable"))

    def ensure(self, canceled=lambda: False):
        if self.settings.get('cloud_model_id'):
            self.state='loading'
            self.cloud.probe(self.settings['cloud_model_id'])
            self.state='ready'
            return
        with self.lock:
            if self.process is not None and self.process.poll() is None and self.state == "ready":
                return
            if not self.available():
                raise RuntimeError("The local language-model runtime is missing. Prepare offline assets first.")
            # A foreign process is never adopted or terminated.
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", self.settings["model_port"])) == 0:
                    raise RuntimeError("The configured model port is occupied. Select a different model port.")
            self.log = (self.config.data / "model-runtime.log").open("ab")
            command = [self.settings["llama_executable"], "--host", "127.0.0.1", "--port",
                       str(self.settings["model_port"]), "-m", self.settings["model_file"],
                       "-ngl", str(self.settings["gpu_layers"]), "-c", str(self.settings["context_size"]),
                       "--parallel", "1", "--jinja", "--chat-template-kwargs", '{"enable_thinking":false}']
            self.state = "loading"
            try:
                self.process_owner = ProcessOwner()
                self.process = subprocess.Popen(command, stdout=self.log, stderr=self.log,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
                self.process_owner.attach(self.process)
            except Exception:
                self.close()
                raise RuntimeError('The local model could not start with automatic process cleanup. Check the runtime and Windows permissions.') from None
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if canceled():
                    self.close()
                    raise InterruptedError("Answer canceled.")
                if self.process.poll() is not None:
                    self.state = "failed"
                    raise RuntimeError("The local model failed to start. Check the local runtime log and GPU settings.")
                try:
                    with self.opener.open(self.url + "/health", timeout=2) as response:
                        if response.status == 200:
                            self.state = "ready"
                            return
                except (urllib.error.URLError, OSError):
                    pass
                time.sleep(.5)
            self.close()
            raise RuntimeError("The local model did not become ready within three minutes.")

    def generate(self, messages, canceled=lambda: False):
        if self.settings.get('cloud_model_id'):
            try:result=self.cloud.generate(self.settings['cloud_model_id'],messages,canceled)
            except Exception:
                self.state='failed'
                raise
            self.state='ready'
            return result
        self.ensure(canceled)
        schema = {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["answered", "clarify", "insufficient"]},
            "answer": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "integer"}}},
            "required": ["status", "answer", "citations"], "additionalProperties": False}
        payload = {"messages": messages, "stream": True, "max_tokens": self.settings["max_answer_tokens"],
                   "temperature": 0, "seed": 42, "chat_template_kwargs": {"enable_thinking": False},
                   "response_format": {"type": "json_schema", "json_schema": {"name": "grounded_answer", "strict": True, "schema": schema}}}
        request = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        pieces, finished = [], False
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=120) as response:
                for line in response:
                    if canceled():
                        raise InterruptedError("Answer canceled.")
                    if time.monotonic() - started > 180:
                        raise RuntimeError("Answer time limit reached. Try a shorter question.")
                    if not line.startswith(b"data: "):
                        continue
                    data = line[6:].strip()
                    if data == b"[DONE]":
                        finished = True
                        break
                    event = json.loads(data)
                    delta = event["choices"][0].get("delta", {})
                    if delta.get("content"):
                        pieces.append(delta["content"])
        except (urllib.error.URLError, OSError) as exc:
            if isinstance(exc, InterruptedError):
                raise
            raise RuntimeError("The local model connection failed. Retry or check the runtime log.") from exc
        if not finished:
            raise RuntimeError("The model answer was interrupted; no partial answer was saved.")
        raw = "".join(pieces).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("The model returned an invalid structured answer. Please retry.") from exc

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        if self.process_owner is not None:
            self.process_owner.close()
            self.process_owner = None
        self.state = "stopped"
        if self.log is not None:
            self.log.close()
            self.log = None
