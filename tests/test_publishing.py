import os
import json
import logging
import time
from datetime import datetime
from urllib.parse import parse_qs,urlsplit
import httpx
import pytest
from backend import publishing as p,publishing_auth as auth,db
from backend.schemas import PublishBatch

CHANNEL='UC'+'a'*22
VID='aBcd1234xyz'
COPY={'title':'A useful moment','description':'A real description #Shorts','hashtags':['#Shorts'],'tags':['moment']}

@pytest.fixture
def setup(isolated_db,tmp_path,monkeypatch):
    monkeypatch.setattr(auth,'ROOT',tmp_path)
    monkeypatch.setattr(p,'DATA',tmp_path)
    monkeypatch.setattr(p,'safe_path',lambda value:tmp_path/value)
    auth.FLOWS.clear()
    auth.save_client({'client_id':'test.apps.googleusercontent.com','client_secret':'test-secret'})
    auth.write('token.json',{'access_token':'ACCESS_SECRET','refresh_token':'REFRESH_SECRET','expires_at':time.time()+3600,'channel':{'id':CHANNEL,'title':'My test channel'}})
    settings={**db.settings(),'cloud_enabled':True,'openai_model':'test-model','openai_request_limit':100,'publish_made_for_kids':False,'publish_synthetic':True}
    for k,v in settings.items():db.execute('UPDATE settings SET value=? WHERE key=?',(db.dump(v),k))
    from backend import integrations,metadata
    monkeypatch.setattr(integrations,'secret',lambda provider:'fake-openai-key')
    monkeypatch.setattr(metadata,'delivery_path',lambda clip:tmp_path/clip['render_path'])
    monkeypatch.setattr(p,'probe',lambda path:{'duration':20})
    def clip(index=1):
        sid,cid,jid=db.uid(),db.uid(),db.uid();now=time.time()
        path=tmp_path/f'{index}.mp4';path.write_bytes(f'fake-media-{index}'.encode())
        plan={'segments':[{'start':0,'end':20}],'aspect':'9:16'}
        db.execute('INSERT INTO sources(id,name,kind,duration,created_at) VALUES(?,?,?,?,?)',(sid,'test source','local',120,now))
        db.execute('INSERT INTO clips(id,source_id,title,start,end,score,provider,data,render_path,render_revision,revision,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(cid,sid,'Clip '+str(index),0,20,90,'local','{}',path.name,1,1,now))
        db.execute('INSERT INTO jobs(id,source_id,clip_id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(jid,sid,cid,'render','Completed',db.dump({'revision':1}),now,now))
        db.execute('INSERT INTO render_tasks VALUES(?,?,?)',(jid,db.dump(plan),db.dump({'passed':True})))
        return cid
    return clip

def admit(ids,**kw):return p.enqueue_batch(PublishBatch(ids=ids,channel_id=CHANNEL,consent=True,**kw))
def publication(result):return db.one('SELECT * FROM publications WHERE id=?',(result['jobs'][0]['id'],))
def job(row):return db.one('SELECT * FROM jobs WHERE id=?',(row['job_id'],))
def response(status,body=None,**headers):return httpx.Response(status,json=body or {},headers=headers)
def mock_copy(monkeypatch):
    def copy(row,jid):p.update(row['id'],metadata=db.dump(COPY));return COPY
    monkeypatch.setattr(p,'metadata',copy)

def test_fifty_slots_and_deduplication(setup):
    ids=[setup(i) for i in range(50)]
    result=admit(ids)
    assert result['clips']==50
    slots=db.rows('SELECT publish_at,channel_id FROM publications ORDER BY publish_at')
    assert all(b['publish_at']-a['publish_at']==3600 for a,b in zip(slots,slots[1:]))
    assert all(r['channel_id']==CHANNEL for r in slots)
    again=admit(ids)
    assert again['clips']==0 and len(again['duplicates'])==50
    second=publication(admit([setup(51)]))
    assert second['publish_at']==slots[-1]['publish_at']+3600

def test_preflight_atomic_missing_revision(setup):
    first,second=setup(1),setup(2)
    db.execute('UPDATE clips SET revision=2 WHERE id=?',(second,))
    with pytest.raises(ValueError,match='актуальные'):admit([first,second])
    assert not db.rows('SELECT * FROM publications')
    assert not db.rows("SELECT * FROM jobs WHERE kind='publish'")

def test_preflight_limits_profile_channel_and_qc(setup):
    cid=setup()
    db.execute("UPDATE settings SET value='null' WHERE key='publish_synthetic'")
    with pytest.raises(ValueError,match='отметку'):admit([cid])
    db.execute("UPDATE settings SET value='true' WHERE key='publish_synthetic'")
    db.execute("UPDATE settings SET value='0' WHERE key='openai_request_limit'")
    with pytest.raises(ValueError,match='лимит'):admit([cid])
    with pytest.raises(ValueError,match='канал'):p.enqueue_batch(PublishBatch(ids=[cid],channel_id='UC'+'b'*22,consent=True))
    db.execute("UPDATE settings SET value='100' WHERE key='openai_request_limit'")
    db.execute('UPDATE render_tasks SET qc=?',(db.dump({'passed':False}),))
    with pytest.raises(ValueError,match='качества'):admit([cid])

def test_private_no_schedule_and_no_secret_in_dto(setup):
    row=publication(admit([setup()],mode='private'))
    assert row['publish_at'] is None
    text=json.dumps(p.list_publications())
    assert not any(v in text for v in ['ACCESS_SECRET','REFRESH_SECRET','render_path','sha256'])

def test_start_rejects_past_dst_and_late_slot_append(setup):
    for value in ['2000-01-01T00:00','bad','2027-03-28T03:30','2027-10-31T03:30']:
        with pytest.raises(ValueError):p.parse_start(value)
    row=publication(admit([setup()]))
    db.execute('UPDATE publications SET publish_at=? WHERE id=?',(time.time()-10,row['id']))
    row=db.one('SELECT * FROM publications WHERE id=?',(row['id'],))
    occupied=publication(admit([setup(2)]))['publish_at']
    actual=p.reserve_future(row)
    assert actual>=time.time()+600 and abs(actual-occupied)>=3600

def test_oauth_pkce_one_use_and_secure_storage(setup,monkeypatch):
    url=auth.connect()['url'];params=parse_qs(urlsplit(url).query)
    assert params['scope']==[auth.SCOPE] and params['code_challenge_method']==['S256']
    assert 'test-secret' not in url
    state=params['state'][0]
    monkeypatch.setattr(auth,'token_request',lambda data:{'access_token':'new-access','refresh_token':'new-refresh','scope':auth.SCOPE,'expires_in':3600})
    monkeypatch.setattr(auth,'channel_for',lambda token:{'id':CHANNEL,'title':'My channel'})
    assert auth.callback(state,'code')['id']==CHANNEL
    with pytest.raises(ValueError,match='использована'):auth.callback(state,'code')
    assert os.name=='nt' or auth.private_path('token.json').stat().st_mode&0o777==0o600
    assert os.name=='nt' or auth.private_path('token.json').parent.stat().st_mode&0o777==0o700
    assert 'new-access' not in json.dumps(auth.status())
    with pytest.raises(ValueError,match='другой канал'):auth.access_token('UC'+'b'*22)

def test_oauth_scope_and_redirect_validation(setup,monkeypatch):
    with pytest.raises(ValueError,match='redirect'):auth.save_client({'web':{'client_id':'a.apps.googleusercontent.com','client_secret':'secret','redirect_uris':['http://evil.test']}})
    for scope in ['','https://www.googleapis.com/auth/youtube.upload']:
        state=parse_qs(urlsplit(auth.connect()['url']).query)['state'][0]
        monkeypatch.setattr(auth,'token_request',lambda data:{'access_token':'new','refresh_token':'refresh','scope':scope})
        with pytest.raises(ValueError,match='разрешение'):auth.callback(state,'code')
    with pytest.raises(ValueError):auth.callback('forged','code')

def test_oauth_access_log_redacts_code():
    record=logging.LogRecord('uvicorn.access',20,'',0,'%s - "%s %s HTTP/%s" %d',('127.0.0.1','GET','/api/publishing/oauth/callback?code=PRIVATE_CODE&state=SECRET','1.1',303),None)
    auth.OAuthLogFilter().filter(record)
    assert 'PRIVATE_CODE' not in record.getMessage()

@pytest.mark.parametrize('url',['http://www.googleapis.com/upload/youtube/v3/videos','https://www.googleapis.com.evil.test/upload/youtube/v3/videos','https://evil.test/upload/youtube/v3/videos','https://user:secret@www.googleapis.com/upload/youtube/v3/videos','https://www.googleapis.com:444/upload/youtube/v3/videos','https://www.googleapis.com/other'])
def test_session_url_rejects_exfiltration(url):
    with pytest.raises(ValueError):p.session_url(url)

def test_private_insert_then_schedule_and_retry_without_upload(setup,monkeypatch):
    row=publication(admit([setup()]));mock_copy(monkeypatch);calls=[]
    def remote(method,url=p.API,channel=None,**kw):
        calls.append((method,url,kw));assert channel==CHANNEL
        if method=='POST':
            assert kw['json']['status']['privacyStatus']=='private' and 'publishAt' not in kw['json']['status']
            return response(200,Location=p.UPLOAD+'?upload_id=PRIVATE_SESSION')
        if url.startswith(p.UPLOAD):return response(200,{'id':VID})
        if method=='GET':return response(200,{'items':[{'id':VID,'snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private'}}]})
        assert kw['json']['status']['privacyStatus']=='private'
        assert datetime.fromisoformat(kw['json']['status']['publishAt'].replace('Z','+00:00')).timestamp()>time.time()+590
        return response(200,{'id':VID,'status':kw['json']['status']})
    monkeypatch.setattr(p,'api_request',remote)
    p.work(job(row));done=db.one('SELECT * FROM publications WHERE id=?',(row['id'],))
    assert done['state']=='Scheduled' and done['youtube_id']==VID
    assert len([c for c in calls if c[0]=='POST'])==1
    assert 'PRIVATE_SESSION' not in json.dumps(p.list_publications())
    calls.clear();p.work(job(row));assert not any(c[0]=='POST' for c in calls)

def test_resume_chunk_after_network_loss_no_new_session(setup,monkeypatch):
    row=publication(admit([setup()],mode='private'));mock_copy(monkeypatch);calls=[]
    auth.write(p.session_name(row['id']),{'url':p.UPLOAD+'?upload_id=SECRET','offset':0,'attempted':True,'size':len(b'fake-media-1'),'sha256':row['sha256']})
    def remote(method,url=p.API,channel=None,**kw):
        calls.append((method,kw))
        if kw['headers']['Content-Range'].startswith('bytes */'):return response(308,Range='bytes=0-3')
        assert kw['headers']['Content-Range']=='bytes 4-11/12'
        assert kw['content']==b'-media-1'
        return response(201,{'id':VID})
    monkeypatch.setattr(p,'api_request',remote)
    p.work(job(row))
    assert db.one('SELECT state FROM publications')['state']=='Private'
    assert len(calls)==2 and all(c[0]=='PUT' for c in calls)

def test_expired_attempted_upload_blocks_duplicate(setup,monkeypatch):
    row=publication(admit([setup()]));mock_copy(monkeypatch)
    auth.write(p.session_name(row['id']),{'url':p.UPLOAD+'?upload_id=SECRET','attempted':True})
    monkeypatch.setattr(p,'api_request',lambda *a,**kw:response(410))
    with pytest.raises(p.ReviewRequired):p.work(job(row))
    assert db.one('SELECT state FROM publications')['state']=='Review'
    with pytest.raises(ValueError,match='запрещена'):p.control(job(row),'retry')

def test_recovery_after_final_upload_response_saved_before_db(setup,monkeypatch):
    row=publication(admit([setup()],mode='private'));mock_copy(monkeypatch)
    auth.write(p.session_name(row['id']),{'video_id':VID,'url':p.UPLOAD+'?upload_id=SECRET'})
    monkeypatch.setattr(p,'api_request',lambda *a,**kw:pytest.fail('Must recover ID without API upload'))
    p.work(job(row))
    assert db.one('SELECT youtube_id,state FROM publications')=={'youtube_id':VID,'state':'Private'}

def test_schedule_response_loss_reconciles_existing_without_repost(setup,monkeypatch):
    row=publication(admit([setup()]));mock_copy(monkeypatch)
    p.update(row['id'],youtube_id=VID)
    stamp=datetime.fromtimestamp(row['publish_at'],p.timezone.utc).isoformat()
    monkeypatch.setattr(p,'api_request',lambda method,*a,**kw:response(200,{'items':[{'snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private','publishAt':stamp}}]}) if method=='GET' else pytest.fail('Must not repost or reschedule confirmed video'))
    p.work(job(row));assert db.one('SELECT state FROM publications')['state']=='Scheduled'

def test_cancel_remote_removes_schedule_keeps_private(setup,monkeypatch):
    row=publication(admit([setup()]));p.update(row['id'],youtube_id=VID,state='Scheduled');db.job_update(row['job_id'],status='Completed')
    remote_status={'privacyStatus':'private','publishAt':'2028-01-01T12:00:00Z','selfDeclaredMadeForKids':False,'containsSyntheticMedia':True}
    def remote(method,*a,**kw):
        if method=='GET':return response(200,{'items':[{'snippet':{'channelId':CHANNEL},'status':dict(remote_status)}]})
        assert 'publishAt' not in kw['json']['status'] and kw['json']['status']['privacyStatus']=='private'
        remote_status.pop('publishAt');return response(200,{'status':remote_status})
    monkeypatch.setattr(p,'api_request',remote)
    assert p.cancel(row['id'])=={'cancelled':True}
    assert db.one('SELECT state,publish_at FROM publications')=={'state':'Cancelled','publish_at':None}

def test_cancel_during_schedule_request_clears_after_response(setup,monkeypatch):
    row=publication(admit([setup()]));p.update(row['id'],youtube_id=VID);db.job_update(row['job_id'],status='Running');mock_copy(monkeypatch)
    remote_status={'privacyStatus':'private'}
    def remote(method,*a,**kw):
        if method=='GET':return response(200,{'items':[{'snippet':{'channelId':CHANNEL},'status':dict(remote_status)}]})
        if kw['json']['status'].get('publishAt'):
            db.job_update(row['job_id'],status='Cancelled');remote_status.update(kw['json']['status']);return response(200,{'status':dict(remote_status)})
        remote_status.pop('publishAt',None);return response(200,{'status':dict(remote_status)})
    monkeypatch.setattr(p,'api_request',remote)
    with pytest.raises(p.Interrupted):p.work(job(row))
    assert 'publishAt' not in remote_status
    assert db.one('SELECT state FROM publications')['state']=='Cancelled'

def test_global_pause_and_quota_leave_other_jobs_alone(setup,monkeypatch):
    row=publication(admit([setup()]))
    with pytest.raises(ValueError,match='Квота'):p.require_ok(response(403,{'error':{'errors':[{'reason':'quotaExceeded'}]}}))
    with pytest.raises(p.Interrupted):p.work(job(row))
    assert db.one('SELECT status FROM jobs WHERE id=?',(row['job_id'],))['status']=='Paused'
    assert db.one("SELECT status FROM jobs WHERE kind='render'")['status']=='Completed'

def test_api_connect_callback_and_no_secrets(setup,client):
    assert client.get('/api/publishing').status_code==200
    status=client.get('/api/publishing/account').json()
    assert 'test-secret' not in json.dumps(status) and status['connected']
    assert client.post('/api/publishing/client',json=[]).status_code==400
    assert client.get('/api/publishing/oauth/callback?state=forged&code=SECRET').status_code==400
    assert client.post('/api/publishing/batch',json={'ids':[setup()],'channel_id':CHANNEL,'consent':False}).status_code==422
    queued=client.post('/api/publishing/batch',json={'ids':[db.one('SELECT id FROM clips')['id']],'channel_id':CHANNEL,'consent':True})
    assert queued.status_code==200
    assert client.post('/api/publishing/disconnect').status_code==400
    assert client.post('/api/publishing/pause',json={'paused':True}).status_code==200

def test_cancel_with_lost_schedule_response_requires_review(setup,monkeypatch):
    row=publication(admit([setup()]));p.update(row['id'],youtube_id=VID);db.job_update(row['job_id'],status='Running');mock_copy(monkeypatch)
    def remote(method,*a,**kw):
        if method=='GET':return response(200,{'items':[{'snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private'}}]})
        db.job_update(row['job_id'],status='Cancelled')
        raise ValueError('Network failed after request')
    monkeypatch.setattr(p,'api_request',remote)
    with pytest.raises(p.Interrupted):p.work(job(row))
    assert db.one('SELECT state FROM publications')['state']=='Review'
    assert db.one('SELECT status FROM jobs WHERE id=?',(row['job_id'],))['status']=='Cancelled'

def test_refresh_preserves_failed_schedule_retry_and_detects_publication(setup,monkeypatch):
    row=publication(admit([setup()]));p.update(row['id'],youtube_id=VID,state='Failed',error='Schedule failed');db.job_update(row['job_id'],status='Failed')
    state={'privacyStatus':'private'}
    monkeypatch.setattr(p,'api_request',lambda *a,**kw:response(200,{'items':[{'id':VID,'snippet':{'channelId':CHANNEL},'status':state}]}))
    p.refresh_remote();assert db.one('SELECT state FROM publications')['state']=='Failed'
    state['privacyStatus']='public'
    p.refresh_remote();assert db.one('SELECT state FROM publications')['state']=='Published'

def test_http_transport_does_not_leak_credentials(setup,monkeypatch):
    original=httpx.Client;seen=[]
    def transport(request):
        seen.append(request)
        assert request.headers['Authorization']=='Bearer ACCESS_SECRET'
        return response(200,{'items':[]})
    monkeypatch.setattr(p.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    assert p.api_request('GET',channel=CHANNEL,params={'part':'status'}).status_code==200
    assert seen[0].url.host=='www.googleapis.com'
    def broken(request):raise httpx.ConnectError('SECRET_SESSION https://url-containing-token',request=request)
    monkeypatch.setattr(p.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(broken),**kw))
    with pytest.raises(ValueError) as error:p.api_request('GET',channel=CHANNEL)
    assert 'SECRET_SESSION' not in str(error.value) and 'ACCESS_SECRET' not in str(error.value)

def test_known_generated_music_requires_disclosure(setup):
    cid=setup();db.execute("UPDATE settings SET value='false' WHERE key='publish_synthetic'")
    row=db.one('SELECT job_id,plan FROM render_tasks');plan=json.loads(row['plan']);plan['audio_replacement']={'mode':'music'}
    db.execute('UPDATE render_tasks SET plan=? WHERE job_id=?',(db.dump(plan),row['job_id']))
    with pytest.raises(ValueError,match='AI-музыка'):admit([cid])
    assert not db.rows('SELECT * FROM publications')

def test_cancel_before_any_media_can_be_requeued_without_new_record(setup):
    row=publication(admit([setup()]))
    p.cancel(row['id'])
    assert p.control(job(row),'retry') is None
    again=db.one('SELECT * FROM publications WHERE id=?',(row['id'],))
    assert again['state']=='Queued' and again['publish_at']>time.time()+590
    p.cancel(row['id'])
    auth.write(p.session_name(row['id']),{'attempted':True})
    with pytest.raises(ValueError,match='передавались'):p.control(job(row),'retry')
