import os
import base64
import json
import time
import httpx
import pytest
from backend import db,config
from backend import integrations as ai
from backend.schemas import CandidateList,AnalyzeOptions
from tests.test_core import candidate

@pytest.fixture
def integration(isolated_db,tmp_path,monkeypatch):
    monkeypatch.setattr(ai,'secret',lambda provider:'unit-test-credential')
    monkeypatch.setattr(ai,'DATA',tmp_path)
    (tmp_path/'ai-cache').mkdir()
    for key,value in {'cloud_enabled':True,'openai_model':'test-model','openai_budget_usd':0}.items():
        db.execute('UPDATE settings SET value=? WHERE key=?',(db.dump(value),key))
    return tmp_path

def response(data,status='completed'):
    return {'status':status,'output':[{'type':'message','content':[{'type':'output_text','text':db.dump(data)}]}],
            'usage':{'input_tokens':200,'output_tokens':100}}

def test_openai_structured_contract_cache_and_usage(integration,monkeypatch):
    calls=[]
    def remote(provider,method,path,payload=None):
        calls.append((provider,method,path,payload))
        return response(CandidateList(candidates=[candidate()]).model_dump())
    monkeypatch.setattr(ai,'remote',remote)
    client=ai.OpenAIClient(db.settings())
    first=client.request([{'type':'input_text','text':'fixture'}],'instructions')
    second=client.request([{'type':'input_text','text':'fixture'}],'instructions')
    assert len(calls)==1 and first==second
    payload=calls[0][3]
    assert calls[0][2]=='/responses' and payload['store'] is False
    schema=payload['text']['format']['schema']
    assert schema['$defs']['Candidate']['required']==list(schema['$defs']['Candidate']['properties'])
    assert schema['$defs']['Candidate']['additionalProperties'] is False
    usage=ai.usage_summary('openai')
    assert usage['requests']==1 and usage['input_tokens']==200 and usage['output_tokens']==100

@pytest.mark.parametrize('setting,value,message',[('cloud_enabled',False,'облач'),('openai_budget_usd',1,'тариф'),('openai_request_limit',1,'лимит')])
def test_openai_preflight_no_paid_request(integration,monkeypatch,setting,value,message):
    db.execute('UPDATE settings SET value=? WHERE key=?',(db.dump(value),setting))
    if setting=='openai_request_limit':
        db.execute('INSERT INTO usage VALUES(?,?,?,?,?,?)',(db.uid(),'openai:test',1,1,None,time.time()))
    monkeypatch.setattr(ai,'remote',lambda *a,**k:pytest.fail('Unexpected API call'))
    with pytest.raises(ValueError,match=message): ai.OpenAIClient(db.settings()).request([],'test')

def test_openai_budget_counts_input_then_blocks_generation(integration,monkeypatch):
    for key,value in {'openai_budget_usd':.001,'openai_input_price_per_million':100,'openai_output_price_per_million':100}.items():
        db.execute('UPDATE settings SET value=? WHERE key=?',(db.dump(value),key))
    calls=[]
    def remote(provider,method,path,payload=None):
        calls.append(path)
        assert path=='/responses/input_tokens'
        return {'input_tokens':1000}
    monkeypatch.setattr(ai,'remote',remote)
    with pytest.raises(ValueError,match='бюджет'): ai.OpenAIClient(db.settings()).request([],'test')
    assert calls==['/responses/input_tokens'] and ai.usage_summary('openai')['requests']==0

def test_openai_failed_generation_is_counted_and_not_retried(integration,monkeypatch):
    calls=[]
    def remote(*args):
        calls.append(args)
        raise ValueError('HTTP 429 insufficient_quota')
    monkeypatch.setattr(ai,'remote',remote)
    with pytest.raises(ValueError,match='429'): ai.OpenAIClient(db.settings()).request([],'test')
    assert len(calls)==1 and ai.usage_summary('openai')['requests']==1
    assert not list((integration/'ai-cache').glob('*.json'))

def test_openai_successful_budget_uses_actual_reported_tokens(integration,monkeypatch):
    for key,value in {'openai_budget_usd':2,'openai_input_price_per_million':1,'openai_output_price_per_million':2}.items():
        db.execute('UPDATE settings SET value=? WHERE key=?',(db.dump(value),key))
    calls=[]
    def remote(provider,method,path,payload=None):
        calls.append(path)
        if path=='/responses/input_tokens': return {'input_tokens':100}
        return response(CandidateList(candidates=[]).model_dump())
    monkeypatch.setattr(ai,'remote',remote)
    ai.OpenAIClient(db.settings()).request([],'test')
    assert calls==['/responses/input_tokens','/responses']
    assert ai.usage_summary('openai')['estimated_cost']==pytest.approx(.0004)

def test_pause_keeps_paid_result_for_resume(integration,monkeypatch):
    from backend.media import Interrupted
    paused=False
    calls=[]
    def check(job):
        if paused: raise Interrupted('Paused')
    def remote(*args):
        nonlocal paused
        calls.append(args);paused=True
        return response(CandidateList(candidates=[]).model_dump())
    monkeypatch.setattr(ai,'check_job',check)
    monkeypatch.setattr(ai,'remote',remote)
    client=ai.OpenAIClient(db.settings(),'fixture-job')
    with pytest.raises(Interrupted): client.request([],'test')
    paused=False
    assert client.request([],'test').candidates==[] and len(calls)==1

def test_openai_incomplete_response_records_usage_without_cache(integration,monkeypatch):
    monkeypatch.setattr(ai,'remote',lambda *a:response({},'incomplete'))
    with pytest.raises(ValueError,match='не завершил'): ai.OpenAIClient(db.settings()).request([],'test')
    assert ai.usage_summary('openai')['output_tokens']==100
    assert not list((integration/'ai-cache').glob('*.json'))

def test_openai_rejects_edited_excerpt_outside_bounds(integration,monkeypatch,source,transcript):
    source={**source,'path':'fixture.mp4'}
    first=candidate(source_video_id=source['id'])
    bad=first.model_copy(update={'end_seconds':50})
    results=iter([CandidateList(candidates=[first]),CandidateList(candidates=[bad])])
    monkeypatch.setattr(ai.OpenAIClient,'request',lambda *a,**k:next(results))
    monkeypatch.setattr(ai,'frames',lambda *a,**k:([],[5]))
    with pytest.raises(ValueError,match='пределами'): ai.OpenAIProvider(db.settings(),None).analyze(source,transcript,AnalyzeOptions(),[],None)

def test_author_pilot_rejects_unseen_evidence(integration,monkeypatch,source):
    cid=db.uid()
    db.execute('INSERT INTO clips(id,source_id,title,start,end,score,provider,data,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(cid,source['id'],'Pilot',0,30,50,'local','{}',time.time()))
    monkeypatch.setattr(ai,'frames',lambda *a,**k:([],[5,10,15]))
    monkeypatch.setattr(ai.OpenAIClient,'request',lambda *a,**k:ai.PilotScript(title='Test',observations=[{'timestamp':25,'visible_detail':'A visible detail','interpretation':''}],script='An original analytical commentary draft for this test.',warnings=[]))
    with pytest.raises(ValueError,match='не отправлялся'): ai.author_pilot(cid)
    assert db.one('SELECT id FROM clips WHERE id=?',(cid,))

def test_settings_keys_are_private_and_validation_does_not_echo(client,tmp_path,monkeypatch):
    monkeypatch.setattr(config,'ROOT',tmp_path)
    monkeypatch.setattr(config,'SECRET_PATH',tmp_path/'.secrets/gemini.key')
    marker='unit-test-not-a-real-key'
    r=client.put('/api/settings',json={'values':{'provider':'openai','elevenlabs_voice_id':'Voice123'},'openai_api_key':marker,'elevenlabs_api_key':marker})
    assert r.status_code==200 and marker not in r.text
    assert r.json()['openai_key_connected'] and r.json()['elevenlabs_key_connected']
    assert os.name=='nt' or (tmp_path/'.secrets/openai.key').stat().st_mode&0o777==0o600
    assert os.name=='nt' or (tmp_path/'.secrets').stat().st_mode&0o777==0o700
    bad=marker*30
    r=client.put('/api/settings',json={'values':{},'openai_api_key':bad})
    assert r.status_code==422 and bad not in r.text
    assert client.put('/api/settings',json={'values':{'elevenlabs_voice_id':'../../outside'}}).status_code==400
    assert client.put('/api/settings',json={'values':{'openai_request_limit':1.5}}).status_code==400
    assert client.put('/api/settings',json={'values':{},'openai_api_key':''}).json()['openai_key_connected'] is False

def test_generation_requires_explicit_consent(client,monkeypatch):
    monkeypatch.setattr(ai,'remote',lambda *a,**k:pytest.fail('No consent'))
    for body in ({'text':'hello'},{'text':'hello','consent':False}):
        assert client.post('/api/integrations/voice-preview',json=body).status_code==422
    assert client.post('/api/integrations/author-pilot',json={'clip_id':'a'*32,'consent':False}).status_code==422
    assert client.post('/api/integrations/voice-preview',json={'text':'x'*1201,'consent':True}).status_code==422
    assert client.get('/api/integrations/voice/not-a-hash').status_code==404

def test_http_transport_uses_only_provider_host_and_redacts_errors(integration,monkeypatch):
    original=httpx.Client
    def handler(request):
        assert request.url.host=='api.openai.com'
        assert request.headers['authorization']=='Bearer unit-test-credential'
        return httpx.Response(401,json={'error':{'message':'Invalid key'}})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    with pytest.raises(ValueError,match='401'): ai.remote('openai','GET','/models')

def test_real_voice_file_validation_and_cache(integration,monkeypatch):
    audio=integration/'fixture.mp3'
    from backend.media import run
    run([config.FFMPEG,'-v','error','-f','lavfi','-i','sine=frequency=440:duration=1','-c:a','libmp3lame',audio],timeout=15)
    calls=[]
    def remote(*args):
        calls.append(args)
        return {'audio_base64':base64.b64encode(audio.read_bytes()).decode(),'alignment':{'characters':['H','i'],'character_start_times_seconds':[0,.4],'character_end_times_seconds':[.3,.8]}}
    monkeypatch.setattr(ai,'remote',remote)
    settings={**db.settings(),'elevenlabs_voice_id':'testvoice'}
    first=ai.voice_preview('Hi',settings)
    second=ai.voice_preview('Hi',settings)
    assert first['duration']>0 and second['cached'] and len(calls)==1
    assert first['url'].startswith('/api/integrations/voice/')
    assert ai.usage_summary('elevenlabs')['requests']==1

def test_invalid_voice_alignment_never_produces_audio(integration,monkeypatch):
    monkeypatch.setattr(ai,'remote',lambda *a:{'audio_base64':base64.b64encode(b'x'*200).decode(),'alignment':{}})
    with pytest.raises(ValueError,match='разметку'): ai.voice_preview('Test',{**db.settings(),'elevenlabs_voice_id':'testvoice'})
    assert not list(integration.rglob('*.mp3'))

def test_voice_read_permissions_are_optional_for_generation(integration,monkeypatch):
    def remote(provider,method,path,payload=None):
        permission='voices_read' if '/voices/' in path else 'models_read'
        raise ValueError('elevenlabs HTTP 401: The API key you used is missing the permission '+permission+' to execute this operation.')
    monkeypatch.setattr(ai,'remote',remote)
    result=ai.test_voice({**db.settings(),'elevenlabs_voice_id':'testvoice'})
    assert result['ok'] and not result['voice_verified']
    assert result['limited_permissions']==['voices_read','models_read']
    assert result['models']==[]

def test_pilot_is_persisted_and_restored_with_existing_voice(integration,monkeypatch,source):
    cid=db.uid()
    db.execute('INSERT INTO clips(id,source_id,title,start,end,score,provider,data,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(cid,source['id'],'Pilot',0,30,50,'local','{}',time.time()))
    monkeypatch.setattr(ai,'frames',lambda *a,**k:([],[5,10,15]))
    monkeypatch.setattr(ai.OpenAIClient,'request',lambda *a,**k:ai.PilotScript(title='Test',observations=[{'timestamp':5,'visible_detail':'Visible fixture','interpretation':''}],script='An original analytical commentary draft for this test.',warnings=[]))
    draft=ai.author_pilot(cid)
    assert ai.latest_pilot()['script']==draft['script']
    directory=integration/'previews'/'voices';directory.mkdir(parents=True)
    (directory/('a'*64+'.mp3')).write_bytes(b'fixture')
    ai.link_pilot_voice(draft['script'],{'url':'/api/integrations/voice/'+'a'*64,'duration':1,'voice_id':'test','model':'test'})
    assert ai.latest_pilot()['voice']['duration']==1
    (directory/('a'*64+'.mp3')).unlink()
    assert 'voice' not in ai.latest_pilot()
    db.execute('DELETE FROM clips WHERE id=?',(cid,))
    assert ai.latest_pilot() is None
