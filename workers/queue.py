import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from backend import db
from backend.config import DATA, FFMPEG, safe_path, redact
from backend.media import run, check_job, Interrupted, check_space
from backend.schemas import AnalyzeOptions, EditPlan, SubtitleStyle
from backend.analysis import LocalProvider, GeminiProvider, score
from backend.render import render

ACTIVE = ('Queued', 'Running')

class Farm:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='factory')
        self.ffmpeg = threading.Semaphore(1)
        self.whisper = threading.Semaphore(1)
        self.ai = threading.Semaphore(1)
        self.active = {}

    def start(self):
        # A killed process leaves only checkpointed stages. Resume each unfinished job once.
        db.execute("UPDATE jobs SET status='Queued',stage='Recovering',updated_at=? WHERE status='Running'", (time.time(),))
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        # subprocess polling observes Paused, killing only owned process groups.
        for job_id in list(self.active):
            db.execute("UPDATE jobs SET status='Paused',stage='Paused on shutdown' WHERE id=? AND status='Running'", (job_id,))
        if self.thread:
            self.thread.join(timeout=3)
        self.executor.shutdown(wait=True, cancel_futures=True)

    def loop(self):
        while not self.stop_event.wait(.4):
            self.active = {k: v for k, v in self.active.items() if not v.done()}
            running_kinds = [row['kind'] for k in self.active if (row:=db.one('SELECT kind FROM jobs WHERE id=?',(k,))) is not None]
            for job in db.rows("SELECT * FROM jobs WHERE status='Queued' ORDER BY created_at LIMIT 100"):
                if len(self.active) >= 3 or job['id'] in self.active or job['kind'] in running_kinds:
                    continue
                if job['kind']=='publish' and db.settings().get('publish_paused'):continue
                if job['kind']=='export':
                    required=json.loads(job['payload']).get('required_jobs',[])
                    statuses=[db.one('SELECT status FROM jobs WHERE id=?',(jid,)) for jid in required]
                    if any(not row or row['status'] in ('Failed','Cancelled') for row in statuses):
                        db.job_update(job['id'],status='Failed',error='Один из роликов не создан или отменён. Исправьте задачу генерации и повторите ZIP.')
                        continue
                    if any(row['status']!='Completed' for row in statuses):continue
                claimed = db.execute("UPDATE jobs SET status='Running',error=NULL,updated_at=? WHERE id=? AND status='Queued'", (time.time(),job['id']))
                if claimed:
                    self.active[job['id']] = self.executor.submit(self.work, job['id'])
                    running_kinds.append(job['kind'])

    def work(self, job_id):
        job = db.one('SELECT * FROM jobs WHERE id=?', (job_id,))
        try:
            check_job(job_id)
            source = db.one('SELECT * FROM sources WHERE id=?', (job['source_id'],))
            if job['kind'] == 'analysis':
                self.analyze(job, source)
            elif job['kind'] == 'render':
                self.render(job, source)
            elif job['kind'] == 'download':
                from backend.youtube import download
                from backend.main import register_file
                # yt-dlp may merge audio/video with FFmpeg; share the resource limit.
                with self.ffmpeg:
                    download(job,register_file,db.settings())
            elif job['kind']=='publish':
                from backend.publishing import work
                work(job)
            elif job['kind']=='montage':
                from backend.montage import render_project
                render_project(job,self.ffmpeg,self.whisper)
            elif job['kind']=='montage_music':
                from backend.montage import generate_project_music
                generate_project_music(job)
            elif job['kind']=='montage_words':
                from backend.montage import recognise_project
                recognise_project(job,self.ffmpeg,self.whisper)
            elif job['kind']=='export':
                from backend.main import create_export
                from backend.schemas import ExportBatch
                payload=json.loads(job['payload'])
                db.job_update(job_id,stage='Создание ZIP',progress=30)
                result=create_export(ExportBatch(ids=payload['ids'],include_subtitles=payload.get('include_subtitles',False),
                                               include_metadata=payload.get('include_metadata',False)),job_id=job_id)
                db.job_update(job_id,checkpoints=db.dump({'download_url':result['url'],'clips':result['clips'],'size':result['size']}))
            check_job(job_id)
            db.job_update(job_id, status='Completed', stage='Completed', progress=100, error=None)
        except Interrupted:
            db.log(job_id, 'Stopped at checkpoint; completed expensive stages remain cached')
        except Exception as e:
            db.job_update(job_id, status='Failed', error=redact(str(e)))
            db.log(job_id, str(e))
            if job['kind'] == 'analysis':
                db.execute("UPDATE sources SET status='Failed' WHERE id=?", (job['source_id'],))

    def analyze(self, job, source):
        jid = job['id']
        payload = json.loads(job['payload'])
        opts = AnalyzeOptions.model_validate(payload['options'])
        settings = payload['settings']
        checkpoints = json.loads(job['checkpoints'])
        def stage(name, progress):
            check_job(jid)
            db.job_update(jid, stage=name, progress=progress)
            db.execute('UPDATE sources SET status=? WHERE id=?', (name,source['id']))
            db.log(jid, name)
        def checkpoint(name, value=True):
            checkpoints[name] = value
            db.job_update(jid, checkpoints=db.dump(checkpoints))
        transcript = {'segments': [], 'text': '', 'language': 'unknown'}
        scenes = []
        if source['path']:
            wav = DATA / 'audio' / f'{source["id"]}.wav'
            stage('Audio extraction', 8)
            if not source['has_audio']:
                raise ValueError('В исходнике нет аудио: локальный поиск смысловых фрагментов невозможен. Можно создать ручной клип.')
            if not checkpoints.get('audio') or not wav.exists():
                check_space(int(source['duration'] * 32000), settings['min_free_mb'])
                with self.ffmpeg:
                    run([FFMPEG,'-hide_banner','-loglevel','error','-y','-i',safe_path(source['path']),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',wav], jid)
                checkpoint('audio')
            stage('Transcribing', 20)
            cached = db.one('SELECT * FROM transcripts WHERE source_id=?', (source['id'],))
            if cached and cached['model'] == settings['whisper_model'] and (opts.language == 'auto' or cached['language'] == opts.language):
                transcript = json.loads(cached['data'])
                db.log(jid,'Using cached word timestamps')
            else:
                destination = DATA / 'transcripts' / f'{source["id"]}.json'
                with self.whisper:
                    run([sys.executable,'-m','workers.transcribe',wav,destination,settings['whisper_model'],opts.language], jid, timeout=14400)
                transcript = json.loads(destination.read_text())
                if not transcript.get('segments'):
                    raise ValueError('Whisper не распознал речь. Проверьте аудио и язык.')
                db.execute('INSERT OR REPLACE INTO transcripts VALUES(?,?,?,?,?,?)',
                           (source['id'],settings['whisper_model'],transcript.get('language','unknown'),transcript.get('text',''),db.dump(transcript),time.time()))
            checkpoint('transcript')
            stage('Scene detection', 50)
            scene_path = DATA / 'projects' / f'{source["id"]}-scenes.json'
            if not scene_path.exists():
                run([sys.executable,'-m','workers.scenes',safe_path(source['path']),scene_path],jid,timeout=14400)
            scenes = json.loads(scene_path.read_text())
            checkpoint('scenes')
        stage('Analyzing', 63)
        provider_name = settings['provider'] if opts.cloud_consent and settings['cloud_enabled'] and settings['provider'] in ('gemini','openai') else 'local'
        if not source['path'] and provider_name != 'gemini':
            raise ValueError('Анализ URL требует Gemini и отдельного согласия на отправку URL в облако. Для локального режима загрузите файл.')
        material = [source['sha256'] or source['url'],opts.model_dump(),provider_name,settings['openai_model'] if provider_name=='openai' else settings['model'] if provider_name=='gemini' else settings['whisper_model'],transcript.get('text',''), 'analysis-v2']
        key = hashlib.sha256(db.dump(material).encode()).hexdigest()
        previous = db.one('SELECT * FROM analysis WHERE cache_key=?',(key,))
        from backend.schemas import CandidateList
        if previous:
            candidates = CandidateList.model_validate_json(previous['data']).candidates
            db.log(jid,'Using cached analysis')
        else:
            from backend.integrations import OpenAIProvider
            provider = OpenAIProvider(settings,jid) if provider_name=='openai' else GeminiProvider(settings,jid) if provider_name=='gemini' else LocalProvider()
            if provider_name in ('gemini','openai'):
                with self.ai:
                    candidates = provider.analyze(source,transcript,opts,scenes,jid)
            else:
                candidates = provider.analyze(source,transcript,opts,scenes,jid)
            db.execute('INSERT INTO analysis VALUES(?,?,?,?,?,?)',
                       (db.uid(),source['id'],key,provider_name,CandidateList(candidates=candidates).model_dump_json(),time.time()))
        stage('Scoring', 92)
        for candidate in candidates:
            if db.one('SELECT id FROM deleted_clips WHERE id=?',(candidate.clip_id,)):
                continue
            candidate.validate_duration(source['duration'])
            data = candidate.model_dump()
            db.execute('INSERT OR IGNORE INTO clips(id,source_id,title,start,end,score,provider,data,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                       (candidate.clip_id,source['id'],candidate.title,candidate.start_seconds,candidate.end_seconds,score(candidate.scores),provider_name,db.dump(data),time.time()))
            db.execute('INSERT OR IGNORE INTO scores VALUES(?,?)',(candidate.clip_id,db.dump(candidate.scores.model_dump())))
        checkpoint('analysis',key)
        db.execute("UPDATE sources SET status='Analyzed' WHERE id=?",(source['id'],))
        db.log(jid,f'{len(candidates)} candidates. Scores are editorial heuristics, not view predictions.')

    def render(self, job, source):
        payload = json.loads(job['payload'])
        transcript_row = db.one('SELECT data FROM transcripts WHERE source_id=?',(source['id'],))
        transcript = json.loads(transcript_row['data']) if transcript_row else {'segments':[]}
        output = DATA / 'renders' / f'{job["clip_id"]}-r{payload["revision"]}-{job["id"][:8]}.mp4'
        try:
            qc = render(source,transcript,payload['plan'],job['id'],output,self.ffmpeg,payload.get('audio_settings'))
            check_job(job['id'])
            db.execute('UPDATE render_tasks SET qc=? WHERE job_id=?',(db.dump(qc),job['id']))
            # A render may finish after another edit: preserve its revision explicitly.
            db.execute('UPDATE clips SET render_path=?,render_revision=? WHERE id=?',
                       (str(output.relative_to(DATA)),payload['revision'],job['clip_id']))
            checkpoints=json.loads(db.one('SELECT checkpoints FROM jobs WHERE id=?',(job['id'],))['checkpoints'])
            db.job_update(job['id'],checkpoints=db.dump({**checkpoints,'output_path':str(output.relative_to(DATA))}))
            db.log(job['id'],'QC passed: full decode, geometry, duration, FPS, audio timeline')
        except BaseException:
            output.unlink(missing_ok=True)
            output.with_suffix('.srt').unlink(missing_ok=True)
            output.with_suffix('.ass').unlink(missing_ok=True)
            raise

def enqueue(kind, source_id, payload, clip_id=None):
    with db.WRITE_LOCK, db.connect() as c:
        return enqueue_tx(c,kind,source_id,payload,clip_id)

def enqueue_tx(c,kind,source_id,payload,clip_id=None):
    existing = c.execute("SELECT id FROM jobs WHERE kind=? AND source_id=? AND COALESCE(clip_id,'')=? AND status IN ('Queued','Running','Paused')",
                         (kind,source_id,clip_id or '')).fetchone()
    if existing:
        return existing['id']
    jid, now = db.uid(), time.time()
    c.execute('INSERT INTO jobs(id,source_id,clip_id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
              (jid,source_id,clip_id,kind,'Queued',db.dump(payload),now,now))
    if kind=='render':
        c.execute('INSERT INTO render_tasks(job_id,plan) VALUES(?,?)',(jid,db.dump(payload['plan'])))
    return jid

def default_plan(clip):
    from backend.subtitles import PRESETS
    s = db.settings()
    sub = SubtitleStyle(preset=s['subtitle_preset'],**PRESETS.get(s['subtitle_preset'],{}))
    return EditPlan(segments=[{'start':clip['start'],'end':clip['end']}], aspect=s['aspect'], fps=s['fps'],
                    crop_mode=s['crop_mode'], encoder=s['encoder'],quality=s['render_quality'],subtitles=sub)
