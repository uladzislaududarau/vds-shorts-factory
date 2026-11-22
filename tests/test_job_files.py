import json
import time
from types import SimpleNamespace
import pytest
from backend import db,job_files

@pytest.fixture
def files(client,source,tmp_path,monkeypatch):
    from backend import main,metadata
    for folder in ('renders','exports','sources'):(tmp_path/folder).mkdir()
    monkeypatch.setattr(job_files,'safe_path',lambda relative:(tmp_path/relative).resolve())
    monkeypatch.setattr(main,'DATA',tmp_path)
    monkeypatch.setattr(metadata,'delivery_path',lambda clip:tmp_path/clip['render_path'])
    monkeypatch.setattr(job_files.sys,'platform','darwin')
    calls=[]
    monkeypatch.setattr(job_files.subprocess,'run',lambda args,**kwargs:(calls.append((args,kwargs)) or SimpleNamespace(returncode=0)))
    return tmp_path,calls

def job(source,kind='render',status='Completed',clip_id=None,payload=None,checkpoints=None):
    jid=db.uid();now=time.time()
    db.execute('INSERT INTO jobs(id,source_id,clip_id,kind,status,payload,checkpoints,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
               (jid,source['id'],clip_id,kind,status,db.dump(payload or {}),db.dump(checkpoints or {}),now,now))
    return jid

def clip(source):
    cid=db.uid()
    db.execute('INSERT INTO clips(id,source_id,title,start,end,score,provider,data,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
               (cid,source['id'],'Fixture',0,5,0,'manual','{}',time.time()))
    return cid

def test_reveal_exact_job_revision_instead_of_latest_clip(client,source,files):
    root,calls=files;cid=clip(source)
    jid=job(source,clip_id=cid,payload={'revision':1})
    path=root/'renders'/f'{cid}-r1-{jid[:8]}.mp4';path.write_bytes(b'old exact output')
    newer=root/'renders/newer.mp4';newer.write_bytes(b'newer output')
    db.execute('UPDATE clips SET render_path=?,render_revision=2 WHERE id=?',('renders/newer.mp4',cid))
    listing=client.get('/api/jobs').json()
    row=next(j for j in listing if j['id']==jid)
    assert row['output']['path']==str(path)
    result=client.post(f'/api/jobs/{jid}/reveal')
    assert result.status_code==200,result.text
    assert calls[0][0]==['/usr/bin/open','-R',str(path)]
    assert 'shell' not in calls[0][1]
    assert client.get(f'/api/jobs/{jid}/file').content==b'old exact output'

def test_checkpoint_output_supports_legacy_names_with_spaces(client,source,files):
    root,calls=files
    path=root/'renders/My clip.mp4';path.write_bytes(b'fixture')
    jid=job(source,checkpoints={'output_path':'renders/My clip.mp4'})
    assert client.post(f'/api/jobs/{jid}/reveal').status_code==200
    assert calls[0][0][-1]==str(path)

@pytest.mark.parametrize('relative',['../outside.mp4','renders/../../outside.mp4','sources/source.mp4','renders/private.json'])
def test_reveal_refuses_outside_or_wrong_output_type(client,source,files,relative):
    root,calls=files
    path=(root/relative).resolve();path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
    jid=job(source,checkpoints={'output_path':relative})
    assert client.post(f'/api/jobs/{jid}/reveal').status_code==404
    assert client.get(f'/api/jobs/{jid}/file').status_code==404
    assert calls==[]

def test_missing_and_unfinished_outputs_do_not_open_finder(client,source,files):
    root,calls=files
    jid=job(source,checkpoints={'output_path':'renders/missing.mp4'})
    assert client.post(f'/api/jobs/{jid}/reveal').status_code==404
    pending=job(source,status='Running',checkpoints={'output_path':'renders/pending.mp4'})
    (root/'renders/pending.mp4').write_bytes(b'fixture')
    assert client.post(f'/api/jobs/{pending}/reveal').status_code==400
    assert client.get(f'/api/jobs/{pending}/file').status_code==404
    assert calls==[]

def test_zip_and_download_can_be_revealed(client,source,files):
    root,calls=files
    eid=db.uid();archive=root/'exports'/f'{eid}.zip';archive.write_bytes(b'zip fixture')
    export=job(source,kind='export',checkpoints={'download_url':f'/api/exports/{eid}'})
    assert client.post(f'/api/jobs/{export}/reveal').status_code==200
    assert calls[-1][0][-1]==str(archive)
    original=root/'sources/original.mov';original.write_bytes(b'original fixture')
    db.execute('UPDATE sources SET path=? WHERE id=?',('sources/original.mov',source['id']))
    download=job(source,kind='download')
    assert client.post(f'/api/jobs/{download}/reveal').status_code==200
    assert calls[-1][0][-1]==str(original)

def test_reveal_is_local_only_and_reports_native_failure(client,source,files,monkeypatch):
    root,calls=files
    (root/'renders/fixture.mp4').write_bytes(b'fixture')
    jid=job(source,checkpoints={'output_path':'renders/fixture.mp4'})
    assert client.post(f'/api/jobs/{jid}/reveal',headers={'Origin':'https://outside.example'}).status_code==403
    assert not calls
    monkeypatch.setattr(job_files.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1))
    result=client.post(f'/api/jobs/{jid}/reveal')
    assert result.status_code==400 and 'Finder' in result.json()['detail']
