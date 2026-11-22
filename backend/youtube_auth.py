"""Explicit local YouTube session connection; never return cookie values to HTTP."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .config import ROOT
from .media import run

SECRET_DIR=ROOT/'.secrets/youtube'
CHROME=Path('/Applications/Google Chrome.app')
LOCK=threading.RLock()
SESSION_VERSION=0
AUTH_NAMES={'SID','__Secure-1PSID','__Secure-3PSID','LOGIN_INFO','SAPISID','__Secure-3PAPISID'}

def prepare():
    SECRET_DIR.mkdir(mode=0o700,parents=True,exist_ok=True)
    SECRET_DIR.chmod(0o700)

def profile_path():
    return SECRET_DIR/'browser'

def status():
    try:
        meta=json.loads((SECRET_DIR/'session.json').read_text())
    except (OSError,ValueError):
        meta={}
    connected=(SECRET_DIR/'cookies.txt').is_file()
    return {'connected':connected,'browser_available':CHROME.is_dir(),
            'browser':'Google Chrome','updated_at':meta.get('updated_at') if connected else None,
            'cookie_count':meta.get('cookie_count',0) if connected else 0,
            'method':meta.get('method') if connected else None,
            'note':'Сессия сохранена локально. Доступ к выбранному видео проверяется при скачивании.' if connected else 'Войдите в YouTube и подключите сессию.'}

def open_login():
    if not CHROME.is_dir():
        raise ValueError('Для отдельного окна входа нужен Google Chrome. Можно подключить cookies.txt во вкладке YouTube.')
    prepare()
    profile_path().mkdir(mode=0o700,exist_ok=True)
    profile_path().chmod(0o700)
    subprocess.run(['/usr/bin/open','-na',str(CHROME),'--args',
                    '--user-data-dir='+str(profile_path()),'--no-first-run','--no-default-browser-check',
                    '--new-window','https://www.youtube.com/'],check=True,timeout=20)
    return {'opened':True,'note':'Войдите в YouTube в отдельном окне Chrome. Затем нажмите «Подключить сессию».'}

def filter_cookies(raw):
    if len(raw)>1024*1024:
        raise ValueError('Файл cookies слишком большой (максимум 1 МБ)')
    try: lines=raw.decode('utf-8-sig').splitlines()
    except UnicodeDecodeError: raise ValueError('Нужен текстовый cookies.txt в формате Netscape') from None
    if not lines or lines[0].strip() not in ('# Netscape HTTP Cookie File','# HTTP Cookie File'):
        raise ValueError('Нужен cookies.txt в формате Netscape, экспортированный для youtube.com')
    kept={}
    now=time.time()
    for line in lines[1:]:
        http_only=line.startswith('#HttpOnly_')
        if http_only:line=line[len('#HttpOnly_'):]
        elif not line or line.startswith('#'):continue
        parts=line.split('\t')
        if len(parts)!=7:
            raise ValueError('Неверный формат cookies.txt: ожидаются семь полей, разделённых табуляцией')
        domain,subdomains,cpath,secure,expiry,name,value=parts
        host=domain.lower().lstrip('.')
        if host!='youtube.com' and not host.endswith('.youtube.com'):continue
        if subdomains not in ('TRUE','FALSE') or secure not in ('TRUE','FALSE') or not cpath.startswith('/'):
            raise ValueError('Неверные поля cookies.txt')
        try: expires=int(expiry)
        except ValueError:raise ValueError('Неверный срок действия cookies.txt') from None
        if expires<0 or (expires and expires<=now):continue
        if not name or any(ord(c)<33 or ord(c)>126 or c in ';=' for c in name) or '\x00' in value:
            raise ValueError('Неверное имя или значение cookie')
        kept[(domain,cpath,name)]=('#HttpOnly_' if http_only else '')+'\t'.join(parts)
    if not any(key[2] in AUTH_NAMES for key in kept):
        raise ValueError('Сессия входа YouTube не найдена или истекла. Войдите в аккаунт в отдельном окне и подключите сессию снова.')
    return ('# Netscape HTTP Cookie File\n'+'\n'.join(kept.values())+'\n').encode(),len(kept)

def save_cookies(raw,method):
    global SESSION_VERSION
    sanitized,count=filter_cookies(raw)
    prepare()
    with LOCK:
        fd,temporary=tempfile.mkstemp(prefix='session-',dir=SECRET_DIR)
        try:
            with os.fdopen(fd,'wb') as out:out.write(sanitized)
            os.replace(temporary,SECRET_DIR/'cookies.txt')
        finally:Path(temporary).unlink(missing_ok=True)
        meta=SECRET_DIR/'session.json'
        meta.write_text(json.dumps({'updated_at':time.time(),'cookie_count':count,'method':method}))
        meta.chmod(0o600)
        SESSION_VERSION+=1
    return status()

def connect_managed(job_id=None):
    with LOCK:version=SESSION_VERSION
    prepare()
    if not (profile_path()/'Default').is_dir():
        raise ValueError('Сначала откройте окно входа и войдите в YouTube')
    fd,name=tempfile.mkstemp(prefix='extract-',dir=SECRET_DIR)
    os.close(fd)
    destination=Path(name)
    try:
        run([sys.executable,'-m','workers.youtube_cookies',str(profile_path()/'Default'),destination],timeout=90,job_id=job_id)
        with LOCK:
            if version!=SESSION_VERSION:
                raise ValueError('Сессия изменилась во время подключения. Повторите подключение, если оно ещё нужно.')
            return save_cookies(destination.read_bytes(),'managed_chrome')
    except (RuntimeError,TimeoutError):
        raise ValueError('Не удалось прочитать сессию Chrome. Завершите вход, закройте отдельное окно YouTube и попробуйте снова. Если macOS запросит доступ к Chrome Safe Storage, разрешите его. Также доступен импорт cookies.txt.') from None
    finally:destination.unlink(missing_ok=True)

def disconnect():
    global SESSION_VERSION
    with LOCK:
        for name in ('cookies.txt','session.json'):(SECRET_DIR/name).unlink(missing_ok=True)
        SESSION_VERSION+=1
    return status()

@contextmanager
def cookie_snapshot(use_account,job_id=None):
    if not use_account:
        yield None
        return
    prepare()
    # Browser cookies rotate. Re-read only the explicitly connected, studio-owned
    # profile before a new request; never inspect the user's normal Chrome profile.
    if status()['method']=='managed_chrome':
        connect_managed(job_id)
    with LOCK:
        source=SECRET_DIR/'cookies.txt'
        if not source.is_file():raise ValueError('Подключите сессию YouTube перед скачиванием с аккаунтом')
        sanitized,_=filter_cookies(source.read_bytes())
        fd,name=tempfile.mkstemp(prefix='request-',suffix='.cookies',dir=SECRET_DIR)
        with os.fdopen(fd,'wb') as out:out.write(sanitized)
    try:yield Path(name)
    finally:Path(name).unlink(missing_ok=True)
