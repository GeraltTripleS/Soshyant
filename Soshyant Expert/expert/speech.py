"""Short English dictation. Jobs/audio/transcripts are ephemeral, never stored in SQLite."""
import base64
import io
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid
import wave

MAX_SECONDS = 30
MAX_BYTES = MAX_SECONDS * 16000 * 2 + 4096


def validate_audio(body):
    try:
        with wave.open(io.BytesIO(body), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise ValueError('Use mono 16 kHz PCM16 WAV audio.')
            frames = source.getnframes()
            if not 1600 <= frames <= 16000 * MAX_SECONDS:
                raise ValueError('Record between 0.1 and 30 seconds.')
            pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError('The recording is incomplete.')
            return pcm
    except (wave.Error, EOFError) as exc:
        raise ValueError('The recording must be a valid PCM WAV file.') from exc


class Speech:
    def __init__(self, config, transcriber=None):
        self.config = config
        self.runtime_root = config.root
        self.transcriber = transcriber
        self.lock = threading.RLock()
        self.jobs = {}
        self.queue = queue.Queue(2)
        self.stop = threading.Event()
        self.process = None
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    def installed(self):
        root = self.runtime_root
        return self.transcriber is not None or all((root / path).is_file() for path in (
            'speech-runtime/python.exe', 'assets/speech/model.bark', 'assets/speech/bark_loader.py',
            'assets/speech/processor/processor_config.json', 'assets/speech/processor/tokenizer.json',
            'assets/speech/processor/generation_config.json', 'assets/speech/READY.json'))

    def status(self):
        return {'enabled': self.config.settings['speech_enabled'], 'installed': self.installed(),
                'device': self.config.settings['speech_device'], 'language': 'en', 'max_seconds': MAX_SECONDS}

    def settings(self, data):
        if type(data.get('enabled')) is not bool or data.get('device') not in ('cpu', 'cuda'):
            raise ValueError('Choose whether speech is enabled and select CPU or CUDA.')
        if data['enabled'] and not self.installed():
            raise ValueError('Run SETUP-SPEECH.bat on this server first.')
        with self.lock:
            if any(job['status'] in ('queued', 'running') for job in self.jobs.values()):
                raise ValueError('Wait for dictation to finish before changing speech settings.')
            self.config.save_setting('speech_device', data['device'])
            self.config.save_setting('speech_enabled', data['enabled'])
        return self.status()

    def _expire(self):
        now = time.monotonic()
        for identity in list(self.jobs):
            if now - self.jobs[identity].get('finished', now) > 300 and self.jobs[identity]['status'] not in ('queued', 'running'):
                del self.jobs[identity]

    def submit(self, owner, body):
        if not self.config.settings['speech_enabled'] or not self.installed():
            raise ValueError('Voice input is unavailable. Ask an administrator to enable local speech input.')
        if len(body) > MAX_BYTES:
            raise ValueError('Recording exceeds the 30-second limit.')
        pcm = validate_audio(body)
        with self.lock:
            self._expire()
            if len(self.jobs) >= 100:
                raise ValueError('Speech is busy. Retry in a few minutes.')
            if any(job['owner'] == owner and job['status'] in ('queued', 'running') for job in self.jobs.values()):
                raise ValueError('Your previous recording is still being transcribed.')
            identity = uuid.uuid4().hex
            self.jobs[identity] = {'owner': owner, 'created': time.monotonic(), 'status': 'queued', 'cancel': threading.Event()}
            try:
                self.queue.put_nowait((identity, pcm))
            except queue.Full:
                del self.jobs[identity]
                raise ValueError('Speech queue is full. Retry shortly.') from None
            return identity

    def get(self, identity, owner, consume=False):
        with self.lock:
            self._expire()
            job = self.jobs.get(identity)
            if not job or job['owner'] != owner:
                raise PermissionError('Recording not found or expired.')
            result = {key: job[key] for key in ('status', 'text', 'error') if key in job}
            if consume and job['status'] not in ('queued', 'running'):
                del self.jobs[identity]
            return result

    def cancel(self, identity, owner):
        with self.lock:
            self.get(identity, owner)
            job = self.jobs[identity]
            job['cancel'].set()
            job.pop('text', None)
            job['status'] = 'canceled'
            job['finished'] = time.monotonic()
            if self.process and getattr(self.process, 'speech_id', None) == identity:
                self.process.terminate()

    def _transcribe(self, identity, pcm, canceled):
        command = [str(self.runtime_root / 'speech-runtime/python.exe'), '-I',
                   str(Path(__file__).with_name('speech_worker.py')), str(self.runtime_root / 'assets/speech'),
                   self.config.settings['speech_device']]
        with self.lock:
            if canceled():
                raise InterruptedError()
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            process.speech_id = identity
            self.process = process
        try:
            output, _ = process.communicate(base64.b64encode(pcm), timeout=180)
            if canceled():
                raise InterruptedError()
            if process.returncode:
                raise RuntimeError('Local transcription failed. Check the speech installation and selected device.')
            result = json.loads(output)
            text = result.get('text')
            if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                raise RuntimeError('No usable speech was recognized. Try a shorter, clearer recording.')
            return text.strip()
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError('Transcription timed out. Try a shorter recording.') from None
        finally:
            with self.lock:
                self.process = None

    def _work(self):
        while not self.stop.is_set():
            try:
                identity, pcm = self.queue.get(timeout=.5)
            except queue.Empty:
                with self.lock:
                    self._expire()
                continue
            try:
                with self.lock:
                    job = self.jobs.get(identity)
                    if not job:
                        continue
                    canceled = job['cancel'].is_set
                    if canceled():
                        continue
                    job['status'] = 'running'
                text = self.transcriber(pcm, canceled) if self.transcriber else self._transcribe(identity, pcm, canceled)
                with self.lock:
                    if not canceled():
                        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                            raise RuntimeError('No usable speech was recognized. Try a shorter, clearer recording.')
                        job.update(status='completed', text=text.strip(), finished=time.monotonic())
            except Exception:
                with self.lock:
                    if not canceled():
                        job.update(status='failed', finished=time.monotonic(), error='Local transcription failed. Try a shorter recording and check speech settings.')
            finally:
                pcm = None
                self.queue.task_done()

    def close(self):
        self.stop.set()
        with self.lock:
            for job in self.jobs.values():
                job['cancel'].set()
            if self.process:
                self.process.terminate()
        self.worker.join(timeout=5)
        with self.lock:
            self.jobs.clear()
