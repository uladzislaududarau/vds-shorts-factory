"""Real native test: authored speech/video → import → MLX → candidates → MP4 → ZIP.

Requires the running app at 127.0.0.1:8765. No Gemini calls or third-party media.
"""
import json
import subprocess
import sys
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.config import DATA,FFMPEG
from backend.media import probe,run

TEXT='''Why do people stop watching a video after the first few seconds? The problem is often the beginning. A long introduction makes the viewer wait for the useful part. Here is a simple editing technique. Listen to the whole answer before making your first cut. Find a clear question, then keep the explanation and the conclusion together. This way the short video still makes sense on its own. Never remove a word that changes what the speaker means. Always watch the result before exporting it.
There is another mistake that is easy to fix. Editors sometimes place captions too close to the bottom of the frame. On a phone, application controls can cover those words. Move your captions into a safe area and keep each line short. Then check the sound, the first sentence and the final frame. The result should be a complete idea that someone can understand without the original interview. That is more useful than cutting a recording into identical thirty second pieces.'''

def main():
    folder=DATA/'projects/e2e-authored'
    folder.mkdir(parents=True,exist_ok=True)
    speech=folder/'speech.txt'
    speech.write_text(TEXT)
    audio=folder/'speech.aiff'
    if not audio.exists():
        subprocess.run(['say','-v','Samantha','-r','165','-f',str(speech),'-o',str(audio)],check=True)
    source=folder/'authored-editing-lesson.mp4'
    if not source.exists():
        from PIL import Image,ImageDraw,ImageFont
        im=Image.new('RGB',(960,540),'#111111')
        d=ImageDraw.Draw(im)
        font='/System/Library/Fonts/Supplemental/Arial.ttf'
        d.text((60,50),'SHORTS FACTORY',font=ImageFont.truetype(font,24),fill='#BBBBBB')
        d.text((60,180),'A complete idea.',font=ImageFont.truetype(font,68),fill='#FFFFFF')
        d.text((60,280),'Question  /  Explanation  /  Conclusion',font=ImageFont.truetype(font,28),fill='#C6F24E')
        d.text((60,450),'Authored local QA material · synthetic macOS voice',font=ImageFont.truetype(font,18),fill='#BBBBBB')
        image=folder/'title.png';im.save(image)
        run([FFMPEG,'-hide_banner','-loglevel','error','-y','-loop','1','-i',image,'-i',audio,
             '-vf','scale=960:540,fps=30','-c:v','libx264','-preset','veryfast','-tune','stillimage','-crf','24',
             '-c:a','aac','-b:a','128k','-pix_fmt','yuv420p','-shortest','-movflags','+faststart',source])
    client=httpx.Client(base_url='http://127.0.0.1:8765/api',headers={'X-Factory-Client':'local'},timeout=120)
    def req(method,path,**kw):
        r=client.request(method,path,**kw);r.raise_for_status();return r.json()
    with source.open('rb') as file:
        imported=req('POST','/import/files',files={'files':(source.name,file,'video/mp4')},data={'rights_status':'owned','license':'Original script and graphic authored for local QA; macOS synthetic voice'})[0]
    if imported.get('error'): raise RuntimeError(imported['error'])
    sid=imported['source']['id']
    print('Imported source',sid,flush=True)
    analysis=req('POST',f'/sources/{sid}/analyze',json={'cloud_consent':False,'min_duration':12,'max_duration':30,'target_count':3,'score_threshold':20,'language':'en','profile':'Educational'})
    def wait(jid,limit=2400):
        last=''
        began=time.monotonic()
        while time.monotonic()-began<limit:
            job=next(j for j in req('GET','/jobs') if j['id']==jid)
            stamp=job['status']+' / '+job['stage']
            if stamp!=last: print(stamp,flush=True);last=stamp
            if job['status']=='Completed': return job
            if job['status'] in ('Failed','Cancelled','Paused'): raise RuntimeError(job.get('error') or stamp)
            time.sleep(1)
        raise TimeoutError(jid)
    wait(analysis['job_id'])
    detail=req('GET',f'/sources/{sid}')
    assert detail['transcript'] and any(s.get('words') for s in detail['transcript']['segments'])
    assert detail['clips'],'No strong local candidates found in authored speech'
    chosen=detail['clips'][0]
    req('PATCH',f'/clips/{chosen["id"]}',json={'approved':True})
    rendered=req('POST',f'/clips/{chosen["id"]}/render',json={})
    wait(rendered['job_id'])
    clip=req('GET',f'/clips/{chosen["id"]}')
    assert clip['qc']['passed'] and clip['qc']['word_count']>0
    assert clip['qc']['width']==1080 and clip['qc']['height']==1920
    assert req('GET','/dashboard')['rendered']>0
    result=req('POST','/exports',json={'ids':[chosen['id']]})
    report={'source_id':sid,'clip_id':chosen['id'],'source_duration':detail['duration'],
            'transcribed_words':sum(len(s.get('words',[])) for s in detail['transcript']['segments']),
            'candidates':len(detail['clips']),'qc':clip['qc'],'export':result,'gemini_tested':False}
    (ROOT/'docs/e2e-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__': main()
