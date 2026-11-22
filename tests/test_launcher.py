import sys
import json
import plistlib
from types import SimpleNamespace

from scripts import launcher


def test_service_definition_preserves_paths_as_arguments(monkeypatch,tmp_path):
    root=tmp_path/'project with spaces $(not-a-command)'
    monkeypatch.setattr(launcher,'ROOT',root)
    config=plistlib.loads(plistlib.dumps(launcher.service_definition()))
    args=config['ProgramArguments']
    assert args[:2]==['/bin/sh','-c']
    assert str(root) not in args[2]
    assert args[4]==str(root)
    assert args[5]==str(root/'.venv/bin/python')
    assert config['KeepAlive'] is True
    assert config['WorkingDirectory']=='/private/tmp'
    assert config['Umask']==0o077


def test_stop_unloads_supervisor_instead_of_killing_restartable_pid(monkeypatch,tmp_path):
    state=tmp_path/'state.json'
    state.write_text('{}')
    monkeypatch.setattr(launcher,'STATE',state)
    states=iter(['state = running',None])
    monkeypatch.setattr(launcher,'service_info',lambda:next(states))
    monkeypatch.setattr(launcher,'healthy',lambda:False)
    calls=[]
    monkeypatch.setattr(launcher.subprocess,'run',lambda args,**kwargs:
                        (calls.append(args) or SimpleNamespace(returncode=0)))
    launcher.stop()
    assert calls==[['launchctl','bootout',launcher.SERVICE]]
    assert not state.exists()


def test_repeat_start_reuses_healthy_service(monkeypatch,tmp_path):
    state=tmp_path/'state.json'
    monkeypatch.setattr(launcher,'STATE',state)
    monkeypatch.setattr(launcher,'healthy',lambda:True)
    monkeypatch.setattr(launcher,'service_info',lambda:'\tpid = 12345\n')
    monkeypatch.setattr(launcher.sys,'argv',['launcher.py','start','--no-open'])
    monkeypatch.setattr(launcher.subprocess,'run',lambda *a,**kw:
                        (_ for _ in ()).throw(AssertionError('must not launch duplicate')))
    launcher.start()
    assert json.loads(state.read_text())['pid']==12345


def test_stale_pid_is_not_signalled(monkeypatch,tmp_path):
    state=tmp_path/'state.json'
    state.write_text(json.dumps({'pid':12345}))
    monkeypatch.setattr(launcher,'STATE',state)
    monkeypatch.setattr(launcher.subprocess,'check_output',lambda *a,**kw:'/usr/bin/unrelated')
    monkeypatch.setattr(launcher.os,'kill',lambda *a:
                        (_ for _ in ()).throw(AssertionError('must not signal unrelated process')))
    launcher.stop_legacy()
    assert not state.exists()


import pytest

@pytest.mark.skipif(sys.platform=='win32',reason='launchd service definition (macOS); Windows paths contain a colon')
def test_service_path_prefers_installed_tools(monkeypatch,tmp_path):
    monkeypatch.setattr(launcher,'ROOT',tmp_path)
    path=launcher.service_definition()['EnvironmentVariables']['PATH'].split(':')
    assert path[0]==str(tmp_path/'.tools/bin') and '/opt/homebrew/bin' in path
