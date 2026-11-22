"""One cancellable yt-dlp process, bounded progress JSON and local media only."""
import json
import shutil
import sys
import time
from pathlib import Path
from yt_dlp import YoutubeDL

def write_json(path,data):
    temporary=path.with_suffix('.pending')
    temporary.write_text(json.dumps(data,ensure_ascii=False))
    temporary.replace(path)

def main():
    request=Path(sys.argv[1])
    config=json.loads(request.read_text())
    work=request.parent
    progress=work/'progress.json'
    limit=int(config['max_bytes'])
    reserve=int(config['reserve_mb'])*1024**2
    began=time.monotonic()
    last_write=0
    completed=0
    estimated_total=0
    def hook(data):
        nonlocal last_write,completed
        downloaded=int(data.get('downloaded_bytes') or 0)
        if downloaded+completed>limit:
            raise ValueError('Видео превышает установленный лимит размера файла')
        now=time.monotonic()
        if now-last_write<.5 and data['status']!='finished':return
        last_write=now
        if shutil.disk_usage(work).free<reserve:
            raise ValueError('Недостаточно свободного места для продолжения скачивания')
        total=data.get('total_bytes') or data.get('total_bytes_estimate')
        fraction=min((completed+downloaded)/estimated_total,1) if estimated_total else min(downloaded/total,1) if total else 0
        write_json(progress,{'stage':'Скачивание видео','progress':10+fraction*65,
                   'downloaded_bytes':completed+downloaded,'total_bytes':estimated_total or (completed+total if total else None),
                   'speed':data.get('speed'),'eta':data.get('eta'),'elapsed':now-began})
        if data['status']=='finished':completed+=downloaded
    def postprocess(data):
        write_json(progress,{'stage':'Объединение аудио и видео','progress':82})
    def match(info,*,incomplete=False):
        nonlocal estimated_total
        if incomplete:return None
        if info.get('is_live') or info.get('has_drm'):return 'Прямые эфиры и DRM не поддерживаются'
        duration=float(info.get('duration') or 0)
        if not 0<duration<86400:return 'Не удалось определить длительность видео (лимит — 24 часа)'
        requested=info.get('requested_formats') or [info]
        estimate=sum(f.get('filesize') or f.get('filesize_approx') or 0 for f in requested)
        estimated_total=max(estimated_total,estimate)
        if estimate>limit:return 'Видео превышает установленный лимит размера файла'
        # Leave room for separate streams and the merged output.
        if shutil.disk_usage(work).free<reserve+2*(estimate or min(limit,int(duration*1_000_000))):
            return 'Недостаточно места для скачивания и объединения исходника'
        write_json(progress,{'stage':'Получение исходника','progress':8,'title':str(info.get('title') or '')[:300]})
        return None
    node=shutil.which('node')
    if not node:raise ValueError('Для YouTube нужен установленный Node.js 22 или новее')
    opts={'noplaylist':True,'geo_bypass':False,'quiet':True,'socket_timeout':20,'retries':3,'fragment_retries':3,
          'concurrent_fragment_downloads':1,'sleep_interval_requests':1,'sleep_interval':2,'max_sleep_interval':4,
          'http_chunk_size':10*1024*1024,
          'js_runtimes':{'node':{'path':node}},'cachedir':str(work/'cache'),
          'outtmpl':str(work/'source.%(ext)s'),'merge_output_format':'mp4',
          'format':'bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/b[height<=1080][vcodec^=avc1]/bv*[height<=1080]+ba/b[height<=1080]',
          'max_filesize':limit,'match_filter':match,'progress_hooks':[hook],'postprocessor_hooks':[postprocess]}
    if config.get('cookie_file'):opts['cookiefile']=config['cookie_file']
    write_json(progress,{'stage':'Проверка доступа к видео','progress':2})
    with YoutubeDL(opts) as ydl:
        info=ydl.extract_info(config['url'],download=True)
    if not info:raise ValueError('YouTube не вернул доступный исходник')
    files=[p for p in work.glob('source.*') if p.suffix.lower() in ('.mp4','.mkv','.webm','.mov')]
    if len(files)!=1:raise ValueError('Не найден объединённый видеофайл после скачивания')
    if files[0].stat().st_size>limit:raise ValueError('Скачанный файл превышает лимит размера')
    write_json(work/'result.json',{'file':files[0].name,'title':str(info.get('title') or 'YouTube')[:300],
               'duration':info.get('duration'),'id':info.get('id'),'uploader':str(info.get('uploader') or '')[:300],
               'license':str(info.get('license') or '')[:500]})

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
