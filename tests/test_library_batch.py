import json
import time
import zipfile
from types import SimpleNamespace
from contextlib import contextmanager
from pathlib import Path

import pytest

from backend import db,library
from workers.queue import Farm,enqueue

@pytest.fixture
def library_data(client,source,tmp_path,monkeypatch):
    root=tmp_path/'media'
    for name in ('sources','renders','projects','exports'):(root/name).mkdir(parents=True)
    original=root/'sources/original.mp4';original.write_bytes(b'original fixture must survive')
    db.execute('UPDATE sources SET path=? WHERE id=?',('sources/original.mp4',source['id']))
    monkeypatch.setattr(library,'DATA',root)
    monkeypatch.setattr(library,'ROOT',tmp_path)
    monkeypatch.setattr(library,'safe_path',lambda relative:root/relative)
    clips=[client.post(f'/api/sources/{source["id"]}/manual-clip',json={'start':start,'end':start+10}).json() for start in (0,20)]
    return root,original,clips

OVERRIDES={'aspect':'4:5','fps':60,'crop_mode':'smart','smart_fallback':'center','subtitle_preset':'High Contrast','subtitles_enabled':False}

def test_queue_survives_a_cancelled_job_removed_during_worker_cleanup(isolated_db):
    farm=Farm()
    farm.active={'deleted-during-cleanup':SimpleNamespace(done=lambda:False)}
    farm.start()
    try:
        time.sleep(.55)
        assert farm.thread.is_alive()
    finally:farm.stop()

def test_bulk_route_creates_all_with_shared_settings_and_zip_dependency(client,library_data):
    root,original,clips=library_data
    first=clips[0]
    plan=first['plan'];plan['segments']=[{'start':1,'end':4},{'start':6,'end':9}];plan['volume']=.7
    assert client.put(f'/api/clips/{first["id"]}/plan',json=plan).status_code==200
    result=client.post('/api/clips/batch/render',json={'ids':[c['id'] for c in clips],'overrides':OVERRIDES,'download_zip':True})
    assert result.status_code==200,result.text  # Previously /batch/ was treated as a clip ID.
    payload=result.json()
    assert len(payload['jobs'])==2 and payload['export_job_id']
    for item in payload['jobs']:
        job=db.one('SELECT * FROM jobs WHERE id=?',(item['job_id'],))
        edit=json.loads(job['payload'])['plan']
        assert edit['crop_mode']=='smart' and edit['smart_fallback']=='center'
        assert edit['aspect']=='4:5' and edit['fps']==60 and not edit['subtitles']['enabled']
        assert edit['subtitles']['preset']=='High Contrast'
        if item['clip_id']==first['id']:
            assert edit['segments']==plan['segments'] and edit['volume']==.7
    archive=db.one('SELECT * FROM jobs WHERE id=?',(payload['export_job_id'],))
    settings=json.loads(archive['payload'])
    assert archive['kind']=='export' and len(settings['required_jobs'])==2
    assert not settings['include_metadata'] and not settings['include_subtitles']

def test_bulk_preflight_is_atomic_when_selection_is_stale(client,library_data):
    _,_,clips=library_data
    result=client.post('/api/clips/batch/render',json={'ids':[clips[0]['id'],'missing-id'],'overrides':OVERRIDES})
    assert result.status_code==400 and 'Обновите список' in result.json()['detail']
    assert db.one('SELECT COUNT(*) n FROM jobs')['n']==0
    assert db.one('SELECT revision FROM clips WHERE id=?',(clips[0]['id'],))['revision']==1
    assert db.one('SELECT COUNT(*) n FROM projects')['n']==0

def test_fifty_five_selected_clips_queue_in_one_operation(client,library_data):
    _,_,clips=library_data
    source_id=clips[0]['source_id']
    for number in range(53):
        clips.append(client.post(f'/api/sources/{source_id}/manual-clip',json={'start':number,'end':number+5}).json())
    response=client.post('/api/clips/batch/render',json={'ids':[c['id'] for c in clips],'overrides':OVERRIDES,'download_zip':True})
    assert response.status_code==200 and response.json()['clips']==55
    assert db.one("SELECT COUNT(*) n FROM jobs WHERE kind='render' AND status='Queued'")['n']==55
    assert db.one("SELECT COUNT(*) n FROM jobs WHERE kind='export' AND status='Queued'")['n']==1

def test_active_different_plan_does_not_partially_enqueue_batch(client,library_data):
    _,_,clips=library_data
    assert client.post(f'/api/clips/{clips[1]["id"]}/render').status_code==200
    response=client.post('/api/clips/batch/render',json={'ids':[c['id'] for c in clips],'overrides':OVERRIDES})
    assert response.status_code==400 and 'другими настройками' in response.json()['detail']
    assert db.one('SELECT COUNT(*) n FROM jobs')['n']==1
    assert db.one('SELECT COUNT(*) n FROM projects')['n']==0

def test_approval_can_be_added_and_removed_in_bulk(client,library_data):
    _,_,clips=library_data;ids=[c['id'] for c in clips]
    assert client.post('/api/clips/batch/approve',json={'ids':ids,'approved':True}).json()['updated']==2
    assert all(c['approved'] for c in client.get('/api/clips').json())
    assert client.post('/api/clips/batch/approve',json={'ids':ids,'approved':False}).status_code==200
    assert not any(c['approved'] for c in client.get('/api/clips').json())

def artifacts(root,clip):
    cid=clip['id']
    paths=[root/'renders'/f'{cid}-r1-old.mp4',root/'renders'/f'{cid}-r2-current.mp4',
           root/'renders'/f'{cid}-r2-current.srt',root/'renders'/f'{cid}-r2-current.ass',
           root/'projects'/f'{cid}.json',root/'exports'/f'clean-{cid}-cached.mp4']
    for path in paths:path.write_bytes(b'owned clip artifact')
    db.execute('UPDATE clips SET render_path=? WHERE id=?',(str(paths[1].relative_to(root)),cid))
    return paths

def test_deletion_removes_only_selected_artifacts_and_preserves_originals_exports(client,library_data):
    root,original,clips=library_data
    paths=artifacts(root,clips[0]);kept=artifacts(root,clips[1])
    old_zip=root/'exports/already-downloaded.zip';old_zip.write_bytes(b'old archive')
    jid=enqueue('render',clips[0]['source_id'],{'plan':clips[0]['plan'],'revision':1},clips[0]['id'])
    db.job_update(jid,status='Completed')
    response=client.post('/api/clips/batch/delete',json={'ids':[clips[0]['id']]})
    assert response.status_code==200,response.text
    assert response.json()['deleted']==1 and response.json()['removed_bytes']>0
    assert not any(p.exists() for p in paths) and all(p.exists() for p in kept)
    assert original.exists() and old_zip.exists()
    assert db.one('SELECT * FROM clips WHERE id=?',(clips[0]['id'],)) is None
    assert db.one('SELECT id FROM deleted_clips WHERE id=?',(clips[0]['id'],))
    assert db.one('SELECT * FROM render_tasks WHERE job_id=?',(jid,)) is None
    assert client.get('/api/sources/'+clips[0]['source_id']).json()['clip_count']==1

def test_busy_selection_is_not_deleted_partially(client,library_data):
    root,original,clips=library_data;paths=artifacts(root,clips[0])
    jid=enqueue('render',clips[1]['source_id'],{'plan':clips[1]['plan'],'revision':1},clips[1]['id'])
    db.job_update(jid,status='Paused')
    response=client.post('/api/clips/batch/delete',json={'ids':[c['id'] for c in clips]})
    assert response.status_code==400 and 'незавершённой' in response.json()['detail']
    assert all(p.exists() for p in paths) and db.one('SELECT COUNT(*) n FROM clips')['n']==2

def test_delete_restores_files_when_database_commit_fails(client,library_data,monkeypatch):
    root,original,clips=library_data;paths=artifacts(root,clips[0])
    connect=db.connect
    @contextmanager
    def failing():
        with connect() as connection:
            yield connection
            raise RuntimeError('Test database commit failure')
    monkeypatch.setattr(db,'connect',failing)
    response=client.post('/api/clips/batch/delete',json={'ids':[clips[0]['id']]})
    assert response.status_code==400
    monkeypatch.setattr(db,'connect',connect)
    assert all(p.exists() for p in paths) and original.exists()
    assert db.one('SELECT * FROM clips WHERE id=?',(clips[0]['id'],))
    assert not db.one('SELECT * FROM deleted_clips WHERE id=?',(clips[0]['id'],))

def test_export_job_waits_for_paused_renders_then_makes_video_only_zip(client,library_data,monkeypatch):
    import backend.main as main
    import backend.metadata as metadata
    root,_,clips=library_data
    monkeypatch.setattr(main,'DATA',root)
    monkeypatch.setattr(main,'safe_path',lambda relative:root/relative)
    monkeypatch.setattr(metadata,'delivery_path',lambda clip,job_id=None:root/clip['render_path'])
    result=client.post('/api/clips/batch/render',json={'ids':[c['id'] for c in clips],'download_zip':True}).json()
    for item in result['jobs']:db.job_update(item['job_id'],status='Paused')
    farm=Farm();farm.start()
    try:
        time.sleep(.55)
        assert db.one('SELECT status FROM jobs WHERE id=?',(result['export_job_id'],))['status']=='Queued'
        for item,clip in zip(result['jobs'],clips):
            path=root/'renders'/f'{clip["id"]}.mp4';path.write_bytes(b'completed render fixture')
            db.execute('UPDATE clips SET render_path=? WHERE id=?',(str(path.relative_to(root)),clip['id']))
            db.job_update(item['job_id'],status='Completed')
        for _ in range(50):
            row=db.one('SELECT * FROM jobs WHERE id=?',(result['export_job_id'],))
            if row['status'] in ('Completed','Failed'):break
            time.sleep(.1)
        assert row['status']=='Completed',row['error']
        export_id=json.loads(row['checkpoints'])['download_url'].rsplit('/',1)[-1]
        with zipfile.ZipFile(root/'exports'/f'{export_id}.zip') as archive:
            assert sorted(archive.namelist())==sorted(c['id']+'.mp4' for c in clips)
            assert all(z.date_time==(1980,1,1,0,0,0) for z in archive.infolist())
    finally:farm.stop()
