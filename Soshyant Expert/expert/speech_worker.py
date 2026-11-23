"""Isolated Bark inference. Reads PCM in memory, writes JSON; no runtime downloads."""
import base64
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')


def offline_only(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
        raise RuntimeError('Network access is disabled in local speech inference.')


sys.addaudithook(offline_only)


def main():
    root, device = Path(sys.argv[1]), sys.argv[2]
    pcm = base64.b64decode(sys.stdin.buffer.read(), validate=True)
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import torch
        from transformers import AutoProcessor, GenerationConfig, ParakeetForTDT, ParakeetTDTConfig
        if device == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable')
        torch.set_num_threads(min(8, max(1, (os.cpu_count() or 2) // 2)))
        spec = importlib.util.spec_from_file_location('bark_loader', root / 'bark_loader.py')
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        weights, config = loader.load_state_dict(root / 'model.bark')
        model = ParakeetForTDT(ParakeetTDTConfig.from_dict(config))
        missing, unexpected = model.load_state_dict({key: value.float() for key, value in weights.items()}, strict=False)
        if unexpected or any('num_batches_tracked' not in key for key in missing):
            raise RuntimeError('Incompatible speech weights')
        del weights
        model.generation_config = GenerationConfig.from_pretrained(root / 'processor', local_files_only=True)
        model.eval().to(device=device, dtype=torch.float32)
        processor = AutoProcessor.from_pretrained(root / 'processor', local_files_only=True)
        wave = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
        if not len(wave) or float(np.sqrt(np.mean(wave ** 2))) < .0003:
            raise RuntimeError('No audible speech')
        wave = np.concatenate([np.zeros(4000, np.float32), wave])
        inputs = processor([wave], sampling_rate=16000, return_tensors='pt', padding=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            output = model.generate(**inputs)
        text = processor.batch_decode(output.sequences, skip_special_tokens=True)[0].strip()
    print(json.dumps({'text': text}, ensure_ascii=False))


if __name__ == '__main__':
    main()
