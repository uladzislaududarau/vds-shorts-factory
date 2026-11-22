"""Atomic bulk generation, selection and deletion of owned clip artifacts."""
import json
import re
import shutil
import threading
import time
from pathlib import Path

from . import db
from .config import DATA,ROOT,safe_path
from .schemas import EditPlan,SubtitleStyle
from .subtitles import PRESETS

WORKFILES_LOCK=threading.RLock()

def selected_rows(connection,ids):
    ids=list(dict.fromkeys(ids))
    rows=[]
    for cid in ids:
        row=connection.execute('SELECT * FROM clips WHERE id=?',(cid,)).fetchone()
        if not row:raise ValueError('Некоторые выбранные клипы уже отсутствуют. Обновите список и выберите их снова.')
        rows.append(dict(row))
    return rows

def generate_batch(payload):
    from workers.queue import default_plan,enqueue_tx
    jobs=[]
    with db.WRITE_LOCK,db.connect() as connection:
        clips=selected_rows(connection,payload.ids)
        prepared=[]
        audio_prepared=[]
        for clip in clips:
            source=connection.execute('SELECT * FROM sources WHERE id=?',(clip['source_id'],)).fetchone()
            if not source or not source['path'] or not safe_path(source['path']).is_file():
                raise ValueError(f'Для «{clip["title"]}» нет локального исходника. Сначала скачайте видео.')
            stored=connection.execute('SELECT data FROM projects WHERE clip_id=?',(clip['id'],)).fetchone()
            original=EditPlan.model_validate_json(stored['data']) if stored else default_plan(clip)
            plan=original.model_copy(deep=True)
            if payload.overrides:
                values=payload.overrides.model_dump()
                preset=values.pop('subtitle_preset')
                subtitles_enabled=values.pop('subtitles_enabled')
                for key,value in values.items():setattr(plan,key,value)
                plan.subtitles=SubtitleStyle(preset=preset,enabled=subtitles_enabled,**PRESETS[preset])
            if payload.audio_replacement is not None:
                plan.audio_replacement=payload.audio_replacement.model_copy(deep=True)
            plan.validate_source(source['duration'])
            changed=plan.model_dump()!=original.model_dump()
            if clip['render_path'] and clip['render_revision']==clip['revision']:
                rendered=connection.execute('SELECT rt.plan FROM render_tasks rt JOIN jobs j ON j.id=rt.job_id WHERE j.clip_id=? AND j.status=\'Completed\' ORDER BY j.created_at DESC LIMIT 1',(clip['id'],)).fetchone()
                if rendered and EditPlan.model_validate_json(rendered['plan']).model_dump()!=plan.model_dump():changed=True
            revision=clip['revision']+int(changed)
            active=connection.execute("SELECT payload FROM jobs WHERE clip_id=? AND kind='render' AND status IN ('Queued','Running','Paused')",(clip['id'],)).fetchone()
            if active:
                snapshot=json.loads(active['payload'])
                if EditPlan.model_validate(snapshot['plan']).model_dump()!=plan.model_dump() or snapshot.get('revision')!=revision:
                    raise ValueError(f'«{clip["title"]}» уже создаётся с другими настройками. Дождитесь завершения или отмените задачу.')
            prepared.append((clip,plan,revision))
            if plan.audio_replacement.mode!='original':
                row=connection.execute('SELECT data FROM transcripts WHERE source_id=?',(source['id'],)).fetchone()
                transcript=json.loads(row['data']) if row else {'segments':[]}
                audio_prepared.append((clip['id'],plan,transcript,sum(s.end-s.start for s in plan.segments)))
        if audio_prepared:
            from .audio_replacement import preflight
            preflight(audio_prepared,db.settings())
        # No mutation until every selected clip and plan passes preflight.
        for clip,plan,revision in prepared:
            connection.execute('INSERT OR REPLACE INTO projects VALUES(?,?,?)',(clip['id'],plan.model_dump_json(),time.time()))
            connection.execute('UPDATE clips SET revision=? WHERE id=?',(revision,clip['id']))
            jid=enqueue_tx(connection,'render',clip['source_id'],{'plan':plan.model_dump(),'revision':revision,'audio_settings':db.settings() if plan.audio_replacement.mode!='original' else None},clip['id'])
            jobs.append({'clip_id':clip['id'],'job_id':jid})
        export_job_id=None
        if payload.download_zip:
            export_job_id=enqueue_tx(connection,'export',None,{'ids':[clip['id'] for clip in clips],
                'required_jobs':[j['job_id'] for j in jobs],'include_subtitles':payload.include_subtitles,
                'include_metadata':payload.include_metadata})
    return {'jobs':jobs,'export_job_id':export_job_id,'clips':len(jobs)}

def approve_batch(payload):
    with db.WRITE_LOCK,db.connect() as connection:
        clips=selected_rows(connection,payload.ids)
        connection.executemany('UPDATE clips SET approved=? WHERE id=?',[(int(payload.approved),c['id']) for c in clips])
    return {'updated':len(clips),'approved':payload.approved}

def delete_batch(ids):
    staging=ROOT/'.run/trash'/db.uid()
    moved=[]
    total=0
    try:
        from .metadata import LOCK as metadata_lock
        with WORKFILES_LOCK,db.WRITE_LOCK,metadata_lock,db.connect() as connection:
            clips=selected_rows(connection,ids)
            wanted={c['id'] for c in clips}
            active=connection.execute("SELECT kind,clip_id,payload FROM jobs WHERE status IN ('Queued','Running','Paused')").fetchall()
            for job in active:
                if job['clip_id'] in wanted or (job['kind']=='export' and wanted.intersection(json.loads(job['payload']).get('ids',[]))):
                    raise ValueError('Выбранные клипы участвуют в незавершённой генерации или ZIP. Дождитесь завершения либо отмените задачи.')
            files=set()
            for clip in clips:
                if clip['render_path']:
                    path=safe_path(clip['render_path'])
                    files.update(path.with_suffix(ext) for ext in ('.mp4','.srt','.ass'))
                if re.fullmatch('[0-9a-f]{32}',clip['id']):
                    files.update((DATA/'renders').glob(clip['id']+'-r*.*'))
                    files.update((DATA/'exports').glob('clean-'+clip['id']+'-*.mp4'))
                    files.add(DATA/'projects'/(clip['id']+'.json'))
            staging.mkdir(parents=True,mode=0o700)
            for number,path in enumerate(sorted(files)):
                if not path.is_file():continue
                if not path.resolve().is_relative_to(DATA.resolve()):raise ValueError('Unsafe clip artifact path')
                destination=staging/str(number)
                size=path.stat().st_size
                path.replace(destination)
                moved.append((path,destination));total+=size
            for clip in clips:
                cid=clip['id']
                connection.execute('DELETE FROM render_tasks WHERE job_id IN (SELECT id FROM jobs WHERE clip_id=?)',(cid,))
                connection.execute('DELETE FROM jobs WHERE clip_id=?',(cid,))
                for table in ('scores','segments','projects'):
                    connection.execute(f'DELETE FROM {table} WHERE clip_id=?',(cid,))
                connection.execute('INSERT OR REPLACE INTO deleted_clips VALUES(?,?)',(cid,time.time()))
                connection.execute('DELETE FROM clips WHERE id=?',(cid,))
    except BaseException:
        for original,temporary in reversed(moved):
            if temporary.exists():temporary.replace(original)
        shutil.rmtree(staging,ignore_errors=True)
        raise
    shutil.rmtree(staging,ignore_errors=True)
    return {'deleted':len(clips),'removed_bytes':total,'originals_preserved':True,'existing_exports_preserved':True}
