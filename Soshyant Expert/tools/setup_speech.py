"""Provision optional isolated CPU speech runtime. Setup requires internet; inference does not."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import html
from pathlib import Path
import shutil
import re
import subprocess
import sys
import urllib.request
import zipfile
from urllib.parse import unquote, urlsplit, urldefrag

ROOT = Path(__file__).resolve().parents[1]
REPO = 'ConwayResearch/Underdog-Bark-3.0'
REVISION = '85db2ad18ab41e534a222ee253c29191d77ed919'


def fetch(url, target, expected, size):
    """Small validated range requests avoid stalled large transfers; resume verified chunks."""
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
        return
    chunk = 4 * 1024 * 1024
    def part(index):
        start, end = index * chunk, min(size, (index + 1) * chunk) - 1
        path = target.with_name(target.name + f'.part{index}')
        if path.is_file() and path.stat().st_size == end - start + 1:
            return path
        request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                raise RuntimeError('Unexpected range response for ' + target.name)
            body = response.read(end-start+2)
        if len(body) != end-start+1:
            raise RuntimeError('Incomplete download chunk')
        path.write_bytes(body)
        return path
    target.parent.mkdir(parents=True, exist_ok=True)
    total = (size + chunk - 1) // chunk
    with ThreadPoolExecutor(max_workers=6) as executor:
        paths = []
        for path in executor.map(part, range(total)):
            paths.append(path)
            if len(paths) % 20 == 0:
                print(f'{target.name}: {len(paths)}/{total} download chunks', flush=True)
    temporary = target.with_suffix(target.suffix + '.download')
    digest = hashlib.sha256()
    with temporary.open('wb') as output:
        for path in paths:
            body = path.read_bytes(); digest.update(body); output.write(body)
    if digest.hexdigest() != expected:
        raise RuntimeError('Download checksum mismatch: ' + target.name)
    temporary.replace(target)
    # Delete only exact chunk files created under the verified workspace destination.
    for path in paths:
        path.unlink()


def metadata(repo, revision='main'):
    with urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true', timeout=60) as response:
        return json.load(response)


def download(repo, revision, filename, destination, entries):
    record = next(row for row in entries if row['rfilename'] == filename)
    expected = record.get('lfs', {}).get('sha256')
    if destination.is_file() and expected and hashlib.sha256(destination.read_bytes()).hexdigest() == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if expected and record.get('size', 0) > 8 * 1024 * 1024:
        fetch(f'https://huggingface.co/{repo}/resolve/{revision}/{filename}', destination, expected, record['size'])
        return
    temporary = destination.with_suffix(destination.suffix + '.download')
    print('Downloading', filename, flush=True)
    with urllib.request.urlopen(f'https://huggingface.co/{repo}/resolve/{revision}/{filename}', timeout=120) as response, temporary.open('wb') as stream:
        shutil.copyfileobj(response, stream)
    body = temporary.read_bytes()
    if expected and hashlib.sha256(body).hexdigest() != expected:
        raise RuntimeError('Checksum mismatch: ' + filename)
    # Git blob hash verifies small non-LFS assets against the pinned repository metadata.
    if not expected and record.get('blobId') and hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest() != record['blobId']:
        raise RuntimeError('Git blob checksum mismatch: ' + filename)
    temporary.replace(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pip-python', type=Path, help='Optional existing Python with pip; never modified')
    args = parser.parse_args()
    runtime = ROOT / 'speech-runtime'
    if not runtime.exists():
        print('Preparing independent speech runtime...', flush=True)
        shutil.copytree(ROOT / 'runtime', runtime, ignore=shutil.ignore_patterns('site-packages', '__pycache__', 'Scripts', 'include', 'libs', 'tcl'))
    target = runtime / 'Lib/site-packages'
    if args.pip_python:
        pip = [str(args.pip_python), '-m', 'pip']
    else:
        if not (target / 'pip').is_dir():
            # Bootstrap from Python's bundled wheel into this private target only.
            # Leave the copied distribution's EXTERNALLY-MANAGED marker intact.
            wheel = next((runtime / 'Lib/ensurepip/_bundled').glob('pip-*.whl'))
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(wheel) as archive:
                if any(not (target / name).resolve().is_relative_to(target.resolve()) for name in archive.namelist()):
                    raise RuntimeError('Unexpected path in bundled pip wheel')
                archive.extractall(target)
        pip = [str(runtime / 'python.exe'), '-m', 'pip']
    if not (runtime / 'torch-ready.txt').exists():
        with urllib.request.urlopen('https://download.pytorch.org/whl/cpu/torch/', timeout=60) as response:
            index = response.read().decode()
        link = next(html.unescape(value) for value in re.findall(r'href="([^"]+)"', index)
                    if 'torch-2.8.0%2Bcpu-cp311-cp311-win_amd64.whl#sha256=' in value)
        url, fragment = urldefrag(link)
        digest = fragment.split('=', 1)[1]
        wheel = ROOT / 'speech-downloads' / unquote(Path(urlsplit(url).path).name)
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Range': 'bytes=0-0'}), timeout=30) as response:
            size = int(response.headers['Content-Range'].split('/')[-1])
            response.read(1)
        print('Downloading verified CPU inference package...', flush=True)
        fetch(url, wheel, digest, size)
        subprocess.run(pip + ['install', '--disable-pip-version-check', '--no-warn-script-location',
            '--target', str(target), str(wheel)], check=True)
        (runtime / 'torch-ready.txt').write_text('2.8.0+cpu', encoding='utf-8')
    if not (runtime / 'dependencies-ready.txt').exists():
        subprocess.run(pip + ['install', '--disable-pip-version-check', '--no-warn-script-location',
            '--target', str(target), 'transformers==5.19.0', 'constriction==0.5.0', 'numpy==2.4.6',
            'soundfile==0.14.0', 'soxr==1.1.0', 'librosa==0.11.0'], check=True)
        (runtime / 'dependencies-ready.txt').write_text('installed', encoding='utf-8')
    asset = ROOT / 'assets/speech'
    info = metadata(REPO, REVISION)
    for filename in ('model.bark', 'bark_loader.py', 'NOTICE'):
        download(REPO, info['sha'], filename, asset / filename, info['siblings'])
    base = 'nvidia/parakeet-tdt-0.6b-v3'
    original = metadata(base)
    wanted = {'config.json', 'preprocessor_config.json', 'processor_config.json', 'tokenizer.json',
              'tokenizer_config.json', 'special_tokens_map.json', 'generation_config.json'}
    for row in original['siblings']:
        if row['rfilename'] in wanted:
            download(base, original['sha'], row['rfilename'], asset / 'processor' / row['rfilename'], original['siblings'])
    subprocess.run([str(runtime / 'python.exe'), '-I', '-c',
        'from transformers import AutoProcessor,GenerationConfig,ParakeetForTDT; import torch,constriction,numpy; '
        f'AutoProcessor.from_pretrained({str(asset / "processor")!r},local_files_only=True); '
        f'GenerationConfig.from_pretrained({str(asset / "processor")!r},local_files_only=True); print("Speech imports and offline processor: OK")'], check=True)
    manifest = {'model_repository': REPO, 'revision': info['sha'], 'processor_repository': base,
                'processor_revision': original['sha'], 'device': 'cpu', 'license': 'CC-BY-4.0', 'files': {}}
    for path in asset.rglob('*'):
        if path.is_file() and path.name != 'READY.json':
            manifest['files'][str(path.relative_to(asset))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (asset / 'READY.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Speech installed. Restart the server, then enable Local speech input in Maintenance & account.', flush=True)


if __name__ == '__main__':
    main()
