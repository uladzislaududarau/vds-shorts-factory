#!/usr/bin/env python3
"""Start and stop only this checkout's owned loopback server."""
import json
import hashlib
import os
import plistlib
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.run/server.json'
URL='http://127.0.0.1:8765'
LABEL='local.ai-shorts-factory.'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
DOMAIN=f'gui/{os.getuid()}' if hasattr(os,'getuid') else ''   # launchd domain (macOS only)
SERVICE=f'{DOMAIN}/{LABEL}'
PLIST=ROOT/'.run'/f'{LABEL}.plist'
BOOT_LOG=Path('/private/tmp')/f'{LABEL}.bootstrap.log'

def service_info():
    result=subprocess.run(['launchctl','print',SERVICE],capture_output=True,text=True)
    return result.stdout if result.returncode==0 else None

def service_definition():
    args=[str(ROOT/'.venv/bin/python'),'-m','uvicorn','backend.main:app',
          '--app-dir',str(ROOT),'--host','127.0.0.1','--port','8765','--no-access-log']
    return {
        'Label':LABEL,
        # launchd cannot itself open this Mac's protected Desktop directory.
        # A system shell performs chdir; paths stay positional argv,
        # never interpolated into shell code. exec preserves launchd's owned PID.
        'ProgramArguments':['/bin/sh','-c',
                            'cd "$1" && shift && exec "$@"',
                            LABEL,str(ROOT),*args],
        'WorkingDirectory':'/private/tmp',
        # .tools/bin holds FFmpeg/FFprobe/Node installed by install.sh; Homebrew copies are used otherwise.
        'EnvironmentVariables':{'PATH':str(ROOT/'.tools/bin')+':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                                'PYTHONUNBUFFERED':'1'},
        'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':5,'ExitTimeOut':15,
        'StandardOutPath':str(BOOT_LOG),
        'StandardErrorPath':str(BOOT_LOG),
        'Umask':0o077,
    }

def record_service(info):
    match=re.search(r'^\s*pid = (\d+)\s*$',info or '',re.MULTILINE)
    STATE.write_text(json.dumps({'pid':int(match[1]) if match else None,'root':str(ROOT),
                                'url':URL,'service':SERVICE}))

def healthy():
    try:
        with urllib.request.urlopen(URL+'/api/health',timeout=2) as r:
            return json.load(r).get('version')=='1.0.0'
    except Exception: return False

def stop_legacy():
    if not STATE.exists():
        print('No owned server recorded.')
        return
    state=json.loads(STATE.read_text())
    pid=state.get('pid')
    if not isinstance(pid,int) or pid<=0:
        STATE.unlink(missing_ok=True)
        return
    # Verify process command and checkout before signalling any PID.
    try:
        command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True).strip()
        if str(ROOT) not in command or 'uvicorn' not in command:
            print('Recorded PID no longer belongs to this server; no process was stopped.')
            STATE.unlink(missing_ok=True)
            return
        os.kill(pid,signal.SIGTERM)
        for _ in range(60):
            try: os.kill(pid,0)
            except ProcessLookupError: break
            time.sleep(.2)
        else:
            # The normal shutdown has already paused and stopped owned media workers.
            # A blocked SDK thread must not keep the local server alive indefinitely.
            try: os.kill(pid,signal.SIGKILL)
            except ProcessLookupError: pass
        print('VDS Shorts Factory stopped. Originals and SQLite preserved.')
    except (ProcessLookupError,subprocess.CalledProcessError):
        print('Server is already stopped.')
    STATE.unlink(missing_ok=True)

def stop():
    if service_info() is not None:
        result=subprocess.run(['launchctl','bootout',SERVICE],capture_output=True,text=True)
        if result.returncode:
            raise SystemExit('Could not stop the macOS service: '+result.stderr.strip())
        # bootout is asynchronous: an immediate start must not reuse the dying server.
        for _ in range(100):
            if service_info() is None and not healthy():
                break
            time.sleep(.2)
        else:
            raise SystemExit('The service is still stopping. Check '+str(ROOT/'.run/server.log'))
        STATE.unlink(missing_ok=True)
        print('VDS Shorts Factory stopped. Originals and SQLite preserved.')
    else:
        stop_legacy()

def start():
    os.chdir(ROOT)
    info=service_info()
    if healthy() and info is not None:
        record_service(info)
        print(URL)
        if '--no-open' not in sys.argv: subprocess.run(['open',URL],check=False)
        return
    if not (ROOT/'frontend/dist/index.html').exists():
        subprocess.run(['npm','run','build'],cwd=ROOT/'frontend',check=True)
    (ROOT/'.run').mkdir(exist_ok=True)
    if info is None:
        # Migrate an earlier directly spawned process, checking ownership before stopping it.
        stop_legacy()
        if healthy():
            raise SystemExit('Port 8765 is already serving another instance; it was not stopped.')
        log=ROOT/'.run/server.log'
        if log.exists() and not log.is_symlink():
            log.rename(ROOT/'.run'/f'server-before-launchd-{time.time_ns()}.log')
        if log.is_symlink():
            log.unlink()
        log.symlink_to(BOOT_LOG)
        PLIST.write_bytes(plistlib.dumps(service_definition()))
        PLIST.chmod(0o600)
        result=subprocess.run(['launchctl','bootstrap',DOMAIN,str(PLIST)],capture_output=True,text=True)
        if result.returncode:
            raise SystemExit('macOS service startup failed: '+result.stderr.strip()+'\nLog: '+str(ROOT/'.run/server.log'))
    for _ in range(60):
        if healthy():
            record_service(service_info())
            print('VDS Shorts Factory: '+URL)
            if '--no-open' not in sys.argv: subprocess.run(['open',URL],check=False)
            return
        time.sleep(.5)
    raise SystemExit('Startup failed. Read '+str(ROOT/'.run/server.log')+' and '+str(BOOT_LOG))

# ---------------------------------------------------------------- Windows and Linux
# No launchd: a hidden supervisor (launcher.py serve) runs uvicorn, restarts it after a crash or a
# «Перезапустить» from the UI, and exits once STOP_FLAG exists («Остановить»). No systemd needed on Linux.
WINDOWS=sys.platform=='win32'
SUP_STATE=ROOT/'.run/supervisor.json'
STOP_FLAG=ROOT/'.run/stop-requested'
SUP_LOG=ROOT/'.run/server.log'
NO_WINDOW={'creationflags':subprocess.CREATE_NO_WINDOW} if WINDOWS else {}

def venv_python(windowless=False):
    if WINDOWS: return str(ROOT/'.venv/Scripts'/('pythonw.exe' if windowless else 'python.exe'))
    return str(ROOT/'.venv/bin/python')

def sup_alive(pid):
    if WINDOWS:
        # os.kill(pid, 0) would terminate the process on Windows; ask tasklist instead.
        out=subprocess.run(['tasklist','/FI',f'PID eq {pid}','/FO','CSV','/NH'],capture_output=True,text=True,**NO_WINDOW).stdout
        return f'"{pid}"' in out and 'pythonw' in out.lower()
    out=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True).stdout
    return 'launcher.py' in out and 'serve' in out

def alert(text):
    # Shortcuts start without a console: show failures where the user can see them.
    if WINDOWS:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,text,'VDS Shorts Factory',0x10)
    else:
        import shutil
        if shutil.which('notify-send'): subprocess.run(['notify-send','VDS Shorts Factory',text],capture_output=True,check=False)

def supervisor():
    try: pid=json.loads(SUP_STATE.read_text())['pid']
    except (OSError,ValueError,KeyError): return None
    return pid if sup_alive(pid) else None

def serve():
    (ROOT/'.run').mkdir(exist_ok=True)
    STOP_FLAG.unlink(missing_ok=True)
    SUP_STATE.write_text(json.dumps({'pid':os.getpid(),'root':str(ROOT),'url':URL}))
    # PYTHONUTF8: Windows defaults to cp1252 for files; the studio's JSON and captions are UTF-8.
    env={**os.environ,'VDS_SUPERVISED':'1','PYTHONUNBUFFERED':'1','PYTHONUTF8':'1',
         'PATH':str(ROOT/'.tools/bin')+os.pathsep+os.environ.get('PATH','')}
    crashes=[]
    try:
        while True:
            with SUP_LOG.open('ab') as log:
                child=subprocess.Popen([venv_python(),'-m','uvicorn','backend.main:app','--app-dir',str(ROOT),
                                        '--host','127.0.0.1','--port','8765','--no-access-log'],
                                       cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,**NO_WINDOW)
                code=child.wait()
            if STOP_FLAG.exists(): break
            now=time.time()
            crashes=[t for t in crashes if now-t<60]+([now] if code else [])
            if len(crashes)>=5: break   # crash loop: stop instead of spinning; the UI shows «Запустить»
            time.sleep(2)
    finally:
        STOP_FLAG.unlink(missing_ok=True)
        SUP_STATE.unlink(missing_ok=True)

def sup_start():
    if healthy():
        print(URL)
    else:
        if supervisor() is None:
            detach=({'creationflags':subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS
                    else {'start_new_session':True})   # survives closing the terminal
            subprocess.Popen([venv_python(windowless=True),str(ROOT/'scripts/launcher.py'),'serve'],cwd=str(ROOT),
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**detach)
        for _ in range(120):
            if healthy(): break
            time.sleep(.5)
        else:
            alert('VDS Shorts Factory не запустился.\n\nЖурнал: '+str(SUP_LOG)+
                  '\n\nЕсли папка программы была перемещена или удалена, установите программу заново.')
            raise SystemExit('Сервер не запустился. Журнал: '+str(SUP_LOG))
        print('VDS Shorts Factory: '+URL)
    if '--no-open' not in sys.argv:
        import webbrowser
        webbrowser.open(URL)

def sup_stop():
    pid=supervisor()
    if pid is None and not healthy():
        print('Server is already stopped.');return
    (ROOT/'.run').mkdir(exist_ok=True)
    STOP_FLAG.touch()
    try:
        request=urllib.request.Request(URL+'/api/system/stop',data=b'',method='POST',headers={'X-Factory-Client':'local'})
        urllib.request.urlopen(request,timeout=5).close()
    except Exception: pass
    for _ in range(60):
        if not healthy() and (pid is None or not sup_alive(pid)): break
        time.sleep(.5)
    else:
        if pid and WINDOWS: subprocess.run(['taskkill','/T','/F','/PID',str(pid)],capture_output=True,**NO_WINDOW)
        elif pid: os.killpg(pid,signal.SIGTERM)
    print('VDS Shorts Factory stopped. Originals and SQLite preserved.')

if __name__=='__main__' and sys.platform!='darwin':
    command=sys.argv[1] if len(sys.argv)>1 else 'start'
    if command=='serve': serve()
    elif command=='stop': sup_stop()
    elif command=='status': print(('Running: ' if healthy() else 'Stopped or unavailable: ')+URL)
    else: sup_start()
elif __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='stop': stop()
    elif len(sys.argv)>1 and sys.argv[1]=='status':
        print(('Running: ' if healthy() else 'Stopped or unavailable: ')+URL)
    else: start()
