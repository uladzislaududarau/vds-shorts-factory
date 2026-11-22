"""Persistent YouTube download jobs; cookies never enter SQLite payloads."""
import json
import shutil
import sys
import time
from pathlib import Path
from . import db
from .config import DATA,safe_path
from .media import check_job,run_youtube,validate_youtube
from .schemas import YouTubeDownload
from .youtube_auth import cookie_snapshot,status as session_status

def enqueue_download(payload:YouTubeDownload):
    url=validate_youtube(payload.url)
    with db.WRITE_LOCK,db.connect() as conn:
        existing=conn.execute("SELECT id FROM jobs WHERE kind='download' AND json_extract(payload,'$.url')=? AND status IN ('Queued','Running','Paused')",(url,)).fetchone()
        if existing:return {'job_id':existing['id'],'queued':True,'duplicate':True}
        source=conn.execute("SELECT id,path FROM sources WHERE url=? AND path IS NOT NULL AND status!='Archived' ORDER BY created_at DESC LIMIT 1",(url,)).fetchone()
        if source and safe_path(source['path']).is_file():
            if payload.analyze_after:
                from workers.queue import enqueue
                source_id=source['id']
            else:return {'source_id':source['id'],'duplicate':True,'queued':False}
        else:source_id=None
        if source_id:
            # This connection has made no changes, so another connection may enqueue.
            return {'job_id':enqueue('analysis',source_id,{'options':payload.options.model_dump(),'settings':db.settings()}),
                    'source_id':source_id,'queued':True,'duplicate':True,'already_downloaded':True}
        if payload.use_account and not session_status()['connected']:
            raise ValueError('Сначала войдите в YouTube и нажмите «Подключить сессию» или отключите «Использовать мой аккаунт» для публичного видео')
        jid,now=db.uid(),time.time()
        data={**payload.model_dump(),'url':url}
        conn.execute('INSERT INTO jobs(id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                     (jid,'download','Queued',db.dump(data),now,now))
    return {'job_id':jid,'queued':True,'duplicate':False}

def download(job,register_file,settings):
    jid=job['id']
    payload=YouTubeDownload.model_validate_json(job['payload'])
    checkpoints=json.loads(job['checkpoints'])
    source_id=checkpoints.get('download_source_id')
    source=db.one('SELECT * FROM sources WHERE id=?',(source_id,)) if source_id else None
    work=DATA/'temp'/f'youtube-{jid}'
    work.mkdir(exist_ok=True)
    if not source or not source['path'] or not safe_path(source['path']).is_file():
        db.job_update(jid,stage='Проверка доступа к видео',progress=1)
        db.log(jid,'Скачивание YouTube: '+('подключённая сессия' if payload.use_account else 'без аккаунта'))
        updated=0
        def progress():
            nonlocal updated
            if time.monotonic()-updated<.7:return
            updated=time.monotonic()
            try:data=json.loads((work/'progress.json').read_text())
            except (OSError,ValueError):return
            fields={'stage':str(data['stage'])[:100],'progress':min(float(data.get('progress',0)),88)}
            detail={k:data[k] for k in ('downloaded_bytes','total_bytes','speed','eta','title') if k in data}
            checkpoints['download_progress']={**checkpoints.get('download_progress',{}),**detail}
            db.job_update(jid,**fields,checkpoints=db.dump(checkpoints))
        with cookie_snapshot(payload.use_account,jid) as cookies:
            request=work/'request.json'
            request.write_text(db.dump({'url':validate_youtube(payload.url),'cookie_file':str(cookies) if cookies else None,
                              'max_bytes':int(settings['max_upload_mb']*1024**2),'reserve_mb':settings['min_free_mb']}))
            try:run_youtube([sys.executable,'-m','workers.youtube_fetch',request],timeout=14400,job_id=jid,on_progress=progress)
            finally:request.unlink(missing_ok=True)
        check_job(jid)
        result=json.loads((work/'result.json').read_text())
        media=(work/result['file']).resolve()
        if media.parent!=work.resolve() or media.suffix.lower() not in ('.mp4','.mkv','.webm','.mov'):
            raise ValueError('Некорректный путь результата скачивания')
        db.job_update(jid,stage='Сохранение исходника',progress=90)
        old=db.one('SELECT * FROM sources WHERE url=? AND path IS NULL ORDER BY created_at LIMIT 1',(payload.url,))
        if old and abs(float(result.get('duration') or 0)-old['duration'])>2:
            raise ValueError('Длительность скачанного видео отличается от ранее сохранённой ссылки; проверьте источник')
        imported=register_file(media,result['title']+media.suffix,payload.rights_status,payload.license,payload.url,True)
        source_id=imported['source']['id']
        db.execute('UPDATE sources SET url=? WHERE id=?',(payload.url,source_id))
        if old:
            local=db.one('SELECT * FROM sources WHERE id=?',(source_id,))
            with db.WRITE_LOCK,db.connect() as connection:
                fields=('path','width','height','fps','size','has_audio','thumbnail','metadata')
                connection.execute('UPDATE sources SET '+','.join(f'{key}=?' for key in fields)+",kind='local',status='Imported' WHERE id=?",
                                   (*[local[key] for key in fields],old['id']))
                if not imported['duplicate']:
                    connection.execute("UPDATE sources SET status='Archived' WHERE id=?",(source_id,))
            source_id=old['id']
        checkpoints['download_source_id']=source_id
        db.job_update(jid,source_id=source_id,checkpoints=db.dump(checkpoints))
        db.log(jid,'Исходник сохранён в локальной библиотеке')
    check_job(jid)
    if payload.analyze_after:
        from workers.queue import enqueue
        analysis_id=checkpoints.get('analysis_job_id')
        if not analysis_id or not db.one('SELECT id FROM jobs WHERE id=?',(analysis_id,)):
            analysis_id=enqueue('analysis',source_id,{'options':payload.options.model_dump(),'settings':settings})
            checkpoints['analysis_job_id']=analysis_id
            db.job_update(jid,checkpoints=db.dump(checkpoints))
        db.log(jid,'Анализ поставлен в очередь: '+analysis_id[:8])
    shutil.rmtree(work,ignore_errors=True)
    return source_id
