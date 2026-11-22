"""Privacy cleanup of editable MP4 tags; technical stream fields stay intact."""
import hashlib
import threading
from .config import DATA,FFMPEG
from .media import run,probe,check_space

LOCK=threading.Lock()
VERSION=1

def output_options():
    return ['-map_metadata','-1','-map_chapters','-1','-fflags','+bitexact',
            '-flags:v','+bitexact','-flags:a','+bitexact',
            '-metadata','encoder=','-metadata:s:v:0','encoder=',
            '-metadata:s:v:0','handler_name=','-metadata:s:a:0','handler_name=',
            '-bsf:v','filter_units=remove_types=6']

def audit(raw):
    unexpected=[]
    for key in raw.get('format',{}).get('tags',{}):
        if key not in ('major_brand','minor_version','compatible_brands'):unexpected.append('format.'+key)
    for stream in raw.get('streams',[]):
        for key,value in stream.get('tags',{}).items():
            if key=='language' and value=='und':continue
            if key=='handler_name' and value in ('VideoHandler','SoundHandler'):continue
            if key=='vendor_id' and value=='[0][0][0][0]':continue
            unexpected.append(f'stream{stream.get("index",0)}.{key}')
    if raw.get('chapters'):unexpected.append('chapters')
    return {'metadata_clean':not unexpected,'metadata_cleanup_version':VERSION,
            'unexpected_metadata_fields':unexpected,
            'metadata_note':'Editable tags removed; technical MP4/codec fields remain. This is not an origin or platform-policy guarantee.'}

def delivery_path(clip,job_id=None):
    from .config import safe_path
    path=safe_path(clip['render_path'])
    qc=clip.get('qc') or {}
    if qc.get('metadata_cleanup_version')==VERSION and qc.get('metadata_clean'):return path
    stat=path.stat()
    digest=hashlib.sha256(f'{path}:{stat.st_size}:{stat.st_mtime_ns}:{VERSION}'.encode()).hexdigest()[:20]
    target=DATA/'exports'/f'clean-{clip["id"]}-{digest}.mp4'
    with LOCK:
        if target.exists():return target
        check_space(stat.st_size)
        temporary=target.with_suffix('.pending.mp4')
        try:
            run([FFMPEG,'-hide_banner','-loglevel','error','-y','-i',path,
                 '-map','0:v:0','-map','0:a:0?','-c','copy',*output_options(),'-movflags','+faststart',temporary],job_id,timeout=300)
            before=probe(path);after=probe(temporary)
            result=audit(after['raw'])
            if not result['metadata_clean'] or abs(before['duration']-after['duration'])>.15:
                raise ValueError('Не удалось проверить очистку метаданных MP4')
            temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
    return target
