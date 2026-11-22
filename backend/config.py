import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
DB_PATH = Path(os.environ.get('SHORTS_DB', ROOT / 'database/factory.sqlite3'))
for name in ('sources', 'audio', 'transcripts', 'thumbnails', 'ai-cache', 'projects', 'previews', 'renders', 'exports', 'temp', 'models','audio-replacements'):
    (DATA / name).mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('HF_HOME', str(DATA / 'models'))
os.environ.setdefault('MPLCONFIGDIR', str(DATA / 'temp/matplotlib'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
SECRET_PATH = ROOT / '.secrets/gemini.key'
FFMPEG = os.environ.get('FFMPEG_BINARY', 'ffmpeg')
FFPROBE = os.environ.get('FFPROBE_BINARY', 'ffprobe')
DEFAULTS = {
    'provider': 'local', 'model': '', 'cloud_enabled': False,
    'whisper_model': 'mlx-community/whisper-tiny', 'language': 'auto',
    'min_duration': 20.0, 'max_duration': 40.0, 'target_count': 5,
    'score_threshold': 35, 'profile': 'Educational',
    'subtitle_preset': 'Bold Viral', 'aspect': '9:16', 'fps': 30,
    'crop_mode': 'blur', 'encoder': 'auto', 'render_quality': 20,
    'min_free_mb': 512, 'max_upload_mb': 10240,
    'ai_concurrency': 1, 'whisper_concurrency': 1, 'ffmpeg_concurrency': 1,
    'budget_usd': 5.0, 'input_price_per_million': None, 'output_price_per_million': None,
    'cloud_request_limit': 30, 'max_output_tokens': 8192,
    'openai_model': '', 'openai_budget_usd': 2.0, 'openai_request_limit': 10,
    'openai_input_price_per_million': None, 'openai_output_price_per_million': None,
    'openai_max_output_tokens': 4096,
    'elevenlabs_voice_id': '', 'elevenlabs_model': 'eleven_multilingual_v2',
    'elevenlabs_request_limit': 10,
    'music_model': 'music_v2_5','music_request_limit':60,'music_seconds_limit':1800,
    'publish_language':'en','publish_category':'20','publish_made_for_kids':None,
    'publish_synthetic':None,'publish_paused':False,
}

def safe_path(relative: str) -> Path:
    path = (DATA / relative).resolve()
    if not path.is_relative_to(DATA.resolve()):
        raise ValueError('Unsafe media path')
    return path

def secret(provider='gemini') -> str:
    path = SECRET_PATH if provider == 'gemini' else ROOT / '.secrets' / f'{provider}.key'
    if provider not in ('gemini','openai','elevenlabs'):
        raise ValueError('Unknown secret provider')
    return (path.read_text().strip() if path.exists() else os.environ.get(provider.upper()+'_API_KEY', '')).strip()

def write_secret(provider, value):
    path = SECRET_PATH if provider == 'gemini' else ROOT / '.secrets' / f'{provider}.key'
    if provider not in ('gemini','openai','elevenlabs'):
        raise ValueError('Unknown secret provider')
    path.parent.mkdir(mode=0o700,exist_ok=True)
    path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix='.key-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream: stream.write(value.strip())
        os.replace(temporary,path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def redact(message: str) -> str:
    text = str(message)
    for provider in ('gemini','openai','elevenlabs'):
        key = secret(provider)
        if key: text = text.replace(key,'[redacted]')
    return re.sub(r'sk-(?:proj-)?[A-Za-z0-9_-]{12,}', '[redacted]', text)[:3000]
