import json
import threading
import time
import importlib
import numpy as np
import pytest
import httpx
from backend import db
from backend.config import FFMPEG
from backend.media import run
from backend.schemas import EditPlan,AudioReplacement
from backend import audio_replacement as audio
REAL_GENERATE_MUSIC=audio.generate_music

@pytest.fixture
def sound_fixture(source,tmp_path,monkeypatch):
    renderer=importlib.import_module('backend.render')
    for folder in ('sources','renders','temp','projects','audio-replacements','previews/voices'):(tmp_path/folder).mkdir(parents=True,exist_ok=True)
    original=tmp_path/'sources/source.mp4'
    run([FFMPEG,'-v','error','-y','-f','lavfi','-i','color=c=0x222222:size=320x180:rate=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','4','-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',original])
    music=tmp_path/'music.mp3';voice=tmp_path/'previews/voices/fixture.mp3'
    for path,frequency,duration in [(music,880,4),(voice,660,1)]:
        run([FFMPEG,'-v','error','-y','-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=48000','-t',duration,'-c:a','libmp3lame',path])
    monkeypatch.setattr(audio,'DATA',tmp_path)
    monkeypatch.setattr(audio,'secret',lambda p:'fixture-not-a-real-key')
    monkeypatch.setattr(renderer,'DATA',tmp_path)
    monkeypatch.setattr(renderer,'safe_path',lambda relative:tmp_path/relative)
    calls=[]
    def generate(*args):
        calls.append('music')
        return music,{'provider':'fixture','terms_url':audio.MUSIC_TERMS}
    monkeypatch.setattr(audio,'generate_music',generate)
    monkeypatch.setattr(audio,'voice_preview',lambda *a:{'url':'/api/integrations/voice/fixture','duration':1,'alignment':{'characters':list('One two'),'character_start_times_seconds':[.05,.1,.15,.2,.3,.4,.5],'character_end_times_seconds':[.1,.15,.2,.25,.4,.5,.6]}})
    db.execute('UPDATE sources SET path=?,duration=4,has_audio=1 WHERE id=?',('sources/source.mp4',source['id']))
    source=db.one('SELECT * FROM sources WHERE id=?',(source['id'],))
    transcript={'segments':[{'words':[{'word':'One','start':.2,'end':.5},{'word':'two','start':.6,'end':.9}]}]}
    settings={**db.settings(),'elevenlabs_voice_id':'fixture-voice'}
    return renderer,source,transcript,settings,tmp_path,calls,music

@pytest.mark.parametrize('mode',['music','music_voice'])
def test_real_mp4_excludes_original_sound_and_mixes_replacement(sound_fixture,mode):
    renderer,source,transcript,settings,root,calls,music=sound_fixture
    jid=db.uid();now=time.time()
    db.execute('INSERT INTO jobs(id,source_id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(jid,source['id'],'render','Running','{}',now,now))
    plan=EditPlan(segments=[{'start':0,'end':3}],encoder='software',aspect='16:9',crop_mode='center',normalize_audio=False,
                  audio_replacement=AudioReplacement(mode=mode,consent=True))
    plan.subtitles.enabled=mode=='music_voice'
    output=root/'renders/replaced.mp4'
    qc=renderer.render(source,transcript,plan.model_dump(),jid,output,threading.Semaphore(1),settings)
    assert qc['passed'] and qc['metadata_clean'] and qc['full_decode'] and qc['has_audio']
    assert qc['audio_replacement']['original_audio_included'] is False
    assert calls==['music']
    samples=root/'samples.f32'
    run([FFMPEG,'-v','error','-y','-i',output,'-vn','-ac','1','-ar','48000','-f','f32le',samples])
    signal=np.fromfile(samples,dtype=np.float32)
    spectrum=np.abs(np.fft.rfft(signal));frequencies=np.fft.rfftfreq(len(signal),1/48000)
    band=lambda frequency:float(spectrum[np.abs(frequencies-frequency)<3].max())
    assert band(880)>band(440)*30  # Original 440Hz is absent; replacement 880Hz is audible.
    if mode=='music_voice':
        assert band(660)>band(440)*20
        assert qc['word_count']==2 and 'One' in output.with_suffix('.srt').read_text()

def test_alignment_tracks_new_speech_not_original_timestamps():
    words=audio.alignment_words({'characters':list('Hi there'),'character_start_times_seconds':[i*.1 for i in range(8)],'character_end_times_seconds':[(i+1)*.1 for i in range(8)]},offset=2,rate=1.25)
    assert words[0]['word']=='Hi' and words[0]['start']==2
    assert words[1]['start']==pytest.approx(2.24)

def test_no_consent_fails_before_a_paid_request(sound_fixture,monkeypatch):
    _,source,transcript,settings,root,calls,_=sound_fixture
    plan=EditPlan(segments=[{'start':0,'end':3}],audio_replacement=AudioReplacement(mode='music',consent=False))
    with pytest.raises(ValueError,match='Подтвердите'): audio.preflight([('clip',plan,transcript,3)],settings)
    assert not calls and audio.music_stats()['requests']==0

def test_music_budget_fails_before_generation(sound_fixture):
    _,source,transcript,settings,root,calls,_=sound_fixture
    plan=EditPlan(segments=[{'start':0,'end':3}],audio_replacement=AudioReplacement(mode='music',consent=True))
    with pytest.raises(ValueError,match='секунд'): audio.preflight([('clip',plan,transcript,3)],{**settings,'music_seconds_limit':2})
    assert not calls

def test_voice_requires_real_words_before_music_generation(sound_fixture):
    _,source,transcript,settings,root,calls,_=sound_fixture
    plan=EditPlan(segments=[{'start':0,'end':3}],audio_replacement=AudioReplacement(mode='music_voice',consent=True))
    with pytest.raises(ValueError,match='распознанные слова'): audio.preflight([('clip',plan,{'segments':[]},3)],settings)
    assert not calls

def test_music_api_contract_cache_and_job_cancellation(sound_fixture,monkeypatch):
    _,source,transcript,settings,root,calls,music=sound_fixture
    monkeypatch.setattr(audio,'generate_music',REAL_GENERATE_MUSIC)
    # Test the real transport/caching function with an authored MP3 response.
    monkeypatch.setattr(audio,'DATA',root);monkeypatch.setattr(audio,'secret',lambda p:'fixture-credential')
    requested=[];original=httpx.Client
    def handler(request):
        requested.append(request)
        assert request.url.host=='api.elevenlabs.io' and request.url.path=='/v1/music'
        payload=json.loads(request.content)
        assert payload['force_instrumental'] is True and payload['music_length_ms']==3000
        assert 'audio' not in payload and 'audio_reference' not in payload
        return httpx.Response(200,content=music.read_bytes(),headers={'song-id':'fixture-song'})
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    plan=EditPlan(segments=[{'start':0,'end':3}],audio_replacement=AudioReplacement(mode='music',consent=True))
    first,record=audio.generate_music('clip',plan,settings,3,None)
    second,_=audio.generate_music('clip',plan,settings,3,None)
    assert first==second and len(requested)==1 and record['song_id']=='fixture-song'
    assert audio.music_stats()['requests']==1

def test_fifty_replacement_plans_queue_atomically(client,source,tmp_path,monkeypatch):
    import backend.library as library
    root=tmp_path/'media';(root/'sources').mkdir(parents=True);(root/'sources/original.mp4').write_bytes(b'preflight fixture')
    monkeypatch.setattr(library,'safe_path',lambda relative:root/relative)
    monkeypatch.setattr(audio,'DATA',root);monkeypatch.setattr(audio,'secret',lambda p:'fixture')
    db.execute('UPDATE sources SET path=? WHERE id=?',('sources/original.mp4',source['id']))
    clips=[client.post(f'/api/sources/{source["id"]}/manual-clip',json={'start':i,'end':i+5}).json() for i in range(50)]
    result=client.post('/api/clips/batch/render',json={'ids':[c['id'] for c in clips],'audio_replacement':{'mode':'music','consent':True},'download_zip':True})
    assert result.status_code==200,result.text
    assert result.json()['clips']==50 and result.json()['export_job_id']
    for job in db.rows("SELECT payload FROM jobs WHERE kind='render'"):
        payload=json.loads(job['payload'])
        assert payload['plan']['audio_replacement']['mode']=='music'
        assert payload['audio_settings']['music_model']=='music_v2_5'
    assert db.one("SELECT COUNT(*) n FROM jobs WHERE kind='render'")['n']==50

def test_insufficient_batch_music_limit_does_not_partially_queue(client,source,tmp_path,monkeypatch):
    import backend.library as library
    root=tmp_path/'media';(root/'sources').mkdir(parents=True);(root/'sources/original.mp4').write_bytes(b'fixture')
    monkeypatch.setattr(library,'safe_path',lambda relative:root/relative)
    monkeypatch.setattr(audio,'DATA',root);monkeypatch.setattr(audio,'secret',lambda p:'fixture')
    db.execute('UPDATE sources SET path=? WHERE id=?',('sources/original.mp4',source['id']))
    db.execute("UPDATE settings SET value='1' WHERE key='music_request_limit'")
    clips=[client.post(f'/api/sources/{source["id"]}/manual-clip',json={'start':i,'end':i+5}).json() for i in range(2)]
    result=client.post('/api/clips/batch/render',json={'ids':[c['id'] for c in clips],'audio_replacement':{'mode':'music','consent':True}})
    assert result.status_code==400 and 'лимита' in result.json()['detail']
    assert db.one('SELECT COUNT(*) n FROM jobs')['n']==0 and db.one('SELECT COUNT(*) n FROM projects')['n']==0

def test_second_batch_respects_already_queued_music(sound_fixture):
    _,source,transcript,settings,root,calls,_=sound_fixture
    cid=db.uid();now=time.time()
    db.execute('INSERT INTO clips(id,source_id,title,start,end,score,provider,data,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(cid,source['id'],'Queued',0,3,0,'manual','{}',now))
    plan=EditPlan(segments=[{'start':0,'end':3}],audio_replacement=AudioReplacement(mode='music',consent=True))
    from workers.queue import enqueue
    enqueue('render',source['id'],{'plan':plan.model_dump(),'revision':1},cid)
    with pytest.raises(ValueError,match='лимита'):
        audio.preflight([('another-clip',plan,transcript,3)],{**settings,'music_request_limit':1})
    assert not calls

def test_failed_replacement_never_exports_original_sound(sound_fixture,monkeypatch):
    renderer,source,transcript,settings,root,calls,music=sound_fixture
    monkeypatch.setattr(audio,'generate_music',lambda *a:(_ for _ in ()).throw(ValueError('Music unavailable')))
    jid=db.uid();now=time.time()
    db.execute('INSERT INTO jobs(id,source_id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(jid,source['id'],'render','Running','{}',now,now))
    plan=EditPlan(segments=[{'start':0,'end':3}],audio_replacement=AudioReplacement(mode='music',consent=True))
    output=root/'renders/must-not-exist.mp4'
    with pytest.raises(ValueError,match='Music unavailable'):
        renderer.render(source,transcript,plan.model_dump(),jid,output,threading.Semaphore(1),settings)
    assert not output.exists()
