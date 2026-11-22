import asyncio
import csv
import hashlib
import io
import json
import mimetypes
import math
import re
import os
import platform
import shutil
import sys
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from . import db
from .config import ROOT, DATA, DEFAULTS, SECRET_PATH, safe_path, secret, redact, write_secret
from .media import probe, thumbnail, check_space, check_job,run, run_youtube, capabilities, validate_youtube
from .schemas import AnalyzeOptions, EditPlan, Batch, BatchRender,ApprovalBatch,ExportBatch,SettingsUpdate, URLImport, YouTubeDownload, YouTubeConsent,VoicePreview,AuthorPilot,PublishBatch
from . import youtube_auth, publishing_auth
from workers.queue import Farm, enqueue, default_plan

farm = Farm()
EXTENSIONS = {'.mp4','.mov','.mkv','.webm'}

@asynccontextmanager
async def lifespan(app):
    db.init()
    farm.start()
    yield
    farm.stop()

app = FastAPI(title='VDS Shorts Factory',version='1.0.0',lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def validation_error(request,error):
    # Pydantic's default error includes raw input, which could be an API key.
    return JSONResponse({'detail':[{'loc':list(item['loc']),'msg':item['msg'],'type':item['type']} for item in error.errors()]},status_code=422)

@app.middleware('http')
async def local_security(request: Request, call_next):
    host = request.headers.get('host','').split(':')[0]
    if host not in ('127.0.0.1','localhost','testserver'):
        return JSONResponse({'detail':'Only localhost hosts are accepted'},status_code=403)
    origin = request.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173'):
        return JSONResponse({'detail':'Cross-origin request rejected'},status_code=403)
    if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('x-factory-client') != 'local':
        return JSONResponse({'detail':'Local client header required'},status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

@app.exception_handler(ValueError)
async def invalid(request, error):
    return JSONResponse({'detail':redact(str(error))},status_code=400)

@app.exception_handler(RuntimeError)
async def runtime_error(request, error):
    return JSONResponse({'detail':redact(str(error))},status_code=400)

def source_or_404(source_id):
    source = db.one('SELECT * FROM sources WHERE id=?',(source_id,))
    if not source:
        raise HTTPException(404,'Source not found')
    return source

def clip_or_404(clip_id):
    clip = db.one('SELECT * FROM clips WHERE id=?',(clip_id,))
    if not clip:
        raise HTTPException(404,'Clip not found')
    return clip

def source_json(source):
    source = dict(source)
    source['metadata'] = json.loads(source['metadata'])
    source['rights'] = db.one('SELECT status,license,origin,confirmed_at FROM rights_metadata WHERE source_id=?',(source['id'],))
    source['media_url'] = f'/api/sources/{source["id"]}/media' if source['path'] else None
    source['thumbnail_url'] = f'/api/sources/{source["id"]}/thumbnail' if source['thumbnail'] else None
    source['clip_count'] = db.one('SELECT COUNT(*) n FROM clips WHERE source_id=?',(source['id'],))['n']
    source.pop('path',None)
    return source

def clip_json(clip):
    clip = dict(clip)
    clip['data'] = json.loads(clip['data'])
    clip['media_url'] = f'/api/clips/{clip["id"]}/media' if clip['render_path'] else None
    poster=db.one('SELECT thumbnail FROM sources WHERE id=?',(clip['source_id'],))
    clip['poster_url']=f'/api/sources/{clip["source_id"]}/thumbnail' if poster and poster['thumbnail'] else None
    project = db.one('SELECT data FROM projects WHERE clip_id=?',(clip['id'],))
    clip['plan'] = json.loads(project['data']) if project else default_plan(clip).model_dump()
    latest = db.one('SELECT rt.qc FROM render_tasks rt JOIN jobs j ON j.id=rt.job_id WHERE j.clip_id=? AND rt.qc IS NOT NULL ORDER BY j.created_at DESC LIMIT 1',(clip['id'],))
    clip['qc'] = json.loads(latest['qc']) if latest else None
    clip['stale'] = bool(clip['render_path'] and clip['render_revision'] != clip['revision'])
    return clip

def managed_service():
    """True when the app's supervisor runs this server (launchd on macOS, launcher.py serve on Windows/Linux):
    only then can the UI restart or stop it."""
    return os.environ.get('XPC_SERVICE_NAME','').startswith('local.ai-shorts-factory.') or os.environ.get('VDS_SUPERVISED')=='1'

def graceful_exit():
    """uvicorn shuts down cleanly (running jobs are paused and resumable); the supervisor decides what happens next."""
    import signal,threading
    if sys.platform=='win32': threading.Timer(.4,lambda:signal.raise_signal(signal.SIGINT)).start()
    else: threading.Timer(.4,lambda:os.kill(os.getpid(),signal.SIGTERM)).start()

@app.get('/api/health')
def health():
    return {'ok':True,'version':'1.0.0','platform':platform.machine(),'os':sys.platform,'local_only':True,'managed':managed_service()}

@app.post('/api/system/restart')
def system_restart():
    if not managed_service(): raise ValueError('Перезапуск доступен, когда сервер запущен через приложение VDS Shorts Factory')
    graceful_exit()   # launchd KeepAlive / the Windows supervisor start a fresh process
    return {'restarting':True}

@app.post('/api/system/stop')
def system_stop():
    if not managed_service(): raise ValueError('Остановка доступна, когда сервер запущен через приложение VDS Shorts Factory')
    if sys.platform!='darwin':   # Windows / Linux: launcher.py serve supervises the server
        (ROOT/'.run').mkdir(exist_ok=True)
        (ROOT/'.run/stop-requested').touch()   # the supervisor exits instead of restarting
        graceful_exit()
        return {'stopping':True}
    import subprocess
    # `launchctl bootout` terminates this process, so it runs detached in its own session.
    subprocess.Popen([sys.executable,str(ROOT/'scripts/launcher.py'),'stop'],start_new_session=True,
                     stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return {'stopping':True}

@app.get('/api/dashboard')
def dashboard():
    disk = shutil.disk_usage(DATA)
    return {'sources':db.one("SELECT COUNT(*) n FROM sources WHERE status!='Archived'")['n'],
            'clips':db.one('SELECT COUNT(*) n FROM clips')['n'],
            'rendered':db.one('SELECT COUNT(*) n FROM clips WHERE render_path IS NOT NULL')['n'],
            'active':db.one("SELECT COUNT(*) n FROM jobs WHERE status IN ('Queued','Running')")['n'],
            'disk':{'free':disk.free,'total':disk.total},
            'usage':db.one('SELECT COUNT(*) requests,COALESCE(SUM(input_tokens),0) input_tokens,COALESCE(SUM(output_tokens),0) output_tokens,SUM(estimated_cost) estimated_cost FROM usage'),
            'key_connected':bool(secret(db.settings()['provider'])) if db.settings()['provider']!='local' else False,'provider':db.settings()['provider'],'cloud_enabled':db.settings()['cloud_enabled']}

@app.get('/api/doctor')
def doctor():
    result = capabilities()
    import importlib.metadata as metadata
    for package in ('fastapi','mlx','mlx-whisper','faster-whisper','scenedetect','opencv-python','google-genai','Pillow','yt-dlp','yt-dlp-ejs','pycryptodomex'):
        try: result[package] = metadata.version(package)
        except metadata.PackageNotFoundError: result[package] = None
    result.update({'python':sys.version.split()[0],'architecture':platform.machine(),'free_mb':shutil.disk_usage(DATA).free//1024**2,
                   'paths':{'sources':str(DATA/'sources'),'renders':str(DATA/'renders'),'exports':str(DATA/'exports')},
                   'subtitle_engine':'Pillow RGBA + FFmpeg overlay (Cyrillic font support)',
                   'limits':['Smart crop follows largest visible face; no speaker diarization or object detector.',
                             'Meaning, transcript accuracy and face safety require manual review.',
                             'Concurrency is deliberately fixed to one task per resource on this Mac.']})
    return result

@app.get('/api/sources')
def sources():
    return [source_json(s) for s in db.rows("SELECT * FROM sources WHERE status!='Archived' ORDER BY created_at DESC")]

@app.get('/api/sources/{source_id}')
def source_detail(source_id):
    source = source_json(source_or_404(source_id))
    transcript = db.one('SELECT * FROM transcripts WHERE source_id=?',(source_id,))
    source['transcript'] = json.loads(transcript['data']) if transcript else None
    source['clips'] = [clip_json(c) for c in db.rows('SELECT * FROM clips WHERE source_id=? ORDER BY score DESC',(source_id,))]
    scene_file = DATA/'projects'/f'{source_id}-scenes.json'
    source['scenes'] = json.loads(scene_file.read_text()) if scene_file.exists() else []
    return source

@app.get('/api/sources/{source_id}/media')
def source_media(source_id):
    source = source_or_404(source_id)
    if not source['path'] or not safe_path(source['path']).exists():
        raise HTTPException(404,'Local source not available')
    return FileResponse(safe_path(source['path']),media_type=mimetypes.guess_type(source['name'])[0] or 'video/mp4')

@app.get('/api/sources/{source_id}/thumbnail')
def source_thumbnail(source_id):
    source = source_or_404(source_id)
    if not source['thumbnail']:
        raise HTTPException(404,'Thumbnail unavailable')
    return FileResponse(safe_path(source['thumbnail']))

def validate_rights(status, license):
    if status not in ('owned','licensed','permission') or not license.strip() or len(license)>500:
        raise ValueError('Подтвердите права: собственный материал, лицензия или разрешение; укажите лицензию/основание')

def register_file(path, name, rights_status, license, origin='local upload', move=False):
    validate_rights(rights_status,license)
    ext = Path(name).suffix.lower()
    if ext not in EXTENSIONS:
        raise ValueError('Поддерживаются MP4, MOV, MKV, WebM')
    settings = db.settings()
    if path.stat().st_size > settings['max_upload_mb']*1024**2:
        raise ValueError('Файл превышает лимит загрузки')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024**2),b''): digest.update(chunk)
    sha = digest.hexdigest()
    old = db.one('SELECT * FROM sources WHERE sha256=?',(sha,))
    if old:
        db.execute("UPDATE sources SET status=CASE WHEN status='Archived' THEN 'Imported' ELSE status END WHERE id=?",(old['id'],))
        return {'source':source_json(source_or_404(old['id'])),'duplicate':True}
    info = probe(path)
    check_space(0 if move else path.stat().st_size,settings['min_free_mb'])
    sid = db.uid()
    dest = DATA/'sources'/f'{sid}{ext}'
    thumb = DATA/'thumbnails'/f'{sid}.jpg'
    try:
        if move: path.replace(dest)
        else: shutil.copy2(path,dest)
        thumbnail(dest,thumb,info['duration'])
        with db.WRITE_LOCK, db.connect() as c:
            c.execute('INSERT INTO sources(id,name,path,sha256,kind,duration,width,height,fps,size,has_audio,thumbnail,metadata,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (sid,Path(name).name,str(dest.relative_to(DATA)),sha,'local',info['duration'],info['width'],info['height'],info['fps'],dest.stat().st_size,info['has_audio'],str(thumb.relative_to(DATA)),db.dump(info['raw']),time.time()))
            c.execute('INSERT INTO rights_metadata VALUES(?,?,?,?,?)',(sid,rights_status,license,origin,time.time()))
    except BaseException:
        dest.unlink(missing_ok=True)
        thumb.unlink(missing_ok=True)
        raise
    return {'source':source_json(source_or_404(sid)),'duplicate':False}

@app.post('/api/import/files')
async def import_files(files: list[UploadFile] = File(...),rights_status: str = Form(...),license: str = Form(...)):
    validate_rights(rights_status,license)
    if len(files)>100: raise ValueError('Maximum 100 files per batch')
    result = []
    for uploaded in files:
        temp = DATA/'temp'/f'{db.uid()}{Path(uploaded.filename or "").suffix.lower()}'
        try:
            if temp.suffix not in EXTENSIONS:
                raise ValueError('Unsupported file extension')
            size = 0
            with temp.open('wb') as out:
                while chunk := await uploaded.read(1024**2):
                    size += len(chunk)
                    if size > db.settings()['max_upload_mb']*1024**2:
                        raise ValueError('Превышен лимит файла')
                    check_space(len(chunk),db.settings()['min_free_mb'])
                    out.write(chunk)
            result.append(await asyncio.to_thread(register_file,temp,uploaded.filename or 'video.mp4',rights_status,license,'local upload',True))
        except (ValueError,RuntimeError,OSError) as e:
            result.append({'filename':uploaded.filename,'error':redact(str(e))})
        finally:
            temp.unlink(missing_ok=True)
            await uploaded.close()
    return result

@app.post('/api/import/folder')
def import_folder(payload: dict):
    validate_rights(payload.get('rights_status',''),payload.get('license',''))
    path = Path(payload.get('path','')).expanduser()
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError('Укажите абсолютный путь к существующей папке')
    files = [p for p in path.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in EXTENSIONS]
    if not 1 <= len(files) <= 100:
        raise ValueError('В папке должно быть от 1 до 100 видео (без вложенных папок)')
    result = []
    for file in files:
        try: result.append(register_file(file,file.name,payload['rights_status'],payload['license'],str(path)))
        except Exception as e: result.append({'filename':file.name,'error':redact(str(e))})
    return result

@app.post('/api/import/url')
def import_url(payload: URLImport):
    with youtube_auth.cookie_snapshot(payload.use_account) as cookies:
        return import_url_with_session(payload,cookies)

def import_url_with_session(payload,cookie_file=None):
    url = validate_youtube(payload.url)
    old = db.one('SELECT * FROM sources WHERE url=?',(url,))
    if old and (not payload.download or old['path']):
        return {'source':source_json(old),'duplicate':True}
    # Authentication is supplied only through an explicitly connected local session.
    cmd = [sys.executable,'-m','yt_dlp','--ignore-config','--no-playlist','--no-geo-bypass','--no-warnings','--socket-timeout','20','--js-runtimes','node']
    if cookie_file:cmd+=['--cookies',str(cookie_file)]
    raw = json.loads(run_youtube(cmd+['--skip-download','--dump-single-json','--',url],timeout=90))
    if raw.get('is_live') or raw.get('has_drm'):
        raise ValueError('Live or DRM video is not supported')
    duration = float(raw.get('duration') or 0)
    if not 0 < duration < 86400: raise ValueError('No usable public video duration')
    if payload.download:
        check_space(int(duration*2_000_000),db.settings()['min_free_mb'])
        token = db.uid()
        template = str(DATA/'temp'/f'{token}.%(ext)s')
        try:
            run_youtube(cmd+['-f','bv*[height<=1080]+ba/b[height<=1080]','--merge-output-format','mp4','--max-filesize',f'{db.settings()["max_upload_mb"]}M','-o',template,'--',url],timeout=7200)
            files = list((DATA/'temp').glob(f'{token}.*'))
            file = next((p for p in files if p.suffix.lower() in EXTENSIONS),None)
            if not file: raise ValueError('Download adapter did not produce a usable source file')
            result = register_file(file,raw.get('title','YouTube')+file.suffix,payload.rights_status,payload.license,url,True)
            db.execute('UPDATE sources SET url=? WHERE id=?',(url,result['source']['id']))
            if old and not old['path']:
                local = source_or_404(result['source']['id'])
                if abs(local['duration']-old['duration'])>2:
                    raise ValueError('Скачанный файл отличается по длительности: выполните анализ нового локального источника')
                # Attach the authorized local media to the URL record so its approved
                # candidates keep their identities and become editable/renderable.
                db.execute('UPDATE sources SET path=?,width=?,height=?,fps=?,size=?,has_audio=?,thumbnail=?,metadata=?,kind=? WHERE id=?',
                           (local['path'],local['width'],local['height'],local['fps'],local['size'],local['has_audio'],local['thumbnail'],local['metadata'],'local',old['id']))
                if not result['duplicate']:
                    db.execute("UPDATE sources SET status='Archived' WHERE id=?",(local['id'],))
                return {'source':source_json(source_or_404(old['id'])),'duplicate':False}
            return result
        finally:
            for file in (DATA/'temp').glob(f'{token}.*'): file.unlink(missing_ok=True)
    sid = db.uid()
    with db.WRITE_LOCK, db.connect() as c:
        c.execute('INSERT INTO sources(id,name,url,kind,duration,metadata,created_at) VALUES(?,?,?,?,?,?,?)',
                  (sid,raw.get('title','YouTube video'),url,'youtube',duration,db.dump({'license':raw.get('license'),'uploader':raw.get('uploader')}),time.time()))
        c.execute('INSERT INTO rights_metadata VALUES(?,?,?,?,?)',(sid,payload.rights_status,payload.license,url,time.time()))
    return {'source':source_json(source_or_404(sid)),'duplicate':False}

@app.get('/api/youtube/session')
def youtube_session():
    return youtube_auth.status()

@app.post('/api/youtube/login')
def youtube_login():
    return youtube_auth.open_login()

@app.post('/api/youtube/connect')
def youtube_connect(payload:YouTubeConsent):
    return youtube_auth.connect_managed()

@app.post('/api/youtube/cookies')
async def youtube_cookies(file:UploadFile=File(...),consent:bool=Form(False)):
    if not consent:raise ValueError('Подтвердите использование сессии YouTube на этом Mac')
    raw=await file.read(1024*1024+1)
    return youtube_auth.save_cookies(raw,'cookies_file')

@app.delete('/api/youtube/session')
def youtube_disconnect():
    return youtube_auth.disconnect()

@app.post('/api/import/youtube')
def youtube_download(payload:YouTubeDownload):
    validate_rights(payload.rights_status,payload.license)
    from .youtube import enqueue_download
    return enqueue_download(payload)

@app.post('/api/sources/{source_id}/analyze')
def analyze(source_id, options: AnalyzeOptions):
    source_or_404(source_id)
    return {'job_id':enqueue('analysis',source_id,{'options':options.model_dump(),'settings':db.settings()})}

@app.post('/api/sources/{source_id}/manual-clip')
def manual_clip(source_id, segment: dict):
    source = source_or_404(source_id)
    plan = EditPlan(segments=[segment]).validate_source(source['duration'])
    cid = db.uid()
    s = plan.segments[0]
    db.execute('INSERT INTO clips(id,source_id,title,start,end,score,provider,data,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
               (cid,source_id,'Ручной фрагмент',s.start,s.end,0,'manual',db.dump({'warnings':['Manual selection; no AI scoring']}),time.time()))
    return clip_json(clip_or_404(cid))

@app.delete('/api/sources/{source_id}')
def archive_source(source_id):
    source_or_404(source_id)
    if db.one("SELECT id FROM jobs WHERE source_id=? AND status IN ('Queued','Running','Paused')",(source_id,)):
        raise ValueError('Сначала отмените задачи этого видео')
    db.execute("UPDATE sources SET status='Archived' WHERE id=?",(source_id,))
    return {'archived':True,'original_preserved':True}

@app.get('/api/clips')
def clips():
    return [clip_json(c) for c in db.rows('SELECT * FROM clips ORDER BY created_at DESC')]

# Static bulk routes must precede /clips/{clip_id}/render.
@app.post('/api/clips/batch/render')
def render_batch(batch:BatchRender):
    from .library import generate_batch
    return generate_batch(batch)

@app.post('/api/clips/batch/approve')
def approve_clips(batch:ApprovalBatch):
    from .library import approve_batch
    return approve_batch(batch)

@app.post('/api/clips/batch/delete')
def delete_clips(batch:Batch):
    from .library import delete_batch
    return delete_batch(batch.ids)

@app.get('/api/clips/{clip_id}')
def clip_detail(clip_id):
    c = clip_json(clip_or_404(clip_id))
    c['source'] = source_json(source_or_404(c['source_id']))
    tr = db.one('SELECT data FROM transcripts WHERE source_id=?',(c['source_id'],))
    c['transcript'] = json.loads(tr['data']) if tr else None
    return c

@app.patch('/api/clips/{clip_id}')
def update_clip(clip_id,payload: dict):
    clip = clip_or_404(clip_id)
    if set(payload)-{'title','approved'}: raise ValueError('Unknown clip fields')
    title = str(payload.get('title',clip['title'])).strip()[:180]
    if not title: raise ValueError('Title required')
    db.execute('UPDATE clips SET title=?,approved=? WHERE id=?',(title,int(bool(payload.get('approved',clip['approved']))),clip_id))
    return clip_json(clip_or_404(clip_id))

@app.put('/api/clips/{clip_id}/plan')
def save_plan(clip_id,plan: EditPlan):
    clip = clip_or_404(clip_id)
    plan.validate_source(source_or_404(clip['source_id'])['duration'])
    with db.WRITE_LOCK, db.connect() as c:
        c.execute('INSERT OR REPLACE INTO projects VALUES(?,?,?)',(clip_id,plan.model_dump_json(),time.time()))
        c.execute('UPDATE clips SET start=?,end=?,revision=revision+1 WHERE id=?',(plan.segments[0].start,plan.segments[-1].end,clip_id))
        c.execute('DELETE FROM segments WHERE clip_id=?',(clip_id,))
        for pos,segment in enumerate(plan.segments):
            c.execute('INSERT INTO segments VALUES(?,?,?,?,?)',(db.uid(),clip_id,pos,segment.start,segment.end))
    (DATA/'projects'/f'{clip_id}.json').write_text(plan.model_dump_json(),encoding='utf-8')
    return clip_json(clip_or_404(clip_id))

@app.post('/api/clips/{clip_id}/render')
def render_clip(clip_id):
    clip = clip_or_404(clip_id)
    if not source_or_404(clip['source_id'])['path']: raise ValueError('Загрузите локальный исходник для монтажа')
    plan = clip_json(clip)['plan']
    parsed=EditPlan.model_validate(plan)
    if parsed.audio_replacement.mode!='original':
        from .audio_replacement import preflight
        row=db.one('SELECT data FROM transcripts WHERE source_id=?',(clip['source_id'],))
        preflight([(clip_id,parsed,json.loads(row['data']) if row else {'segments':[]},sum(s.end-s.start for s in parsed.segments))],db.settings())
    return {'job_id':enqueue('render',clip['source_id'],{'plan':plan,'revision':clip['revision'],'audio_settings':db.settings() if parsed.audio_replacement.mode!='original' else None},clip_id)}

@app.get('/api/clips/{clip_id}/media')
def clip_media(clip_id,download: bool=False,format: str='mp4'):
    clip = clip_or_404(clip_id)
    if not clip['render_path']: raise HTTPException(404,'Clip has not been rendered')
    if format not in ('mp4','ass','srt'): raise ValueError('Invalid export format')
    path = safe_path(clip['render_path']).with_suffix('.'+format)
    if not path.exists(): raise HTTPException(404,'Export not found')
    if format=='mp4':
        from .metadata import delivery_path
        path=delivery_path(clip_json(clip))
    return FileResponse(path,filename=f'{clip["id"]}.{format}' if download else None,
                        media_type='video/mp4' if format=='mp4' else 'text/plain; charset=utf-8')

@app.post('/api/exports')
def export_batch(batch:ExportBatch):
    return create_export(batch)

def create_export(batch:ExportBatch,job_id=None):
    from .library import WORKFILES_LOCK
    with WORKFILES_LOCK:
        return write_export(batch,job_id)

def write_export(batch,job_id=None):
    from .metadata import delivery_path
    selected=[clip_json(clip_or_404(cid)) for cid in dict.fromkeys(batch.ids)]
    if not batch.include_metadata and any(not c['render_path'] for c in selected):
        raise ValueError('Сначала создайте MP4 для всех выбранных клипов через Generate Reel')
    eid=db.uid()
    dest=DATA/'exports'/f'{eid}.zip'
    required=sum(safe_path(c['render_path']).stat().st_size for c in selected if c['render_path'])
    check_space(required,db.settings()['min_free_mb'])
    fields=['id','source_id','title','start','end','score','provider','revision','render_revision']
    buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader()
    for clip in selected:
        row={field:clip[field] for field in fields}
        for key,value in row.items():
            if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')):row[key]="'"+value
        writer.writerow(row)
    def entry(name):
        info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
        info.external_attr=0o600<<16
        return info
    try:
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_STORED) as archive:
            if batch.include_metadata:
                archive.writestr(entry('metadata.json'),db.dump([{k:v for k,v in c.items() if k not in ('render_path','media_url')} for c in selected]))
                archive.writestr(entry('metadata.csv'),'\ufeff'+buffer.getvalue())
            for clip in selected:
                check_job(job_id)
                if not clip['render_path']:continue
                original=safe_path(clip['render_path'])
                extensions=('.mp4','.ass','.srt') if batch.include_subtitles else ('.mp4',)
                for ext in extensions:
                    file=delivery_path(clip,job_id) if ext=='.mp4' else original.with_suffix(ext)
                    if not file.exists():continue
                    with archive.open(entry(clip['id']+ext),'w',force_zip64=True) as target,file.open('rb') as source:
                        while chunk:=source.read(1024*1024):
                            check_job(job_id);target.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {'url':f'/api/exports/{eid}','size':dest.stat().st_size,'clips':len(selected)}

@app.get('/api/exports/{export_id}')
def download_export(export_id):
    if len(export_id)!=32 or any(c not in '0123456789abcdef' for c in export_id): raise HTTPException(404)
    path = DATA/'exports'/f'{export_id}.zip'
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path,filename='vds-shorts-factory.zip')

@app.get('/api/jobs')
def jobs():
    from .job_files import output_info
    result = db.rows('SELECT j.*,s.name source_name,c.title clip_title FROM jobs j LEFT JOIN sources s ON s.id=j.source_id LEFT JOIN clips c ON c.id=j.clip_id ORDER BY j.created_at DESC LIMIT 500')
    for job in result:
        job['output']=output_info(job)
        if job['kind']=='export':job['source_name']='ZIP · '+str(len(json.loads(job['payload']).get('ids',[])))+' роликов'
        if job['kind'] in ('montage','montage_words','montage_music'):
            prefix={'montage':'Монтаж · ','montage_words':'Распознавание речи · ','montage_music':'AI-музыка ElevenLabs · '}[job['kind']]
            job['source_name']=prefix+json.loads(job['payload']).get('title','')
        if job['kind']=='download' and not job['source_name']:
            job['source_name']='YouTube · '+json.loads(job['payload']).get('url','')
        job['logs']=json.loads(job['logs'])
        job['checkpoints']=json.loads(job['checkpoints'])
        job.pop('payload',None)
    return result

@app.post('/api/jobs/{job_id}/reveal')
def reveal_job(job_id):
    from .job_files import output_path,reveal
    job=db.one('SELECT * FROM jobs WHERE id=?',(job_id,))
    if not job: raise HTTPException(404,'Задача не найдена')
    if job['status']!='Completed': raise ValueError('Файл ещё не готов. Дождитесь завершения задачи.')
    path=output_path(job)
    if path is None: raise HTTPException(404,'Файл этой задачи не найден: возможно, он удалён или перемещён.')
    reveal(path)
    return {'ok':True,'filename':path.name,'path':str(path)}

@app.get('/api/jobs/{job_id}/file')
def download_job_file(job_id):
    from .job_files import output_path
    job=db.one('SELECT * FROM jobs WHERE id=?',(job_id,))
    if not job: raise HTTPException(404,'Задача не найдена')
    path=output_path(job)
    if path is None: raise HTTPException(404,'Готовый файл этой задачи не найден')
    filename=path.name
    if job['kind']=='render':
        from .metadata import delivery_path
        row=db.one('SELECT qc FROM render_tasks WHERE job_id=?',(job_id,))
        qc=json.loads(row['qc']) if row and row['qc'] else {}
        path=delivery_path({'id':job['clip_id'] or job_id,'render_path':str(path.relative_to(DATA.resolve())),'qc':qc})
    return FileResponse(path,filename=filename)

@app.post('/api/jobs/{job_id}/{action}')
def control_job(job_id,action):
    job = db.one('SELECT * FROM jobs WHERE id=?',(job_id,))
    if not job: raise HTTPException(404)
    if job['kind']=='publish':
        from .publishing import control
        result=control(job,action)
        if result is not None:return result
    states = {'pause':('Paused',('Queued','Running')), 'resume':('Queued',('Paused',)),
              'cancel':('Cancelled',('Queued','Running','Paused')), 'retry':('Queued',('Failed','Cancelled'))}
    if action not in states: raise ValueError('Unknown job action')
    status, allowed = states[action]
    if job['status'] not in allowed: raise ValueError(f'{action} unavailable for {job["status"]}')
    if status=='Queued' and job_id in farm.active and not farm.active[job_id].done():
        raise ValueError('Задача останавливается; повторите через секунду')
    db.job_update(job_id,status=status,stage=status,error=None)
    return {'status':status}

@app.get('/api/publishing/account')
def publishing_account():
    return publishing_auth.status()

@app.post('/api/publishing/client')
async def publishing_client(request:Request):
    body=await request.body()
    if len(body)>65536:raise ValueError('OAuth JSON слишком большой')
    try:value=json.loads(body)
    except ValueError:raise ValueError('Нужен корректный JSON OAuth-клиента') from None
    if not isinstance(value,dict):raise ValueError('Нужен JSON-объект OAuth-клиента')
    return publishing_auth.save_client(value)

@app.post('/api/publishing/connect')
def publishing_connect():
    return publishing_auth.connect()

@app.get('/api/publishing/oauth/callback')
def publishing_callback(state:str='',code:str='',error:str=''):
    try:
        publishing_auth.callback(state,code,error)
    except ValueError as exc:
        from html import escape
        return HTMLResponse('<meta charset="utf-8"><title>Подключение YouTube</title><h1>Канал не подключён</h1><p>'+escape(str(exc))+'</p><a href="/?settings=publish#settings">Вернуться в настройки</a>',status_code=400)
    return RedirectResponse('/?settings=publish#settings',status_code=303)

@app.post('/api/publishing/verify')
def publishing_verify():
    return publishing_auth.verify_channel()

@app.post('/api/publishing/disconnect')
def publishing_disconnect():
    if db.one("SELECT id FROM jobs WHERE kind='publish' AND status IN ('Running','Queued','Paused')"):
        raise ValueError('Сначала отмените незавершённые публикации. Уже сохранённое в YouTube расписание отключение не отменит.')
    return publishing_auth.disconnect()

@app.get('/api/publishing')
def publishing_list():
    from .publishing import list_publications
    return {'items':list_publications(),'account':publishing_auth.status(),'paused':db.settings().get('publish_paused',False)}

@app.post('/api/publishing/batch')
def publishing_batch(payload:PublishBatch):
    from .publishing import enqueue_batch
    return enqueue_batch(payload)

@app.post('/api/publishing/pause')
def publishing_pause(payload:dict):
    if not isinstance(payload.get('paused'),bool):raise ValueError('paused must be boolean')
    db.execute("UPDATE settings SET value=? WHERE key='publish_paused'",(db.dump(payload['paused']),))
    if not payload['paused']:
        db.execute("UPDATE jobs SET status='Queued',stage='Queued' WHERE kind='publish' AND status='Paused' AND stage='Публикации приостановлены'")
    return {'paused':payload['paused']}

@app.post('/api/publishing/refresh')
def publishing_refresh():
    from .publishing import refresh_remote
    return refresh_remote()

@app.post('/api/publishing/{pid}/cancel')
def publishing_cancel(pid:str):
    from .publishing import cancel
    return cancel(pid)

@app.get('/api/settings')
def get_settings():
    from .integrations import usage_summary
    from .audio_replacement import music_stats
    return {'values':db.settings(),'key_connected':bool(secret()),
            'openai_key_connected':bool(secret('openai')),'elevenlabs_key_connected':bool(secret('elevenlabs')),
            'integration_usage':{**{p:usage_summary(p) for p in ('openai','elevenlabs')},'music':music_stats()},
            'presets':__import__('backend.subtitles',fromlist=['PRESETS']).PRESETS}

@app.put('/api/settings')
def save_settings(payload: SettingsUpdate):
    from .schemas import SubtitleStyle
    values = {**db.settings(),**payload.values}
    if set(values)-set(DEFAULTS): raise ValueError('Unknown settings')
    from .publishing import validate_profile
    validate_profile(values)
    if values['provider'] not in ('local','gemini','openai'): raise ValueError('Provider is not implemented')
    if not isinstance(values['cloud_enabled'],bool): raise ValueError('cloud_enabled must be boolean')
    EditPlan(segments=[{'start':0,'end':1}],aspect=values['aspect'],fps=values['fps'],crop_mode=values['crop_mode'],encoder=values['encoder'],quality=values['render_quality'])
    SubtitleStyle(preset=values['subtitle_preset'])
    AnalyzeOptions(**{k:values[k] for k in ('min_duration','max_duration','target_count','score_threshold','language','profile')})
    for k,lo,hi in [('min_free_mb',128,100000),('max_upload_mb',1,100000),('budget_usd',0,10000),('cloud_request_limit',1,10000),('max_output_tokens',1024,32000),('openai_budget_usd',0,10000),('openai_request_limit',1,10000),('openai_max_output_tokens',1024,16000),('elevenlabs_request_limit',1,1000),('music_request_limit',1,1000),('music_seconds_limit',3,100000)]:
        if isinstance(values[k],bool) or not isinstance(values[k],(int,float)) or not math.isfinite(values[k]) or not lo<=values[k]<=hi: raise ValueError(f'Invalid {k}')
    for k in ('cloud_request_limit','max_output_tokens','openai_request_limit','openai_max_output_tokens','elevenlabs_request_limit','music_request_limit','music_seconds_limit'):
        if int(values[k])!=values[k]: raise ValueError(f'Invalid {k}')
        values[k]=int(values[k])
    for k in ('ai_concurrency','whisper_concurrency','ffmpeg_concurrency'):
        if values[k]!=1: raise ValueError('This release runs one task per resource')
    for k in ('input_price_per_million','output_price_per_million','openai_input_price_per_million','openai_output_price_per_million'):
        if values[k] is not None and (isinstance(values[k],bool) or not isinstance(values[k],(int,float)) or not math.isfinite(values[k]) or not 0<=values[k]<=10000): raise ValueError('Invalid model pricing')
    if not isinstance(values['model'],str) or len(values['model'])>200: raise ValueError('Invalid model name')
    if values['music_model'] not in ('music_v1','music_v2','music_v2_5'): raise ValueError('Invalid music model')
    if not isinstance(values['whisper_model'],str) or not values['whisper_model'].startswith('mlx-community/'): raise ValueError('Use a model from mlx-community')
    for k in ('openai_model','elevenlabs_voice_id','elevenlabs_model'):
        if not isinstance(values[k],str) or (values[k] and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}',values[k])): raise ValueError(f'Invalid {k}')
    for provider,key in [('gemini',payload.api_key),('openai',payload.openai_api_key),('elevenlabs',payload.elevenlabs_api_key)]:
        if key is not None:
            if any(c.isspace() for c in key.strip()): raise ValueError('API key не должен содержать пробелы или переносы строк')
    for provider,key in [('gemini',payload.api_key),('openai',payload.openai_api_key),('elevenlabs',payload.elevenlabs_api_key)]:
        if key is not None: write_secret(provider,key)
    with db.WRITE_LOCK,db.connect() as c:
        for key,value in values.items(): c.execute('UPDATE settings SET value=? WHERE key=?',(db.dump(value),key))
    return get_settings()

@app.post('/api/settings/test-connection')
def test_connection():
    if db.settings()['provider']=='openai':
        from .integrations import test_openai
        return test_openai()
    if not secret(): raise ValueError('Сначала сохраните Gemini API key')
    from google import genai
    try:
        with genai.Client(api_key=secret(),http_options={'timeout':30000}) as client:
            models = []
            for model in client.models.list():
                actions = getattr(model,'supported_actions',None) or []
                if 'generateContent' in actions or 'generate_content' in actions:
                    models.append({'id':model.name.removeprefix('models/'),'name':model.display_name or model.name})
        return {'ok':True,'models':models,'note':'Authentication and model discovery only; no material was uploaded'}
    except Exception as e:
        raise ValueError(redact(str(e)))

@app.post('/api/settings/test-openai')
def test_openai_connection():
    from .integrations import test_openai
    return test_openai()

@app.post('/api/settings/test-elevenlabs')
def test_elevenlabs_connection():
    from .integrations import test_voice
    return test_voice(db.settings())

@app.post('/api/integrations/author-pilot')
def author_pilot(payload: AuthorPilot):
    from .integrations import author_pilot
    return author_pilot(payload.clip_id)

@app.get('/api/integrations/author-pilot')
def last_author_pilot():
    from .integrations import latest_pilot
    return {'pilot':latest_pilot()}

@app.post('/api/integrations/voice-preview')
def voice_preview(payload: VoicePreview):
    from .integrations import voice_preview
    return voice_preview(payload.text,db.settings())

@app.get('/api/integrations/voice/{digest}')
def voice_audio(digest: str):
    if not re.fullmatch('[0-9a-f]{64}',digest): raise HTTPException(404,'Audio not found')
    path = DATA/'previews'/'voices'/f'{digest}.mp3'
    if not path.is_file(): raise HTTPException(404,'Audio not found')
    return FileResponse(path,media_type='audio/mpeg',filename='voice-preview.mp3',content_disposition_type='inline')

@app.post('/api/storage/clear-cache')
def clear_cache():
    from .integrations import LOCK
    if not LOCK.acquire(blocking=False):
        raise ValueError('Дождитесь завершения AI-пробы или озвучки перед очисткой кэша')
    try: return _clear_cache()
    finally: LOCK.release()

def _clear_cache():
    if db.one("SELECT id FROM jobs WHERE status IN ('Running','Queued','Paused')"):
        raise ValueError('Остановите/отмените очередь перед очисткой')
    removed = 0
    # Original files, word timestamps, AI responses, projects and completed renders are preserved.
    for folder in ('audio','temp','previews'):
        path=DATA/folder
        for entry in path.iterdir():
            if entry.is_file(): removed+=entry.stat().st_size; entry.unlink()
            elif entry.is_dir() and not entry.is_symlink():
                removed+=sum(p.stat().st_size for p in entry.rglob('*') if p.is_file())
                shutil.rmtree(entry)
    db.execute("UPDATE jobs SET checkpoints='{}' WHERE kind='analysis' AND status IN ('Failed','Cancelled')")
    return {'removed_bytes':removed}

from .montage import router as montage_router
app.include_router(montage_router)

dist=ROOT/'frontend/dist'
if dist.exists():
    app.mount('/',StaticFiles(directory=dist,html=True),name='studio')
