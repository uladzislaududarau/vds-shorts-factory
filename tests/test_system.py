import plistlib
import subprocess
import sys

import pytest

from backend import main


def test_health_reports_whether_launchd_manages_the_server(client, monkeypatch):
    monkeypatch.delenv('XPC_SERVICE_NAME', raising=False)
    assert client.get('/api/health').json()['managed'] is False
    monkeypatch.setenv('XPC_SERVICE_NAME', 'local.ai-shorts-factory.abc123')
    assert client.get('/api/health').json()['managed'] is True


def test_restart_and_stop_require_managed_server(client, monkeypatch):
    monkeypatch.delenv('XPC_SERVICE_NAME', raising=False)
    assert client.post('/api/system/restart').status_code == 400
    assert client.post('/api/system/stop').status_code == 400
    # Same CSRF guard as every mutation.
    assert client.post('/api/system/restart', headers={'X-Factory-Client': 'other'}).status_code == 403


def test_restart_signals_own_process_and_stop_detaches_launcher(client, monkeypatch):
    monkeypatch.setenv('XPC_SERVICE_NAME', 'local.ai-shorts-factory.abc123')
    import threading
    timers, spawned = [], []
    monkeypatch.setattr(threading, 'Timer', lambda delay, fn: timers.append((delay, fn)) or type('T', (), {'start': lambda self: None})())
    assert client.post('/api/system/restart').json() == {'restarting': True}
    assert timers and timers[0][0] < 1
    monkeypatch.setattr(subprocess, 'Popen', lambda args, **kw: spawned.append((args, kw)))
    assert client.post('/api/system/stop').json() == {'stopping': True}
    if sys.platform == 'darwin':   # launchd: a detached `launcher.py stop` unloads the service
        args, kw = spawned[0]
        assert args[1].endswith('scripts/launcher.py') and args[2] == 'stop' and kw['start_new_session'] is True
    else:                          # Windows/Linux supervisor: stop flag + graceful exit, no restart
        assert not spawned and len(timers) == 2 and (main.ROOT / '.run/stop-requested').exists()
        (main.ROOT / '.run/stop-requested').unlink()


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS app bundle')
def test_app_bundle_registers_url_scheme_and_is_signed(tmp_path, monkeypatch):
    sys.path.insert(0, str(main.ROOT / 'scripts'))
    import build_app
    monkeypatch.setattr(build_app.subprocess, 'run', _no_lsregister(build_app.subprocess.run))
    monkeypatch.setattr(sys, 'argv', ['build_app.py', '--dest', str(tmp_path)])
    app = build_app.build()
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    assert info['CFBundleURLTypes'][0]['CFBundleURLSchemes'] == ['shortsfactory']
    assert info['CFBundleIdentifier'] == 'local.shorts-factory.launcher'
    assert (app / 'Contents/Resources/applet.icns').stat().st_size > 10000
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    source = build_app.applescript(main.ROOT)
    assert 'on open location' in source and '--no-open' in source and 'launcher.py' in source


def _no_lsregister(run):
    # Never register a throwaway test bundle as the system handler for shortsfactory://.
    def wrapped(args, **kw):
        if args and str(args[0]).endswith('lsregister'):
            return subprocess.CompletedProcess(args, 0)
        return run(args, **kw)
    return wrapped
