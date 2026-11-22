"""New instrumental compositions and optional verbatim TTS, never an original-audio fallback."""
import hashlib
import json
import math
import re
import time

import httpx
from . import db
from .config import DATA,FFMPEG,FFPROBE,secret,redact
from .media import check_job,check_space,run
from .subtitles import remap_words
from .integrations import LOCK,voice_preview,usage_summary

MUSIC_TERMS='https://elevenlabs.io/music-terms'

def spec(clip_id,plan,settings,duration):
    prompt=('Create an independent original instrumental composition, not a recreation of any existing song, melody or recording. '
            'No vocals or spoken words. Mood, tempo and instrumentation brief: '+plan.audio_replacement.music_prompt)
    value={'prompt':prompt,'music_length_ms':max(3000,math.ceil(duration*1000)),
           'model_id':settings['music_model'],'force_instrumental':True}
    digest=hashlib.sha256(db.dump(['music-v1',clip_id,value]).encode()).hexdigest()
    return value,digest

def music_stats():
    return db.one('SELECT COUNT(*) requests,COALESCE(SUM(seconds),0) seconds FROM music_usage')

def speech_text(transcript,plan):
    material={'segments':[{'words':[w.model_dump() for w in plan.caption_words]}]} if plan.caption_words is not None else transcript
    words=remap_words(material,plan.segments)
    return ' '.join(word['word'] for word in words).strip(),words

def preflight(plans,settings):
    """All selected items are checked before the batch mutates projects or queues jobs."""
    from .schemas import EditPlan
    plans=list(plans)
    requested={item[0] for item in plans}
    # Account for earlier queued batches too; a new batch cannot spend their allowance.
    for job in db.rows("SELECT clip_id,source_id,payload FROM jobs WHERE kind='render' AND status IN ('Queued','Running','Paused')"):
        if job['clip_id'] in requested: continue
        payload=json.loads(job['payload'])
        if not payload.get('plan') or payload['plan'].get('audio_replacement',{}).get('mode','original')=='original': continue
        plan=EditPlan.model_validate(payload['plan'])
        row=db.one('SELECT data FROM transcripts WHERE source_id=?',(job['source_id'],))
        plans.append((job['clip_id'],plan,json.loads(row['data']) if row else {'segments':[]},sum(s.end-s.start for s in plan.segments)))
        requested.add(job['clip_id'])
    music_count=0;music_seconds=0;voice_count=0
    for clip_id,plan,transcript,duration in plans:
        audio=plan.audio_replacement
        if audio.mode=='original': continue
        if not audio.consent: raise ValueError('Подтвердите отправку текста/запроса и генерацию аудио ElevenLabs')
        if not secret('elevenlabs'): raise ValueError('Добавьте ключ ElevenLabs в Настройки → Озвучка')
        if duration>180: raise ValueError('Замена аудио пока поддерживает ролики до 180 секунд')
        if plan.remove_pauses:
            from .render import remove_long_pauses
            plan=plan.model_copy(deep=True);plan.segments=remove_long_pauses(plan,transcript)
            duration=sum(s.end-s.start for s in plan.segments)
        _,digest=spec(clip_id,plan,settings,duration)
        if not all((DATA/'audio-replacements'/f'music-{digest}{suffix}').exists() for suffix in ('.mp3','.json')):
            music_count+=1;music_seconds+=max(3,duration)
        if audio.mode=='music_voice':
            text,words=speech_text(transcript,plan)
            if not text: raise ValueError('Для переозвучки нужны распознанные слова. Выполните анализ или выберите режим только музыки.')
            if len(text)>1200: raise ValueError('В одном клипе более 1200 символов речи. Сократите клип для переозвучки.')
            if not settings['elevenlabs_voice_id']: raise ValueError('Укажите Voice ID в Настройки → Озвучка')
            digest=hashlib.sha256(db.dump(['voice-v1',text,settings['elevenlabs_voice_id'],settings['elevenlabs_model']]).encode()).hexdigest()
            if not all((DATA/'previews'/'voices'/f'{digest}{suffix}').exists() for suffix in ('.mp3','.json')): voice_count+=1
    if not music_count and not voice_count: return
    stats=music_stats()
    if stats['requests']+music_count>settings['music_request_limit']:
        raise ValueError(f'Нужно до {music_count} новых музыкальных дорожек; остаток лимита {max(0,settings["music_request_limit"]-stats["requests"])}. Настройки → Озвучка → Eleven Music.')
    if stats['seconds']+music_seconds>settings['music_seconds_limit']:
        raise ValueError(f'Нужно до {math.ceil(music_seconds)} секунд музыки; остаток лимита {max(0,math.floor(settings["music_seconds_limit"]-stats["seconds"]))}. Увеличьте лимит в настройках после проверки тарифа.')
    used=usage_summary('elevenlabs')['requests']
    if used+voice_count>settings['elevenlabs_request_limit']:
        raise ValueError(f'Нужно до {voice_count} переозвучек; остаток лимита {max(0,settings["elevenlabs_request_limit"]-used)}. Увеличьте лимит генераций ElevenLabs в настройках.')

def generate_music(clip_id,plan,settings,duration,job_id):
    payload,digest=spec(clip_id,plan,settings,duration)
    return compose_music(payload,digest,settings,duration,job_id)

def compose_music(payload,digest,settings,duration,job_id):
    """One paid Eleven Music request with local limits, usage accounting and a digest cache.
    A paid, validated result is kept even if the job is paused; failures are never retried automatically."""
    folder=DATA/'audio-replacements';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'music-{digest}.mp3';manifest=path.with_suffix('.json')
    with LOCK:
        check_job(job_id)
        if path.exists() and manifest.exists(): return path,json.loads(manifest.read_text())
        key=secret('elevenlabs')
        if not key: raise ValueError('Ключ ElevenLabs не подключён')
        current={**settings,**db.settings()}
        used=music_stats();seconds=payload['music_length_ms']/1000
        if used['requests']>=current['music_request_limit'] or used['seconds']+seconds>current['music_seconds_limit']:
            raise ValueError('Достигнут лимит генераций/секунд Eleven Music. Исходный звук не будет использован вместо новой дорожки.')
        check_space(10*1024**2)
        uid=db.uid();temporary=path.with_suffix('.pending.mp3')
        db.execute('INSERT INTO music_usage VALUES(?,?,?,?,?,?)',(uid,payload['model_id'],seconds,'attempted',job_id,time.time()))
        try:
            with httpx.Client(timeout=httpx.Timeout(300,connect=15),follow_redirects=False) as client:
                with client.stream('POST','https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128',headers={'xi-api-key':key},json=payload) as response:
                    if not response.is_success:
                        body=response.read()
                        try:
                            detail=json.loads(body).get('detail',{})
                            message=detail.get('message',str(detail)) if isinstance(detail,dict) else str(detail)
                        except ValueError: message='Проверьте право Music Generation, подписку и баланс ElevenLabs'
                        raise ValueError(redact(f'Eleven Music HTTP {response.status_code}: {message}'))
                    total=0
                    with temporary.open('wb') as stream:
                        for chunk in response.iter_bytes():
                            total+=len(chunk)
                            if total>12*1024**2: raise ValueError('Eleven Music вернул слишком большой файл')
                            stream.write(chunk)
                    song_id=response.headers.get('song-id')
            if temporary.stat().st_size<1000: raise ValueError('Eleven Music вернул пустой файл')
            actual=float(run([FFPROBE,'-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',temporary],timeout=20))
            if not math.isfinite(actual) or actual<max(1,duration-2) or actual>duration+20:
                raise ValueError('Длительность новой музыки не соответствует заказу')
            run([FFMPEG,'-v','error','-xerror','-i',temporary,'-f','null','-'],timeout=90)
            record={'provider':'Eleven Music','model':payload['model_id'],'song_id':song_id,'prompt':payload['prompt'],
                    'requested_seconds':seconds,'actual_seconds':actual,'terms_url':MUSIC_TERMS,'created_at':time.time(),
                    'rights_note':'Использование по условиям тарифа ElevenLabs; отсутствие претензий не гарантируется.'}
            pending=manifest.with_suffix('.tmp');pending.write_text(db.dump(record),encoding='utf-8');pending.replace(manifest)
            temporary.replace(path)
            db.execute("UPDATE music_usage SET status='completed' WHERE id=?",(uid,))
        except httpx.HTTPError:
            db.execute("UPDATE music_usage SET status='failed' WHERE id=?",(uid,))
            raise ValueError('Eleven Music: ошибка сети. Автоматического повтора платного запроса нет.') from None
        except BaseException:
            db.execute("UPDATE music_usage SET status='failed' WHERE id=?",(uid,));raise
        finally: temporary.unlink(missing_ok=True)
        check_job(job_id)
        return path,record

def alignment_words(alignment,offset=0,rate=1):
    chars=alignment['characters'];text=''.join(chars)
    starts=alignment['character_start_times_seconds'];ends=alignment['character_end_times_seconds']
    return [{'word':match.group(),'start':offset+starts[match.start()]/rate,'end':offset+ends[match.end()-1]/rate} for match in re.finditer(r'\S+',text)]

def prepare_audio(clip_id,plan,transcript,duration,job_id,ffmpeg_sem,settings):
    """Render a new WAV and output-timeline captions. Original sound is never an input."""
    audio=plan.audio_replacement
    preflight([(clip_id,plan,transcript,duration)],settings)
    folder=DATA/'temp'/job_id
    folder.mkdir(parents=True,exist_ok=True)
    voice=None;voice_meta=None;words=[];offset=0;rate=1
    if audio.mode=='music_voice':
        text,original_words=speech_text(transcript,plan)
        db.job_update(job_id,stage='Переозвучка ElevenLabs',progress=5)
        voice_meta=voice_preview(text,settings)
        voice=DATA/'previews'/'voices'/(voice_meta['url'].rsplit('/',1)[-1]+'.mp3')
        offset=min(original_words[0]['start'],max(0,duration-.5))
        available=duration-offset
        rate=max(1,voice_meta['duration']/available)
        if rate>1.4: raise ValueError('Новая речь не помещается в клип без чрезмерного ускорения. Сократите текст/увеличьте границы или выберите только музыку.')
        words=alignment_words(voice_meta['alignment'],offset,rate)
        words=[{**w,'end':min(duration,w['end'])} for w in words if w['start']<duration and min(duration,w['end'])>w['start']]
        check_job(job_id)
    db.job_update(job_id,stage='Новая музыка Eleven Music',progress=10)
    music,record=generate_music(clip_id,plan,settings,duration,job_id)
    destination=folder/'replacement.wav'
    args=[FFMPEG,'-v','error','-y','-i',music]
    filters=[f'[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={duration},afade=t=in:d=0.15,afade=t=out:st={max(0,duration-.4)}:d=0.4,volume={audio.music_volume}[music]']
    if voice:
        args+=['-i',voice]
        filters.append(f'[1:a]aresample=48000,aformat=channel_layouts=stereo,atempo={rate},adelay={round(offset*1000)}:all=1,apad,atrim=duration={duration},volume={audio.voice_volume}[voice]')
        filters.append('[music][voice]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=.95[mix]')
    else: filters.append('[music]alimiter=limit=.95[mix]')
    with ffmpeg_sem:
        run(args+['-filter_complex',';'.join(filters),'-map','[mix]','-t',duration,'-c:a','pcm_s16le',destination],job_id,timeout=90)
    check_job(job_id)
    return destination,words,{'mode':audio.mode,'original_audio_included':False,'music':record,
                              'voice_id':settings['elevenlabs_voice_id'] if voice else None,'voice_rate':rate,
                              'note':'Новая музыка и выбранный голос. Исходные эффекты/интонации не сохраняются. Претензии к видеоряду возможны.'}
