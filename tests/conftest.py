import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

@pytest.fixture
def isolated_db(tmp_path,monkeypatch):
    from backend import db
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'test.sqlite3')
    db.init()
    return db

@pytest.fixture
def client(isolated_db,monkeypatch):
    from backend.main import app,farm
    from fastapi.testclient import TestClient
    monkeypatch.setattr(farm,'start',lambda:None)
    monkeypatch.setattr(farm,'stop',lambda:None)
    with TestClient(app,headers={'X-Factory-Client':'local'}) as client:
        yield client

@pytest.fixture
def source(isolated_db):
    import time
    sid=isolated_db.uid()
    isolated_db.execute('INSERT INTO sources(id,name,kind,duration,created_at) VALUES(?,?,?,?,?)',(sid,'Authorized test','local',120,time.time()))
    isolated_db.execute('INSERT INTO rights_metadata VALUES(?,?,?,?,?)',(sid,'owned','Original authored test','test',time.time()))
    return isolated_db.one('SELECT * FROM sources WHERE id=?',(sid,))

@pytest.fixture
def transcript():
    text=['Why do creators miss the strongest moment?', 'The answer is surprisingly simple.',
          'They start editing before listening to the complete story.', 'Try reading the transcript before choosing your first cut.',
          'This gives you a beginning a development and a clear conclusion.', 'So the viewer can understand the idea without watching the full interview.']
    result=[]
    cursor=0.3
    for line in text:
        words=[]
        for word in line.split():
            words.append({'word':word,'start':cursor,'end':cursor+.42})
            cursor+=.5
        result.append({'start':words[0]['start'],'end':words[-1]['end'],'text':line,'words':words})
        cursor+=.5
    return {'language':'en','text':' '.join(text),'segments':result}
