import json
import threading
import time

import pytest

from backend import db
from backend.config import DATA, FFMPEG
from backend.media import run, probe


@pytest.fixture(autouse=True)
def keep_montage_folders_clean():
    """Tests use an isolated SQLite but the real data/ tree: remove every file they add."""
    from backend.montage import MEDIA_DIR, WORDS_DIR, PREVIEW_DIR
    folders = (MEDIA_DIR, WORDS_DIR, PREVIEW_DIR, DATA / 'renders')
    before = {p for folder in folders for p in folder.iterdir()}
    yield
    for folder in folders:
        for path in folder.iterdir():
            if path not in before and path.is_file():
                path.unlink(missing_ok=True)


def make_video(path, size, seconds, audio=True, freq=440):
    args = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=size={size}:rate=30']
    if audio:
        args += ['-f', 'lavfi', '-i', f'sine=frequency={freq}:sample_rate=48000']
    args += ['-t', str(seconds), '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p']
    if audio:
        args += ['-c:a', 'aac', '-shortest']
    run(args + [path])
    return path


def upload(client, path, confirmed=True):
    with path.open('rb') as handle:
        response = client.post('/api/montage/media', data={'confirmed': 'true' if confirmed else 'false'},
                               files={'files': (path.name, handle, 'application/octet-stream')})
    return response


@pytest.fixture
def media(client, tmp_path):
    wide = make_video(tmp_path / 'wide.mp4', '640x360', 3)
    tall = make_video(tmp_path / 'tall.mov', '360x640', 2.5, audio=False)
    music = tmp_path / 'music.mp3'
    run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=44100',
         '-t', '6', '-c:a', 'libmp3lame', music])
    items = [upload(client, p).json()[0] for p in (wide, tall, music)]
    assert all('error' not in i for i in items), items
    return items


def run_job(kind, project, plan):
    from backend.montage import render_project, recognise_project
    jid = db.uid()
    now = time.time()
    payload = {'plan': plan, 'revision': project['revision'], 'project_id': project['id'], 'title': project['title']}
    db.execute('INSERT INTO jobs(id,source_id,clip_id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
               (jid, None, None, kind, 'Running', db.dump(payload), now, now))
    job = db.one('SELECT * FROM jobs WHERE id=?', (jid,))
    (render_project if kind == 'montage' else recognise_project)(job, threading.Semaphore(1), threading.Semaphore(1))
    db.job_update(jid, status='Completed', stage='Completed', progress=100)
    return db.one('SELECT * FROM jobs WHERE id=?', (jid,))


def test_upload_requires_rights_and_deduplicates(client, tmp_path):
    clip = make_video(tmp_path / 'a.mp4', '320x240', 1)
    assert upload(client, clip, confirmed=False).status_code == 400
    first = upload(client, clip).json()[0]
    second = upload(client, clip).json()[0]
    assert first['id'] == second['id'] and first['kind'] == 'video'
    bad = tmp_path / 'notes.txt'
    bad.write_text('hello')
    assert 'error' in upload(client, bad).json()[0]
    assert [m['id'] for m in client.get('/api/montage/media?kind=video').json()] == [first['id']]


@pytest.mark.parametrize('fmt,size', [('9:16', (1080, 1920)), ('16:9', (1920, 1080))])
def test_real_montage_render_with_trim_audio_and_captions(client, media, tmp_path, fmt, size):
    wide, tall, music = media
    project = client.post('/api/montage/projects', json={'title': 'Тест монтажа'}).json()
    plan = {
        'format': fmt, 'fit': 'blur' if fmt == '9:16' else 'fit',
        'clips': [
            {'id': 'c1', 'media_kind': 'upload', 'media_id': wide['id'], 'start': .5, 'end': 2.5, 'volume': 1},
            {'id': 'c2', 'media_kind': 'upload', 'media_id': tall['id'], 'start': 0, 'end': 1.5, 'captions': False},
        ],
        'audio': [{'id': 'm1', 'media_id': music['id'], 'at': 1, 'offset': .5, 'duration': 10, 'volume': .5, 'fade_out': .5}],
        'subtitles': {'template': 'box', 'color': '#FFFFFF', 'accent': '#7C3AED', 'size': 70, 'uppercase': False,
                      'words': 3, 'outline': 0, 'position': .7},
        # Authored timing fixture: no Whisper in unit tests.
        'caption_edits': {'c1': [{'word': 'Привет', 'start': .6, 'end': 1.2}, {'word': 'монтаж!', 'start': 1.3, 'end': 2.0}]},
    }
    saved = client.put(f'/api/montage/projects/{project["id"]}', json={'title': 'Тест монтажа', 'plan': plan})
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    assert saved['revision'] == 2 and abs(saved['duration'] - 3.5) < 1e-6
    assert saved['words']['c1'][0]['word'] == 'Привет'
    job = run_job('montage', saved, saved['plan'])
    qc = json.loads(job['checkpoints'])['qc']
    assert qc['passed'] and qc['full_decode'] and qc['metadata_clean']
    assert (qc['width'], qc['height']) == size
    assert abs(qc['duration'] - 3.5) < .1 and qc['word_count'] == 2
    detail = client.get(f'/api/montage/projects/{project["id"]}').json()
    assert detail['video_url'] and not detail['stale']
    output = DATA / json.loads(job['checkpoints'])['output_path']
    try:
        info = probe(output)
        assert info['has_audio']
        assert output.with_suffix('.srt').read_text(encoding='utf-8').count('-->') == 1
        # Caption plate (accent colour) is burned in while the first words are spoken.
        frame = tmp_path / 'frame.png'
        run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-ss', '0.3', '-i', output, '-frames:v', '1', '-update', '1', frame])
        from PIL import Image
        pixels = Image.open(frame).convert('RGB').get_flattened_data()
        assert sum(1 for r, g, b in pixels if abs(r - 124) < 30 and abs(g - 58) < 30 and b > 200) > 500
        # The silent second clip still has an audio track (music overlay continues over it).
        assert client.get(detail['video_url']).status_code == 200
        jobs = client.get('/api/jobs').json()
        assert any(j['source_name'].startswith('Монтаж') and j['output'] for j in jobs)
    finally:
        output.unlink(missing_ok=True)
        output.with_suffix('.srt').unlink(missing_ok=True)


def test_validation_rejects_bad_trim_and_duplicate_ids(client, media):
    wide, _, music = media
    project = client.post('/api/montage/projects', json={}).json()
    too_long = {'clips': [{'id': 'c1', 'media_kind': 'upload', 'media_id': wide['id'], 'start': 0, 'end': 9}]}
    response = client.put(f'/api/montage/projects/{project["id"]}', json={'title': 'x', 'plan': too_long})
    assert response.status_code == 400 and 'длительность' in response.json()['detail']
    duplicate = {'clips': [{'id': 'same', 'media_kind': 'upload', 'media_id': wide['id'], 'start': 0, 'end': 1}],
                 'audio': [{'id': 'same', 'media_id': music['id'], 'duration': 1}]}
    assert client.put(f'/api/montage/projects/{project["id"]}', json={'title': 'x', 'plan': duplicate}).status_code == 422
    assert client.post(f'/api/montage/projects/{project["id"]}/render').status_code == 400


def test_library_fragment_uses_source_transcript(client, source, transcript):
    from backend.montage import MontagePlan, timeline_words, whisper_model
    db.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?)', (source['id'], 'test', 'en', 'x', db.dump(transcript), time.time()))
    plan = MontagePlan.model_validate({'clips': [
        {'id': 'a', 'media_kind': 'source', 'media_id': source['id'], 'start': 0.3, 'end': 3.3},
        {'id': 'b', 'media_kind': 'source', 'media_id': source['id'], 'start': 4.3, 'end': 5.3}]})
    words = timeline_words(plan, whisper_model())
    assert words[0]['word'] == 'Why' and words[0]['start'] == 0
    second = [w for w in words if w['clip'] == 1]
    assert second and all(3.0 <= w['start'] < 4.0 for w in second)


def test_caption_preview_and_templates(client):
    templates = client.get('/api/montage/templates').json()
    assert [t['id'] for t in templates] == ['bold', 'box', 'single', 'clean', 'neon']
    for template in templates:
        style = json.dumps({'template': template['id'], **template['defaults']})
        response = client.get('/api/montage/caption-preview', params={'style': style, 'crop': 'true'})
        assert response.status_code == 200 and response.content[:4] == b'\x89PNG'
    overlay = client.get('/api/montage/caption-preview', params={'style': json.dumps({'template': 'bold'}), 'format': '16:9'})
    from PIL import Image
    import io
    assert Image.open(io.BytesIO(overlay.content)).size == (960, 540)


def test_project_reports_its_queued_render_with_audio_items(client, media):
    # Regression: an audio item must not shadow the project row when looking up jobs.
    wide, _, music = media
    project = client.post('/api/montage/projects', json={}).json()
    plan = {'clips': [{'id': 'c1', 'media_kind': 'upload', 'media_id': wide['id'], 'start': 0, 'end': 2}],
            'audio': [{'id': 'm1', 'media_id': music['id'], 'duration': 2}]}
    assert client.put(f'/api/montage/projects/{project["id"]}', json={'title': 'x', 'plan': plan}).status_code == 200
    job_id = client.post(f'/api/montage/projects/{project["id"]}/render').json()['job_id']
    detail = client.get(f'/api/montage/projects/{project["id"]}').json()
    assert detail['jobs']['montage']['id'] == job_id
    assert detail['last_render']['id'] == job_id and detail['last_render']['status'] == 'Queued'
    assert client.post(f'/api/montage/projects/{project["id"]}/render').json()['job_id'] == job_id
    assert client.delete(f'/api/montage/projects/{project["id"]}').status_code == 400


@pytest.fixture
def fake_eleven(monkeypatch, tmp_path):
    """Eleven Music answered by a mock transport with a real MP3 of the requested length. No paid request is made."""
    import httpx
    from backend import audio_replacement as audio, config
    monkeypatch.setattr(audio, 'DATA', tmp_path)
    monkeypatch.setattr(audio, 'secret', lambda p: 'fixture-not-a-real-key')
    monkeypatch.setattr(config, 'secret', lambda p='gemini': 'fixture-not-a-real-key' if p == 'elevenlabs' else '')
    requests = []
    original = httpx.Client

    def handler(request):
        body = json.loads(request.content)
        requests.append({'url': str(request.url), 'key': request.headers.get('xi-api-key'), 'body': body})
        song = tmp_path / f'song-{len(requests)}.mp3'
        run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency={300 + 100 * len(requests)}:sample_rate=44100',
             '-t', str(body['music_length_ms'] / 1000), '-c:a', 'libmp3lame', song])
        return httpx.Response(200, content=song.read_bytes(), headers={'song-id': f'song-{len(requests)}'})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return requests


def run_music(client, pid, body):
    from backend.montage import generate_project_music
    response = client.post(f'/api/montage/projects/{pid}/music', json=body)
    assert response.status_code == 200, response.text
    jid = response.json()['job_id']
    db.execute("UPDATE jobs SET status='Running' WHERE id=?", (jid,))
    generate_project_music(db.one('SELECT * FROM jobs WHERE id=?', (jid,)))
    db.job_update(jid, status='Completed', stage='Completed', progress=100)
    return jid


def test_ai_music_covers_whole_montage_and_replaces_previous_variant(client, media, fake_eleven, tmp_path):
    wide, tall, _ = media
    project = client.post('/api/montage/projects', json={}).json()
    plan = {'clips': [{'id': 'c1', 'media_kind': 'upload', 'media_id': wide['id'], 'start': 0, 'end': 3},
                      {'id': 'c2', 'media_kind': 'upload', 'media_id': tall['id'], 'start': 0, 'end': 2.5}]}
    client.put(f'/api/montage/projects/{project["id"]}', json={'title': 'Мультик', 'plan': plan})
    assert client.post(f'/api/montage/projects/{project["id"]}/music', json={'style': 'kids'}).status_code == 422  # consent required
    assert client.post(f'/api/montage/projects/{project["id"]}/music', json={'style': 'custom', 'notes': '', 'consent': True}).status_code == 422
    options = client.get('/api/montage/music-options').json()
    assert options['key_connected'] and any(s['id'] == 'kids' for s in options['styles'])

    run_music(client, project['id'], {'style': 'kids', 'tempo': 'fast', 'notes': 'колокольчики, как в мультфильме', 'consent': True})
    sent = fake_eleven[0]
    assert sent['url'].startswith('https://api.elevenlabs.io/v1/music') and sent['key'] == 'fixture-not-a-real-key'
    assert sent['body']['music_length_ms'] == 5500 and sent['body']['force_instrumental'] is True
    assert 'cartoon' in sent['body']['prompt'] and '128 BPM' in sent['body']['prompt'] and 'колокольчики' in sent['body']['prompt']
    detail = client.get(f'/api/montage/projects/{project["id"]}').json()
    music = [a for a in detail['plan']['audio'] if a['kind'] == 'music']
    assert len(music) == 1 and music[0]['at'] == 0 and abs(music[0]['duration'] - 5.5) < .1 and music[0]['label'] == 'Детская / мультик'
    assert detail['media'][music[0]['id']]['media_url'] and len(detail['music_variants']) == 1
    assert detail['revision'] == 3

    # The editor still holds revision 2: its stale save must not silently drop the new track.
    stale = client.put(f'/api/montage/projects/{project["id"]}', json={'title': 'Мультик', 'plan': plan, 'revision': 2})
    assert stale.status_code == 409

    run_music(client, project['id'], {'style': 'custom', 'notes': 'тихий эмбиент с пианино', 'consent': True})
    detail = client.get(f'/api/montage/projects/{project["id"]}').json()
    music = [a for a in detail['plan']['audio'] if a['kind'] == 'music']
    assert len(music) == 1 and music[0]['label'] == 'тихий эмбиент с пианино'
    assert len(detail['music_variants']) == 2 and len(fake_eleven) == 2
    from backend.audio_replacement import music_stats
    assert music_stats()['requests'] == 2

    # The generated background renders like any other audio track.
    job = run_job('montage', detail, detail['plan'])
    qc = json.loads(job['checkpoints'])['qc']
    assert qc['passed'] and qc['audio_items'] == 1 and abs(qc['duration'] - 5.5) < .1


def test_ai_music_preflight_checks_key_and_limits(client, media, monkeypatch):
    from backend import config
    wide = media[0]
    project = client.post('/api/montage/projects', json={}).json()
    body = {'style': 'action', 'consent': True}
    assert 'клипы' in client.post(f'/api/montage/projects/{project["id"]}/music', json=body).json()['detail']
    plan = {'clips': [{'id': 'c1', 'media_kind': 'upload', 'media_id': wide['id'], 'start': 0, 'end': 3}]}
    client.put(f'/api/montage/projects/{project["id"]}', json={'title': 'x', 'plan': plan})
    monkeypatch.setattr(config, 'secret', lambda p='gemini': '')
    assert 'ключ ElevenLabs' in client.post(f'/api/montage/projects/{project["id"]}/music', json=body).json()['detail']
    monkeypatch.setattr(config, 'secret', lambda p='gemini': 'fixture')
    db.execute("UPDATE settings SET value='2' WHERE key='music_seconds_limit'")
    assert 'лимит' in client.post(f'/api/montage/projects/{project["id"]}/music', json=body).json()['detail']
    assert not db.one("SELECT id FROM jobs WHERE kind='montage_music'")
