import json
import os
import time
from pathlib import Path

import pytest

from backend import db,youtube_auth as auth

@pytest.fixture
def session_dir(tmp_path,monkeypatch):
    path=tmp_path/'private-session'
    monkeypatch.setattr(auth,'SECRET_DIR',path)
    return path

def cookies(*lines):
    return ('# Netscape HTTP Cookie File\n'+'\n'.join(lines)+'\n').encode()

YT='.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tunit-test-only-value'

def test_session_filters_other_sites_and_never_returns_values(client,session_dir):
    response=client.post('/api/youtube/cookies',data={'consent':'true'},files={'file':('cookies.txt',cookies(YT,'.example.com\tTRUE\t/\tTRUE\t0\tSID\tother-site-test'))})
    assert response.status_code==200 and response.json()['connected']
    assert 'unit-test-only-value' not in response.text
    saved=(session_dir/'cookies.txt').read_text()
    assert 'youtube.com' in saved and 'example.com' not in saved and 'other-site-test' not in saved
    assert os.name=='nt' or os.stat(session_dir).st_mode&0o777==0o700
    assert os.name=='nt' or os.stat(session_dir/'cookies.txt').st_mode&0o777==0o600
    assert client.get('/api/youtube/session').json()['cookie_count']==1

@pytest.mark.parametrize('raw',[
    b'{"cookies":"not Netscape"}',
    cookies('.youtube.com.evil.test\tTRUE\t/\tTRUE\t0\tSID\ttest'),
    cookies('.youtube.com\tTRUE\t/\tTRUE\t1\tSID\texpired'),
    cookies('.youtube.com\tTRUE\t/\tTRUE\t0\tPREF\tlogged-out'),
    cookies('.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tbad\textra'),
])
def test_bad_or_logged_out_cookie_file_is_rejected(client,session_dir,raw):
    result=client.post('/api/youtube/cookies',data={'consent':'true'},files={'file':('cookies.txt',raw)})
    assert result.status_code==400
    assert not (session_dir/'cookies.txt').exists()

def test_connect_requires_explicit_consent(client,session_dir,monkeypatch):
    monkeypatch.setattr(auth,'connect_managed',lambda:pytest.fail('must not read browser without consent'))
    assert client.post('/api/youtube/connect',json={'consent':False}).status_code==422
    assert client.post('/api/youtube/cookies',files={'file':('cookies.txt',cookies(YT))}).status_code==400

def test_snapshot_is_private_independent_and_removed_on_error(session_dir):
    auth.save_cookies(cookies(YT),'test')
    snapshot=None
    with pytest.raises(RuntimeError):
        with auth.cookie_snapshot(True) as snapshot:
            assert snapshot!=session_dir/'cookies.txt'
            assert os.name=='nt' or snapshot.stat().st_mode&0o777==0o600
            auth.disconnect()
            assert snapshot.exists() and 'SID' in snapshot.read_text()
            raise RuntimeError('cancel fixture')
    assert not snapshot.exists() and not auth.status()['connected']

def test_disconnect_wins_over_inflight_browser_connection(session_dir,monkeypatch):
    (session_dir/'browser/Default').mkdir(parents=True)
    auth.save_cookies(cookies(YT),'test')
    def extract(args,**kwargs):
        auth.disconnect()
        Path(args[-1]).write_bytes(cookies(YT))
    monkeypatch.setattr(auth,'run',extract)
    with pytest.raises(ValueError,match='изменилась'):
        auth.connect_managed()
    assert not auth.status()['connected']

def test_download_queue_is_persistent_deduplicated_and_cookie_free(client,session_dir):
    auth.save_cookies(cookies(YT),'test')
    payload={'url':'https://youtu.be/abcdef12345','rights_status':'permission','license':'Test permission','use_account':True,'analyze_after':True}
    first=client.post('/api/import/youtube',json=payload)
    assert first.status_code==200
    jid=first.json()['job_id']
    second=client.post('/api/import/youtube',json=payload)
    assert second.json()['job_id']==jid and second.json()['duplicate']
    row=db.one('SELECT * FROM jobs WHERE id=?',(jid,))
    assert row['kind']=='download' and row['source_id'] is None and row['status']=='Queued'
    assert 'unit-test-only-value' not in row['payload'] and '.cookies' not in row['payload']
    job=client.get('/api/jobs').json()[0]
    assert job['source_name'].startswith('YouTube') and 'payload' not in job
    assert client.post(f'/api/jobs/{jid}/pause').json()['status']=='Paused'
    assert client.post(f'/api/jobs/{jid}/resume').json()['status']=='Queued'
    assert client.post(f'/api/jobs/{jid}/cancel').json()['status']=='Cancelled'
    assert client.post(f'/api/jobs/{jid}/retry').json()['status']=='Queued'

def test_authenticated_download_needs_session_but_public_mode_works(client,session_dir):
    payload={'url':'https://youtu.be/abcdef12345','rights_status':'owned','license':'Test fixture'}
    assert client.post('/api/import/youtube',json=payload).status_code==400
    assert client.post('/api/import/youtube',json={**payload,'use_account':False}).status_code==200

def test_local_host_guard_applies_to_account(client,session_dir):
    assert client.post('/api/youtube/login',headers={'Origin':'https://attacker.example'}).status_code==403
    assert client.delete('/api/youtube/session',headers={'X-Factory-Client':''}).status_code==403

def test_existing_local_source_does_not_require_reconnecting_account(client,source,session_dir,tmp_path,monkeypatch):
    import backend.youtube as module
    media=tmp_path/'already-downloaded.mp4';media.write_bytes(b'existing fixture')
    monkeypatch.setattr(module,'safe_path',lambda p:media)
    url='https://www.youtube.com/watch?v=abcdef12345'
    db.execute('UPDATE sources SET url=?,path=? WHERE id=?',(url,'sources/fixture.mp4',source['id']))
    response=client.post('/api/import/youtube',json={'url':url,'rights_status':'owned','license':'Original fixture','use_account':True})
    assert response.status_code==200 and response.json()['already_downloaded']
    assert db.one("SELECT COUNT(*) n FROM jobs WHERE kind='download'")['n']==0

def test_download_worker_handoff_and_resume_without_redownload(source,session_dir,tmp_path,monkeypatch):
    import backend.youtube as module
    from backend.schemas import YouTubeDownload
    from backend.config import DEFAULTS
    root=tmp_path/'data'
    (root/'temp').mkdir(parents=True)
    (root/'sources').mkdir()
    media=root/'sources/fixture.mp4';media.write_bytes(b'test-only-local-placeholder')
    monkeypatch.setattr(module,'DATA',root)
    monkeypatch.setattr(module,'safe_path',lambda p:root/p)
    db.execute('UPDATE sources SET path=? WHERE id=?',('sources/fixture.mp4',source['id']))
    payload=YouTubeDownload(url='https://youtu.be/abcdef12345',rights_status='permission',license='Test fixture',use_account=False)
    jid=module.enqueue_download(payload)['job_id']
    db.job_update(jid,status='Running',checkpoints=db.dump({'download_source_id':source['id']}))
    monkeypatch.setattr(module,'run_youtube',lambda *a,**kw:pytest.fail('checkpoint must not redownload'))
    module.download(db.one('SELECT * FROM jobs WHERE id=?',(jid,)),lambda *a:pytest.fail('must not reimport'),DEFAULTS)
    cp=json.loads(db.one('SELECT checkpoints FROM jobs WHERE id=?',(jid,))['checkpoints'])
    assert db.one('SELECT kind FROM jobs WHERE id=?',(cp['analysis_job_id'],))['kind']=='analysis'
    module.download(db.one('SELECT * FROM jobs WHERE id=?',(jid,)),None,DEFAULTS)
    assert db.one("SELECT COUNT(*) n FROM jobs WHERE kind='analysis'")['n']==1
