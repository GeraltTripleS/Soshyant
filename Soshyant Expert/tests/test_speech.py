import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import wave

import test_engine
from test_engine import Fixture
from expert.speech import Speech, validate_audio, MAX_BYTES


def audio(seconds=.25, rate=16000, channels=1):
    out = io.BytesIO()
    with wave.open(out, 'wb') as destination:
        destination.setnchannels(channels)
        destination.setsampwidth(2)
        destination.setframerate(rate)
        destination.writeframes(b'\x01\x01' * int(seconds * rate) * channels)
    return out.getvalue()


class SpeechTests(Fixture):
    def service(self, transcriber=lambda pcm, cancel: 'What is the warranty?'):
        service = Speech(self.config, transcriber)
        self.addCleanup(service.close)
        self.config.settings['speech_enabled'] = True
        return service

    def finished(self, service, identity):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = service.get(identity, self.owner)
            if result['status'] not in ('queued', 'running'):
                return result
            time.sleep(.01)
        self.fail('Speech did not finish')

    def test_wav_validation_bounds_and_truncation(self):
        self.assertEqual(len(validate_audio(audio())), 8000)
        for invalid in (b'bad', audio(rate=44100), audio(channels=2), audio(seconds=31), audio()[:-10]):
            with self.assertRaises(ValueError):
                validate_audio(invalid)

    def test_disabled_or_uninstalled_never_accepts_audio(self):
        service = self.service()
        self.config.settings['speech_enabled'] = False
        with self.assertRaises(ValueError): service.submit(self.owner, audio())
        service.transcriber = None
        with self.assertRaises(ValueError): service.settings({'enabled': True, 'device': 'cpu'})
        for data in ({'enabled':'yes','device':'cpu'}, {'enabled':False,'device':'unknown'}):
            with self.assertRaises(ValueError): service.settings(data)

    def test_transcript_scoped_consumed_and_not_saved_as_chat(self):
        service = self.service()
        identity = service.submit(self.owner, audio())
        with self.assertRaises(PermissionError): service.get(identity, self.other)
        self.assertEqual(self.finished(service, identity)['text'], 'What is the warranty?')
        self.assertEqual(self.store.rows('SELECT * FROM messages'), [])
        self.assertNotIn('pcm', service.jobs[identity])
        service.get(identity, self.owner, consume=True)
        with self.assertRaises(PermissionError): service.get(identity, self.owner)

    def test_cancellation_blocks_late_result_and_preserves_owner_boundary(self):
        started, release = threading.Event(), threading.Event()
        def transcriber(pcm, cancel):
            started.set(); release.wait(2); return 'Must not publish'
        service = self.service(transcriber)
        identity = service.submit(self.owner, audio()); self.assertTrue(started.wait(2))
        with self.assertRaises(ValueError): service.submit(self.owner, audio())
        with self.assertRaises(PermissionError): service.cancel(identity, self.other)
        service.cancel(identity, self.owner); release.set(); service.queue.join()
        result = service.get(identity, self.owner)
        self.assertEqual(result['status'], 'canceled'); self.assertNotIn('text', result)

    def test_queue_bound_errors_and_expiry(self):
        started, release = threading.Event(), threading.Event()
        def transcriber(pcm, cancel):
            started.set(); release.wait(3); raise RuntimeError('SECRET TRANSCRIPT')
        service = self.service(transcriber)
        identity = service.submit(self.owner, audio()); self.assertTrue(started.wait(2))
        service.submit('second', audio()); service.submit('third', audio())
        with self.assertRaises(ValueError): service.submit('fourth', audio())
        with self.assertRaises(ValueError): service.submit('fifth', b'x' * (MAX_BYTES+1))
        release.set(); result = self.finished(service, identity)
        self.assertNotIn('SECRET', json.dumps(result))
        service.jobs[identity]['created'] -= 1000
        self.assertEqual(service.get(identity, self.owner)['status'], 'failed')
        service.jobs[identity]['finished'] -= 301
        with self.assertRaises(PermissionError): service.get(identity, self.owner)


class SpeechHTTPTests(test_engine.HTTPTests):
    # Avoid inheriting/re-running every unrelated HTTP test in this focused suite.
    def test_speech_api_auth_csrf_admin_and_audio_body(self):
        self.application.speech.close()
        self.application.speech = Speech(self.config, lambda pcm, cancel: 'Recognized question')
        def upload(csrf=None):
            request=urllib.request.Request(self.base+'/api/speech/transcribe',data=audio(),headers={
                'Content-Type':'audio/wav','X-CSRF-Token':self.csrf if csrf is None else csrf})
            try: response=self.client.open(request,timeout=10)
            except urllib.error.HTTPError as error: response=error
            with response: return response.status, json.load(response)
        self.assertEqual(upload()[0],403)
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/speech/settings',{'enabled':True,'device':'cpu'})[0],403)
        self.login()
        self.assertEqual(self.request('/api/speech/settings',{'enabled':True,'device':'cpu'},{'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/speech/settings',{'enabled':True,'device':'cpu'})[0],200)
        self.assertEqual(upload('wrong')[0],403)
        status,result=upload(); self.assertEqual(status,202); identity=result['job_id']
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            status,result=self.request('/api/speech/jobs/'+identity)
            if result['status']=='completed': break
            time.sleep(.01)
        self.assertEqual(result['text'],'Recognized question')
        self.login('other','test-password-other')
        self.assertEqual(self.request('/api/speech/jobs/'+identity)[0],403)
        self.assertEqual(self.request('/api/speech/jobs/'+identity+'/cancel',{})[0],403)
        self.login()
        self.assertEqual(self.request('/api/speech/jobs/'+identity+'/consume',{})[0],200)
        self.assertEqual(self.request('/api/speech/jobs/'+identity)[0],403)
        self.assertEqual(self.request('/speech.js')[0],200)


# Inherit setup/request helpers, not the parent tests themselves.
for _name in list(vars(test_engine.HTTPTests)):
    if _name.startswith('test_'):
        setattr(SpeechHTTPTests, _name, None)
