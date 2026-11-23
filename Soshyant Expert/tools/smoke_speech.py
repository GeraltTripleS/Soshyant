"""Run actual offline Bark on an explicitly supplied synthetic/test WAV, never a microphone."""
import argparse
import audioop
import base64
import json
from pathlib import Path
import subprocess
import time
import wave

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio', type=Path, help='Short synthetic/test PCM16 WAV')
    args = parser.parse_args()
    with wave.open(str(args.audio), 'rb') as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1 or source.getnframes() / source.getframerate() > 30:
            raise ValueError('Use a short mono PCM16 test WAV.')
        pcm = source.readframes(source.getnframes())
        if source.getframerate() != 16000:
            pcm = audioop.ratecv(pcm, 2, 1, source.getframerate(), 16000, None)[0]
    started = time.monotonic()
    result = subprocess.run([str(ROOT / 'speech-runtime/python.exe'), '-I', str(ROOT / 'expert/speech_worker.py'),
        str(ROOT / 'assets/speech'), 'cpu'], input=base64.b64encode(pcm), capture_output=True, timeout=180)
    if result.returncode:
        print(result.stderr.decode('utf-8', errors='replace'))
        raise RuntimeError('Real speech smoke failed')
    text = json.loads(result.stdout)['text']
    report = {'text': text, 'elapsed_seconds': round(time.monotonic()-started, 2),
              'device': 'cpu', 'network': 'Python network events blocked by speech worker',
              'scope': 'Explicit synthetic/test recording; no microphone or customer documents',
              'recognized_warranty': 'warranty' in text.lower()}
    print(json.dumps(report, indent=2))
    if not report['recognized_warranty']:
        raise RuntimeError('Expected test phrase was not recognized')


if __name__ == '__main__':
    main()
