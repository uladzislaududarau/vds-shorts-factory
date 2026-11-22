import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from .config import FFMPEG, FFPROBE, DATA, ROOT, redact

class Interrupted(Exception):
    pass

def run_youtube(args, timeout, job_id=None, on_progress=None):
    """Translate expected platform refusals without retrying authentication gates."""
    try:
        return run(args, timeout=timeout, job_id=job_id, on_progress=on_progress)
    except TimeoutError:
        raise ValueError('YouTube не ответил вовремя. Проверьте подключение и повторите импорт.') from None
    except RuntimeError as error:
        logging.getLogger(__name__).warning('YouTube import failed: %s', redact(str(error)))
        message = str(error).lower()
        if any(text in message for text in ('confirm your age', 'age-restricted', 'age restricted', 'inappropriate for some users')):
            detail = ('YouTube ограничил доступ к этому видео по возрасту. В блоке «Аккаунт YouTube» войдите в аккаунт с подтверждённым возрастом, '
                      'нажмите «Подключить сессию» и повторите скачивание с включённым переключателем «Использовать мой аккаунт». '
                      'Если сессия уже подключена, обновите её и убедитесь, что видео открывается в этом аккаунте.')
        elif any(text in message for text in ('not a bot', 'private video', 'sign in', 'members-only', 'members only', 'join this channel')):
            detail = ('YouTube требует авторизацию или проверку доступа к этому видео. '
                      'Войдите через «Аккаунт YouTube», подключите сессию и повторите скачивание с вашим аккаунтом. '
                      'Если сессия уже подключена, обновите её; аккаунт должен иметь доступ к этому видео.')
        elif any(text in message for text in ('not available in your country', 'not made this video available in your country', 'geo-restricted')):
            detail = 'YouTube ограничил доступ к видео в вашем регионе. Можно загрузить доступный вам локальный исходник во вкладке «Файлы».'
        elif any(text in message for text in ('video unavailable', 'video has been removed', 'video is unavailable')):
            detail = 'Видео недоступно на YouTube: проверьте ссылку или загрузите локальный исходник во вкладке «Файлы».'
        elif '429' in message or 'too many requests' in message:
            detail = 'YouTube временно ограничил число запросов. Подождите и повторите импорт.'
        elif 'недостаточно' in message or 'лимит размера' in message:
            detail = 'Скачивание остановлено: недостаточно места или видео превышает лимит размера. Проверьте Settings → Хранилище и свободное место на диске.'
        elif 'requested format is not available' in message or 'only images are available' in message:
            detail = 'YouTube не выдал доступный видеоформат. Обновите сессию аккаунта и повторите; подробности сохранены в журнале сервера.'
        else:
            detail = ('Не удалось получить видео с YouTube. Проверьте ссылку и подключение; '
                      'если ошибка повторяется, загрузите локальный исходник во вкладке «Файлы».')
        raise ValueError(detail) from None

def check_space(required=0, reserve_mb=512):
    free = shutil.disk_usage(DATA).free
    if free - required < reserve_mb * 1024**2:
        raise ValueError(f'Недостаточно места: свободно {free / 1024**2:.0f} МБ; требуется {required / 1024**2:.0f} МБ + резерв {reserve_mb} МБ')

def check_job(job_id):
    if not job_id:
        return
    from .db import one
    job = one('SELECT status FROM jobs WHERE id=?', (job_id,))
    if not job or job['status'] in ('Cancelled', 'Paused'):
        raise Interrupted(job['status'] if job else 'Cancelled')

# Each tool runs in its own process group so Pause/Cancel stops it together with its children.
ISOLATED = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {'start_new_session': True}

def stop_tree(p):
    """Terminate a tool and everything it started: process group on macOS/Linux, taskkill /T on Windows."""
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(p.pid)], capture_output=True, **ISOLATED)
        p.wait()
        return
    try:
        os.killpg(p.pid, 15)
        p.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(p.pid, 9)
        except ProcessLookupError:
            pass
        p.wait()

def run(args, job_id=None, timeout=3600, on_progress=None):
    """No shell. File-backed stderr prevents pipe deadlocks and unbounded memory."""
    import tempfile
    with tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as out:
        p = subprocess.Popen([str(a) for a in args], stdout=out, stderr=err, stdin=subprocess.DEVNULL, **ISOLATED)
        began = time.monotonic()
        try:
            while p.poll() is None:
                check_job(job_id)
                if on_progress:
                    on_progress()
                if time.monotonic() - began > timeout:
                    raise TimeoutError(f'{Path(str(args[0])).name} exceeded {timeout}s')
                time.sleep(.2)
            if p.returncode:
                err.seek(max(0, err.tell() - 4000))
                raise RuntimeError(f'{Path(str(args[0])).name}: ' + err.read().decode('utf-8', 'replace'))
            out.seek(0)
            return out.read().decode('utf-8', 'replace')
        finally:
            if p.poll() is None:
                stop_tree(p)

def probe(path: Path):
    # Force the permitted container: an uploaded file must not be auto-detected as
    # a playlist that causes FFprobe to fetch network URLs or other local files.
    suffix = Path(path).suffix.lower()
    demuxer = 'mov' if suffix in ('.mp4','.mov') else 'matroska' if suffix in ('.mkv','.webm') else None
    if demuxer is None:
        raise ValueError('Unsupported container')
    raw = json.loads(run([FFPROBE, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-f', demuxer,
                          '-show_format', '-show_streams', '-of', 'json', path], timeout=60))
    video = next((s for s in raw['streams'] if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    if not video:
        raise ValueError('Файл не содержит видеодорожку')
    a, _, b = video.get('avg_frame_rate', '0/1').partition('/')
    duration = float(raw.get('format', {}).get('duration', video.get('duration', 0)))
    if not 0 < duration < 86400:
        raise ValueError('Invalid or excessive video duration (maximum 24 hours)')
    rotation = int(next((d.get('rotation', 0) for d in video.get('side_data_list', []) if 'rotation' in d), 0))
    width, height = int(video['width']), int(video['height'])
    if abs(rotation) % 180 == 90:
        width, height = height, width
    return {'duration': duration, 'width': width, 'height': height, 'fps': float(a) / max(float(b or 1), 1),
            'has_audio': int(any(s['codec_type'] == 'audio' for s in raw['streams'])), 'raw': raw}

def thumbnail(path, output, duration):
    run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(min(duration / 3, 10)), '-i', path,
         '-frames:v', '1', '-vf', 'scale=640:-2', '-update', '1', output], timeout=60)

def capabilities():
    filters = run([FFMPEG, '-hide_banner', '-filters'], timeout=20)
    encoders = run([FFMPEG, '-hide_banner', '-encoders'], timeout=20)
    return {'libass': ' subtitles ' in filters, 'videotoolbox': 'h264_videotoolbox' in encoders,
            'ffmpeg': run([FFMPEG, '-version'], timeout=10).splitlines()[0]}

def validate_youtube(url):
    from urllib.parse import urlparse, parse_qs
    u = urlparse(url)
    if u.scheme != 'https' or u.hostname not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be') or u.username or u.password or u.port:
        raise ValueError('Требуется публичный HTTPS URL YouTube без авторизации')
    import re
    video_id = u.path.lstrip('/') if u.hostname == 'youtu.be' else (parse_qs(u.query).get('v', [''])[0] if u.path == '/watch' else u.path.split('/')[-1] if u.path.startswith(('/shorts/', '/embed/')) else '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise ValueError('Нужен URL одного видео YouTube')
    return f'https://www.youtube.com/watch?v={video_id}'
