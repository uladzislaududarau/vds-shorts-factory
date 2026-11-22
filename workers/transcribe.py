"""One speech-recognition process per transcription; cancelling the job kills this process.

Apple Silicon Mac: MLX Whisper on Metal. Windows, Intel Mac, Linux: faster-whisper (CTranslate2) on the CPU, int8.
Both engines write the same JSON: {text, language, segments:[{start, end, text, words:[{word, start, end, probability}]}]}.
"""
import json
import platform
import sys
from pathlib import Path

def apple_silicon():
    return sys.platform == 'darwin' and platform.machine() == 'arm64'

def model_size(model):
    """Settings store the MLX repo name (mlx-community/whisper-small); faster-whisper takes the size (small)."""
    return model.rsplit('/', 1)[-1].removeprefix('whisper-').removesuffix('-mlx')

def transcribe_mlx(audio, model, language):
    from backend.config import DATA
    import mlx_whisper
    import mlx.core as mx
    if not mx.metal.is_available():
        raise RuntimeError('MLX Metal is unavailable; run natively on Apple Silicon')
    from huggingface_hub import HfApi, snapshot_download
    locations = DATA/'models/installed.json'
    installed = json.loads(locations.read_text()) if locations.exists() else {}
    cached = installed.get(model,{})
    if cached and (Path(cached['path'])/'config.json').exists() and (Path(cached['path'])/cached['weight']).exists():
        model_path = cached['path']
    else:
        info = HfApi().model_info(model)
        available = {entry.rfilename for entry in info.siblings}
        weight = next((name for name in ('model.safetensors','weights.safetensors','weights.npz') if name in available),None)
        if not weight:
            raise RuntimeError('Whisper repository has no supported weight file')
        # Download only one checkpoint rather than every format in the repository.
        model_path = snapshot_download(model,revision=info.sha,allow_patterns=['config.json',weight])
        installed[model] = {'path':model_path,'weight':weight,'revision':info.sha}
        temporary = locations.with_suffix('.tmp')
        temporary.write_text(json.dumps(installed))
        temporary.replace(locations)
    return mlx_whisper.transcribe(audio, path_or_hf_repo=model_path, word_timestamps=True,
                                  language=None if language == 'auto' else language,
                                  condition_on_previous_text=False, verbose=False)

def to_result(segments, detected_language):
    """faster-whisper segments → the MLX Whisper JSON shape used by the rest of the studio."""
    result = []
    for s in segments:
        result.append({'start': s.start, 'end': s.end, 'text': s.text,
                       'words': [{'word': w.word, 'start': w.start, 'end': w.end, 'probability': w.probability} for w in (s.words or [])]})
    return {'text': ''.join(s['text'] for s in result).strip(), 'language': detected_language, 'segments': result}

def transcribe_portable(audio, model, language):
    from backend.config import DATA
    from faster_whisper import WhisperModel
    # CPU int8 everywhere: GPU (CUDA) needs NVIDIA cuBLAS/cuDNN libraries that are not part of this installation.
    engine = WhisperModel(model_size(model), device='cpu', compute_type='int8', download_root=str(DATA/'models/faster-whisper'))
    segments, info = engine.transcribe(audio, language=None if language == 'auto' else language,
                                       word_timestamps=True, condition_on_previous_text=False)
    return to_result(segments, info.language)

def main():
    audio, destination, model, language = sys.argv[1:]
    result = (transcribe_mlx if apple_silicon() else transcribe_portable)(audio, model, language)
    output = Path(destination)
    temp = output.with_suffix('.tmp')
    temp.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temp.replace(output)

if __name__ == '__main__':
    main()
