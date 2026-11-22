import json
from pathlib import Path

import pytest

from backend import db, media


PAYLOAD={'url':'https://www.youtube.com/watch?v=abcdef12345',
         'rights_status':'owned','license':'Original test fixture'}


@pytest.mark.parametrize(('failure','expected'),[
    ('python: ERROR: Sign in to confirm your age. Use --cookies-from-browser chrome','по возрасту'),
    ('ERROR: This video is age-restricted','по возрасту'),
    ('ERROR: Private video. Sign in if you have access','авторизацию'),
    ("ERROR: Sign in to confirm you’re not a bot",'авторизацию'),
    ('ERROR: The uploader has not made this video available in your country','регионе'),
    ('ERROR: HTTP Error 429: Too Many Requests','число запросов'),
])
def test_metadata_refusals_are_actionable_and_do_not_create_sources(client,monkeypatch,failure,expected):
    calls=[]
    def refuse(args,**kwargs):
        calls.append(args)
        raise RuntimeError(failure)
    monkeypatch.setattr(media,'run',refuse)
    response=client.post('/api/import/url',json=PAYLOAD)
    assert response.status_code==400
    detail=response.json()['detail']
    assert expected in detail
    assert '--cookies' not in detail and 'python:' not in detail
    assert len(calls)==1  # An auth refusal must not cause repeated requests.
    assert not any(arg.startswith('--cookies') for arg in calls[0])
    assert db.one('SELECT COUNT(*) n FROM sources')['n']==0


def test_download_refusal_uses_same_message_and_cleans_partial_files(client,monkeypatch,tmp_path):
    import backend.main as main
    (tmp_path/'temp').mkdir()
    monkeypatch.setattr(main,'DATA',tmp_path)
    monkeypatch.setattr(main,'check_space',lambda *args:None)
    calls=[]
    def extract(args,**kwargs):
        calls.append(args)
        if '--dump-single-json' in args:
            return json.dumps({'title':'Original test fixture','duration':60})
        output=args[args.index('-o')+1].replace('%(ext)s','mp4.part')
        Path(output).write_bytes(b'partial fixture')
        raise RuntimeError('ERROR: Sign in to confirm your age')
    monkeypatch.setattr(media,'run',extract)
    response=client.post('/api/import/url',json={**PAYLOAD,'download':True})
    assert response.status_code==400
    assert 'по возрасту' in response.json()['detail']
    assert len(calls)==2 and not list((tmp_path/'temp').iterdir())
    assert db.one('SELECT COUNT(*) n FROM sources')['n']==0


def test_public_metadata_still_imports(client,monkeypatch):
    monkeypatch.setattr(media,'run',lambda *a,**kw:json.dumps(
        {'title':'Original public fixture','duration':60,'uploader':'Fixture'}))
    response=client.post('/api/import/url',json=PAYLOAD)
    assert response.status_code==200
    assert response.json()['source']['name']=='Original public fixture'
    assert db.one('SELECT COUNT(*) n FROM sources')['n']==1


def test_timeout_is_readable(client,monkeypatch):
    def timeout(*args,**kwargs):raise TimeoutError('python exceeded 90s')
    monkeypatch.setattr(media,'run',timeout)
    response=client.post('/api/import/url',json=PAYLOAD)
    assert response.status_code==400
    assert 'не ответил вовремя' in response.json()['detail']
