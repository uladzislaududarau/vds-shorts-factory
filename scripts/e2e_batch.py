"""Persistent queue, real Russian MLX, restart, style-only rerender and batch export."""
import hashlib
import json
import subprocess
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
client=httpx.Client(base_url='http://127.0.0.1:8765/api',headers={'X-Factory-Client':'local'},timeout=120)
def request(method,path,**kw):
    r=client.request(method,path,**kw)
    if not r.is_success: raise RuntimeError(f'{r.status_code}: {r.text}')
    return r.json()
def wait(jid,timeout=1200):
    last='';began=time.monotonic()
    while time.monotonic()-began<timeout:
        row=next(j for j in request('GET','/jobs') if j['id']==jid)
        state=row['status']+' / '+row['stage']
        if state!=last:print(state,flush=True);last=state
        if row['status']=='Completed':return row
        if row['status'] in ('Failed','Cancelled'):raise RuntimeError(row.get('error') or state)
        time.sleep(1)
    raise TimeoutError(jid)

def main():
    baseline=json.loads((ROOT/'docs/e2e-result.json').read_text())
    source=ROOT/'data/projects/e2e-authored/authored-russian-lesson.mp4'
    with source.open('rb') as file:
        imported=request('POST','/import/files',files={'files':(source.name,file,'video/mp4')},data={'rights_status':'owned','license':'Original Russian QA script; synthetic macOS Milena voice; original title graphic'})[0]
    if imported.get('error'):raise RuntimeError(imported['error'])
    ru=imported['source']['id']
    options={'min_duration':12,'max_duration':30,'target_count':3,'score_threshold':20,'profile':'Educational','cloud_consent':False}
    en_job=request('POST',f'/sources/{baseline["source_id"]}/analyze',json={**options,'language':'en'})['job_id']
    ru_job=request('POST',f'/sources/{ru}/analyze',json={**options,'language':'ru'})['job_id']
    request('POST',f'/jobs/{ru_job}/pause',json={})
    wait(en_job)
    print('Restarting the owned server with a paused queued source.',flush=True)
    subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/launcher.py'),'stop'],check=True,cwd=ROOT)
    subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/launcher.py'),'start','--no-open'],check=True,cwd=ROOT)
    assert next(j for j in request('GET','/jobs') if j['id']==ru_job)['status']=='Paused'
    assert request('GET',f'/clips/{baseline["clip_id"]}')['media_url']
    request('POST',f'/jobs/{ru_job}/resume',json={})
    wait(ru_job)
    russian=request('GET',f'/sources/{ru}')
    assert russian['transcript']['language']=='ru'
    assert russian['clips']
    chosen=russian['clips'][0]
    render_job=request('POST',f'/clips/{chosen["id"]}/render',json={})['job_id']
    wait(render_job)
    before=request('GET',f'/clips/{baseline["clip_id"]}')
    # A real editorial change without touching Whisper, scenes, or the analysis.
    old_render=client.get(before['media_url'].removeprefix('/api')).content
    plan=before['plan'];plan['subtitles']['preset']='High Contrast';plan['subtitles']['active_color']='#FFFF00'
    plan['subtitles']['animation']='pop';plan['volume']=.9
    source_transcript_before=request('GET',f'/sources/{baseline["source_id"]}')['transcript']
    request('PUT',f'/clips/{baseline["clip_id"]}/plan',json=plan)
    edited=request('POST',f'/clips/{baseline["clip_id"]}/render',json={})['job_id']
    wait(edited)
    after=request('GET',f'/clips/{baseline["clip_id"]}')
    new_render=client.get(after['media_url'].removeprefix('/api')).content
    assert hashlib.sha256(old_render).hexdigest()!=hashlib.sha256(new_render).hexdigest()
    assert after['revision']==before['revision']+1 and not after['stale']
    assert source_transcript_before==request('GET',f'/sources/{baseline["source_id"]}')['transcript']
    exported=request('POST','/exports',json={'ids':[baseline['clip_id'],chosen['id']]})
    import io,zipfile
    archive=client.get(exported['url'].removeprefix('/api'))
    archive.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert len([n for n in z.namelist() if n.endswith('.mp4')])==2
        assert z.testzip() is None
    report={'sources':[baseline['source_id'],ru],'jobs':[en_job,ru_job,render_job,edited],
            'russian_words':sum(len(s.get('words',[])) for s in russian['transcript']['segments']),
            'russian_candidates':len(russian['clips']),'russian_clip_id':chosen['id'],
            'paused_queue_survived_restart':True,'render_survived_restart':True,'style_rerender_changed_bytes':True,
            'transcript_preserved':True,'edited_revision':after['revision'],'export':exported,'gemini_tested':False}
    (ROOT/'docs/e2e-batch-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
