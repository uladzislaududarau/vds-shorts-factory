"""Resolve the exact owned output of a completed job and reveal it in Finder / Explorer."""
import json
import re
import subprocess
import sys
from . import db
from .config import safe_path

def output_path(job):
    if job['status']!='Completed': return None
    checkpoints=json.loads(job.get('checkpoints') or '{}')
    payload=json.loads(job.get('payload') or '{}')
    relative=None
    if job['kind']=='render':
        relative=checkpoints.get('output_path')
        if not relative:
            cid=job.get('clip_id');revision=payload.get('revision')
            if not isinstance(cid,str) or not re.fullmatch('[0-9a-f]{32}',cid): return None
            if not isinstance(revision,int) or revision<1: return None
            relative=f'renders/{cid}-r{revision}-{job["id"][:8]}.mp4'
        folder,suffixes='renders',('.mp4',)
    elif job['kind']=='montage':
        relative=checkpoints.get('output_path')
        folder,suffixes='renders',('.mp4',)
    elif job['kind']=='export':
        url=checkpoints.get('download_url','')
        match=re.fullmatch(r'/api/exports/([0-9a-f]{32})',url) if isinstance(url,str) else None
        if not match: return None
        relative=f'exports/{match[1]}.zip'
        folder,suffixes='exports',('.zip',)
    elif job['kind']=='download':
        source=db.one('SELECT path FROM sources WHERE id=?',(job.get('source_id') or checkpoints.get('download_source_id'),))
        if not source: return None
        relative=source['path']
        folder,suffixes='sources',('.mp4','.mov','.mkv','.webm')
    else: return None
    if not isinstance(relative,str): return None
    try:
        path=safe_path(relative)
        allowed=safe_path(folder)
        if not path.is_relative_to(allowed) or path.suffix.lower() not in suffixes or not path.is_file(): return None
        return path
    except (ValueError,OSError): return None

def output_info(job):
    path=output_path(job)
    if path is None: return None
    return {'filename':path.name,'path':str(path),'download_url':f'/api/jobs/{job["id"]}/file'}

def reveal(path):
    if sys.platform=='win32':
        # explorer.exe returns 1 even on success, so its exit code is not checked.
        try: subprocess.run(['explorer',f'/select,{path}'],timeout=10,check=False)
        except (OSError,subprocess.TimeoutExpired): raise ValueError('Не удалось открыть Проводник.') from None
        return
    if sys.platform.startswith('linux'):
        # Linux file managers differ; xdg-open shows the folder that contains the file.
        try: subprocess.run(['xdg-open',str(path.parent)],timeout=10,check=False,capture_output=True)
        except (OSError,subprocess.TimeoutExpired): raise ValueError('Не удалось открыть папку с файлом.') from None
        return
    if sys.platform!='darwin': raise ValueError('Показать файл в папке на этой системе не поддерживается')
    try:
        result=subprocess.run(['/usr/bin/open','-R',str(path)],capture_output=True,text=True,timeout=10,check=False)
    except (OSError,subprocess.TimeoutExpired):
        raise ValueError('Не удалось открыть Finder. Повторите действие в активной сессии macOS.') from None
    if result.returncode:
        raise ValueError('Finder не открыл файл. Проверьте, что активна ваша сессия macOS.')
