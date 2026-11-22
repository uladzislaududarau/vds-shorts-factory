import json
import time
import pytest
from backend import db
from workers.queue import Farm,enqueue

def test_settings_and_secret_response(client):
    result=client.get('/api/settings').json()
    assert 'api_key' not in str(result)
    assert client.put('/api/settings',json={'values':{'fps':37}}).status_code==400
    assert client.put('/api/settings',json={'values':{'cloud_enabled':'yes'}}).status_code==400
    assert client.put('/api/settings',json={'values':{'budget_usd':-1}}).status_code==400
    assert client.put('/api/settings',json={'values':{'fps':60}}).status_code==200
    assert db.settings()['fps']==60

def test_local_security(client):
    assert client.post('/api/storage/clear-cache',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==403
    assert client.post('/api/storage/clear-cache',headers={'X-Factory-Client':''}).status_code==403

def test_bad_file_and_rights(client):
    result=client.post('/api/import/files',data={'rights_status':'owned','license':'Original test'},files={'files':('broken.mp4',b'not a video','video/mp4')})
    assert result.status_code==200 and result.json()[0]['error']
    result=client.post('/api/import/files',data={'rights_status':'unknown','license':''},files={'files':('bad.mp4',b'x','video/mp4')})
    assert result.status_code in (400,422)

def test_queue_controls_persistence_and_dedup(client,source):
    response=client.post('/api/sources/'+source['id']+'/analyze',json={})
    assert response.status_code==200
    jid=response.json()['job_id']
    assert client.post('/api/sources/'+source['id']+'/analyze',json={}).json()['job_id']==jid
    assert client.post(f'/api/jobs/{jid}/pause').json()['status']=='Paused'
    assert client.post(f'/api/jobs/{jid}/resume').json()['status']=='Queued'
    assert client.post(f'/api/jobs/{jid}/cancel').json()['status']=='Cancelled'
    assert client.post(f'/api/jobs/{jid}/retry').json()['status']=='Queued'
    assert db.one('SELECT status FROM jobs WHERE id=?',(jid,))['status']=='Queued'
    assert client.post(f'/api/jobs/{jid}/retry').status_code==400
    assert client.post('/api/storage/clear-cache').status_code==400

def test_failed_task_without_cloud_key(source):
    jid=enqueue('analysis',source['id'],{'options':{},'settings':db.settings()})
    farm=Farm()
    farm.work(jid)
    result=db.one('SELECT * FROM jobs WHERE id=?',(jid,))
    assert result['status']=='Failed'
    assert 'URL' in result['error']
    farm.executor.shutdown()

def test_restart_requeues_running(source):
    jid=enqueue('analysis',source['id'],{'options':{},'settings':db.settings()})
    db.job_update(jid,status='Running',checkpoints=db.dump({'audio':True}))
    farm=Farm()
    # Stop polling for this deterministic recovery test, before any task gets picked up.
    farm.stop_event.set()
    farm.start()
    row=db.one('SELECT * FROM jobs WHERE id=?',(jid,))
    assert row['status']=='Queued'
    assert json.loads(row['checkpoints'])['audio']
    farm.stop()

def test_edit_plan_and_export_metadata(client,source):
    r=client.post(f'/api/sources/{source["id"]}/manual-clip',json={'start':1,'end':22})
    assert r.status_code==200
    clip=r.json()
    plan=clip['plan']
    plan['subtitles']['color']='#FFCC00'
    r=client.put(f'/api/clips/{clip["id"]}/plan',json=plan)
    assert r.status_code==200 and r.json()['revision']==2
    assert db.one('SELECT * FROM projects WHERE clip_id=?',(clip['id'],))
    exported=client.post('/api/exports',json={'ids':[clip['id']]}).json()
    assert client.get(exported['url']).status_code==200

def test_ai_response_persistence_with_mock(source,transcript,monkeypatch):
    from backend.schemas import AnalyzeOptions
    from backend.analysis import LocalProvider
    from workers.queue import Farm
    options=AnalyzeOptions(min_duration=10,max_duration=25)
    result=LocalProvider().analyze(source,transcript,options,[],None)
    from backend.schemas import CandidateList
    payload=CandidateList(candidates=result).model_dump_json()
    db.execute('INSERT INTO analysis VALUES(?,?,?,?,?,?)',(db.uid(),source['id'],'mock-key','gemini-mock',payload,time.time()))
    assert CandidateList.model_validate_json(db.one('SELECT data FROM analysis')['data']).candidates
