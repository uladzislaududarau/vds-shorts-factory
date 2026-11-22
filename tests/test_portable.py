"""Cross-platform pieces that the Windows build relies on (they run on every OS)."""
import subprocess
import sys
from types import SimpleNamespace

from workers import transcribe


def test_model_size_maps_settings_names_to_faster_whisper_sizes():
    assert transcribe.model_size('mlx-community/whisper-tiny') == 'tiny'
    assert transcribe.model_size('mlx-community/whisper-small-mlx') == 'small'
    assert transcribe.model_size('mlx-community/whisper-large-v3-turbo') == 'large-v3-turbo'


def test_faster_whisper_output_matches_mlx_json_shape():
    from backend.analysis import transcript_words
    word = lambda w, s, e: SimpleNamespace(word=w, start=s, end=e, probability=.9)
    segments = [SimpleNamespace(start=0.0, end=1.2, text=' Привет мир.', words=[word(' Привет', 0.0, .5), word(' мир.', .6, 1.2)]),
                SimpleNamespace(start=1.5, end=2.0, text=' Ещё', words=None)]
    result = transcribe.to_result(iter(segments), 'ru')
    assert result['language'] == 'ru' and result['text'] == 'Привет мир. Ещё'
    assert [w['word'] for w in transcript_words(result)] == ['Привет', 'мир.']


def test_engine_choice_by_platform(monkeypatch):
    monkeypatch.setattr(transcribe.sys, 'platform', 'win32')
    assert not transcribe.apple_silicon()
    monkeypatch.setattr(transcribe.sys, 'platform', 'darwin')
    monkeypatch.setattr(transcribe.platform, 'machine', lambda: 'arm64')
    assert transcribe.apple_silicon()


def test_run_stops_the_whole_tool_tree_on_cancel(isolated_db):
    import time
    from backend import db
    from backend.media import run, Interrupted
    jid = db.uid(); now = time.time()
    db.execute('INSERT INTO jobs(id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?)', (jid, 'render', 'Cancelled', '{}', now, now))
    started = time.monotonic()
    try:
        run([sys.executable, '-c', 'import time; time.sleep(30)'], jid)
    except Interrupted:
        pass
    assert time.monotonic() - started < 10


def test_health_reports_os(client):
    assert client.get('/api/health').json()['os'] == sys.platform
