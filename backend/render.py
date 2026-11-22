import json
import math
import shutil
from pathlib import Path
from . import db
from .config import DATA, FFMPEG, safe_path
from .media import run, probe, check_space, check_job
from .schemas import EditPlan, Segment
from .subtitles import remap_words, export_text, raster_captions
from .metadata import output_options,audit

SIZES = {'9:16': (1080,1920), '1:1': (1080,1080), '4:5': (1080,1350), '16:9': (1920,1080)}

def remove_long_pauses(plan, transcript):
    from .analysis import transcript_words
    words = transcript_words(transcript)
    if not words:
        raise ValueError('Для удаления пауз нужны word timestamps')
    result = []
    for s in plan.segments:
        inside = [w for w in words if w['start'] >= s.start and w['end'] <= s.end]
        cursor = s.start
        for a, b in zip(inside, inside[1:]):
            if b['start'] - a['end'] > 1.1:
                result.append(Segment(start=cursor, end=min(s.end, a['end'] + .2)))
                cursor = max(cursor, b['start'] - .15)
        if cursor < s.end:
            result.append(Segment(start=cursor, end=s.end))
    if len(result) > 50:
        raise ValueError('Более 50 монтажных сегментов: сократите клип')
    return result

def smart_crop(source_path, segment, width, height, job_id):
    import cv2
    face = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    cap = cv2.VideoCapture(str(source_path))
    points = []
    crop_ratio = width / height
    try:
        pos = segment.start
        previous = None
        while pos < segment.end:
            check_job(job_id)
            cap.set(cv2.CAP_PROP_POS_MSEC, pos * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            factor = min(1, 640 / w)
            small = cv2.resize(frame, (round(w * factor), round(h * factor)))
            faces = face.detectMultiScale(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 1.15, 4, minSize=(28,28))
            if len(faces):
                # Largest detected face, not a claim of speaker diarization.
                x, y, fw, fh = max(faces, key=lambda f: f[2]*f[3])
                if fw / factor * 1.5 > min(w, h * crop_ratio):
                    return None
                target = (x + fw / 2) / factor / w
                previous = target if previous is None else previous * .78 + target * .22
                points.append((pos - segment.start, previous))
            pos += max(.5, (segment.end - segment.start) / 50)
    finally:
        cap.release()
    if not points:
        return None
    # Smooth linear interpolation avoids crop jumps; max 50 samples keeps filters bounded.
    expr = f'{points[-1][1]:.5f}'
    for (t1, x1), (t2, x2) in reversed(list(zip(points, points[1:]))):
        slope = (x2 - x1) / max(.001, t2 - t1)
        value = f'({x1:.5f}+{slope:.6f}*(t-{t1:.5f}))'
        expr = f'if(lt(t,{t2:.5f}),{value},{expr})'
    return expr

def video_filter(label, out, mode, width, height, plan, x_expr=None):
    if mode == 'blur':
        return (f'[{label}]split=2[bg{out}][fg{out}];'
                f'[bg{out}]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=20:2[blur{out}];'
                f'[fg{out}]scale={width}:{height}:force_original_aspect_ratio=decrease[fit{out}];'
                f'[blur{out}][fit{out}]overlay=(W-w)/2:(H-h)/2,setsar=1[{out}]')
    if mode == 'split':
        return (f'[{label}]format=yuv444p,split=2[left{out}][right{out}];'
                f'[left{out}]crop=iw/2:ih:0:0,scale={width}:{height//2}:force_original_aspect_ratio=increase,crop={width}:{height//2}[a{out}];'
                f'[right{out}]crop=iw/2:ih:iw/2:0,scale={width}:{height//2}:force_original_aspect_ratio=increase,crop={width}:{height//2}[b{out}];'
                f'[a{out}][b{out}]vstack=inputs=2,setsar=1[{out}]')
    cx = x_expr or str(plan.crop_x if mode == 'manual' else .5)
    cy = plan.crop_y if mode == 'manual' else .5
    return (f'[{label}]scale={width}:{height}:force_original_aspect_ratio=increase,'
            f"crop={width}:{height}:x='max(0,min(iw-ow,iw*({cx})-ow/2))':y='max(0,min(ih-oh,ih*{cy}-oh/2))',setsar=1[{out}]")

def render(source, transcript, plan_data, job_id, destination, ffmpeg_sem, audio_settings=None):
    plan = EditPlan.model_validate(plan_data).validate_source(source['duration'])
    if not source.get('path'):
        raise ValueError('Для монтажа нужен локальный исходник. URL-анализ не скачивает видео.')
    width, height = SIZES[plan.aspect]
    if plan.remove_pauses:
        plan.segments = remove_long_pauses(plan, transcript)
    duration = sum(s.end - s.start for s in plan.segments)
    check_space(int(duration * 3_000_000), db.settings()['min_free_mb'])
    folder = DATA / 'temp' / job_id
    folder.mkdir(parents=True, exist_ok=True)
    source_path = safe_path(source['path'])
    warnings = []
    caption_transcript = {'segments':[{'words':[w.model_dump() for w in plan.caption_words]}]} if plan.caption_words is not None else transcript
    words = remap_words(caption_transcript, plan.segments)
    replacement=None;audio_report=None
    original_audio=bool(source['has_audio']) and plan.audio_replacement.mode=='original'
    if plan.audio_replacement.mode!='original':
        from .audio_replacement import prepare_audio
        try:
            job=db.one('SELECT clip_id FROM jobs WHERE id=?',(job_id,))
            replacement,new_words,audio_report=prepare_audio(job['clip_id'] or job_id,plan,transcript,duration,job_id,ffmpeg_sem,audio_settings or db.settings())
            if plan.audio_replacement.mode=='music_voice': words=new_words
        except BaseException:
            shutil.rmtree(folder,ignore_errors=True);raise
    if plan.subtitles.enabled and not words:
        raise ValueError('Нет word timestamps для субтитров. Выполните локальную транскрибацию или отключите субтитры явно.')
    export_text(words, plan.subtitles, width, height, destination)
    try:
        filters = []
        n = len(plan.segments)
        if n > 1:
            filters.append('[0:v]split=' + str(n) + ''.join(f'[sv{i}]' for i in range(n)))
            if original_audio:
                filters.append('[0:a]asplit=' + str(n) + ''.join(f'[sa{i}]' for i in range(n)))
        for i, segment in enumerate(plan.segments):
            check_job(job_id)
            db.job_update(job_id, stage='Preparing', progress=15 + 15*i/n)
            mode, x = plan.crop_mode, None
            if mode == 'smart':
                x = smart_crop(source_path, segment, width, height, job_id)
                if not x:
                    mode = plan.smart_fallback
                    warnings.append('Face tracking unavailable or face too wide: '+mode+' fallback')
                else:
                    warnings.append('Smart crop tracks the largest detected face; active speaker and objects are not identified')
            vlabel = f'sv{i}' if n > 1 else '0:v'
            filters.append(f'[{vlabel}]trim=start={segment.start}:end={segment.end},setpts=PTS-STARTPTS,fps={plan.fps}[trim{i}]')
            filters.append(video_filter(f'trim{i}', f'v{i}', mode, width, height, plan, x))
            if original_audio:
                alabel = f'sa{i}' if n > 1 else '0:a'
                filters.append(f'[{alabel}]atrim=start={segment.start}:end={segment.end},asetpts=PTS-STARTPTS,aresample=48000[a{i}]')
        if original_audio:
            filters.append(''.join(f'[v{i}][a{i}]' for i in range(n)) + f'concat=n={n}:v=1:a=1[video][sound]')
            audio = ['anull']
            if plan.denoise:
                audio.append('afftdn=nf=-25')
            if plan.normalize_audio:
                audio.append('loudnorm=I=-16:TP=-1.5:LRA=11')
            audio.extend([f'volume={plan.volume}', 'aresample=48000', 'alimiter=limit=.97'])
            filters.append('[sound]' + ','.join(audio) + '[audio]')
        else:
            filters.append(''.join(f'[v{i}]' for i in range(n)) + f'concat=n={n}:v=1:a=0[video]')
            if not replacement: warnings.append('Source has no audio; exported without an audio track')
        args = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', source_path]
        if replacement:
            args+=['-i',replacement]
            filters.append(f'[1:a]atrim=duration={duration},asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11,volume={plan.volume},aresample=48000,alimiter=limit=.97[audio]')
            warnings.append('Original soundtrack excluded. New audio does not certify copyright clearance of the video.')
        if plan.subtitles.enabled:
            captions = raster_captions(words, plan.subtitles, width, height, duration, folder / 'captions', job_id)
            args += ['-f', 'concat', '-safe', '0', '-i', captions]
            filters.append(f'[{2 if replacement else 1}:v]fps={plan.fps},format=rgba[subs]')
            filters.append('[video][subs]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[out]')
        else:
            filters.append('[video]format=yuv420p[out]')
        script = folder / 'render.ffscript'
        script.write_text(';\n'.join(filters))
        # FFmpeg 9 removed filter_complex_script. Passing the graph as one argv
        # value is supported by both old/new releases and never invokes a shell.
        args += ['-filter_complex', script.read_text(), '-filter_complex_threads', '2', '-map', '[out]']
        if original_audio or replacement:
            args += ['-map', '[audio]', '-c:a', 'aac', '-b:a', '192k']
        args += ['-t', duration, '-r', plan.fps, '-movflags', '+faststart', '-pix_fmt', 'yuv420p',*output_options()]
        db.job_update(job_id, stage='Rendering', progress=40)
        db.log(job_id, f'Rendering {duration:.2f}s, {width}×{height}, {plan.fps}fps; RGBA subtitle engine')
        with ffmpeg_sem:
            check_job(job_id)
            if plan.encoder in ('auto', 'videotoolbox'):
                try:
                    run(args + ['-c:v', 'h264_videotoolbox', '-b:v', '8M', '-allow_sw', '0', destination], job_id)
                    encoder = 'h264_videotoolbox'
                except RuntimeError:
                    if plan.encoder == 'videotoolbox':
                        raise
                    db.log(job_id, 'VideoToolbox unavailable for this plan; using libx264')
                    run(args + ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', plan.quality, '-threads', '2', destination], job_id)
                    encoder = 'libx264'
            else:
                run(args + ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', plan.quality, '-threads', '2', destination], job_id)
                encoder = 'libx264'
        db.job_update(job_id, stage='Quality check', progress=88)
        qc = quality_check(destination, duration, width, height, plan.fps, bool(original_audio or replacement), job_id)
        qc.update({'warnings': list(dict.fromkeys(warnings)), 'encoder': encoder, 'subtitle_engine': 'Pillow RGBA + FFmpeg overlay',
                   'word_count': len(words), 'semantic_review': 'Manual review required; semantic accuracy is not automatically certified',
                   'segments': [s.model_dump() for s in plan.segments]})
        if audio_report: qc['audio_replacement']=audio_report
        qc.update(audit(probe(destination)['raw']))
        if not qc['metadata_clean']:
            raise ValueError('Выходной MP4 содержит непредусмотренные метаданные')
        return qc
    finally:
        shutil.rmtree(folder, ignore_errors=True)

def quality_check(path, duration, width, height, fps, audio, job_id=None):
    if not path.exists() or path.stat().st_size < 1000:
        raise ValueError('Render file missing or empty')
    info = probe(path)
    videos = [s for s in info['raw']['streams'] if s['codec_type']=='video']
    audios = [s for s in info['raw']['streams'] if s['codec_type']=='audio']
    if not videos or videos[0].get('codec_name')!='h264' or (audio and (not audios or audios[0].get('codec_name')!='aac')):
        raise ValueError('Output must contain H.264 video and expected AAC audio')
    if (info['width'],info['height']) != (width,height):
        raise ValueError('Output resolution mismatch')
    if abs(info['duration'] - duration) > max(.18, 2/fps):
        raise ValueError('Output duration mismatch')
    if abs(info['fps'] - fps) > .1 or bool(info['has_audio']) != audio:
        raise ValueError('Output FPS/audio mismatch')
    starts, ends = [], []
    for stream in info['raw']['streams']:
        if stream['codec_type'] in ('video','audio'):
            start = float(stream.get('start_time',0))
            starts.append(start)
            ends.append(start + float(stream.get('duration',info['duration'])))
    if max(starts)-min(starts) > .15 or max(ends)-min(ends) > .2:
        raise ValueError('Audio/video timeline mismatch exceeds 200ms')
    # Decode every frame including beginning and end; fail on actual decoder errors.
    run([FFMPEG, '-hide_banner', '-v', 'error', '-xerror', '-i', path, '-f', 'null', '-'], job_id)
    return {'passed': True, 'duration': info['duration'], 'width': width, 'height': height, 'fps': info['fps'],
            'has_audio': bool(info['has_audio']), 'size': path.stat().st_size, 'full_decode': True,
            'av_end_difference': round(max(ends)-min(ends),4)}
