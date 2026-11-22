import json
import sys
import threading
import time
from types import SimpleNamespace
import pytest
from backend import db
from backend.analysis import GeminiProvider
from backend.config import DATA
from backend.media import run,Interrupted
from backend.schemas import CandidateList
from tests.test_core import candidate

def test_gemini_mock_structured_cache_and_usage(isolated_db,monkeypatch):
    import backend.analysis as analysis
    from google import genai
    monkeypatch.setattr(analysis,'secret',lambda:'test-only-noncredential')
    calls=[]
    class Models:
        def generate_content(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=CandidateList(candidates=[candidate()]).model_dump_json(),
                usage_metadata=SimpleNamespace(prompt_token_count=100,candidates_token_count=50,thoughts_token_count=10))
    monkeypatch.setattr(genai,'Client',lambda **kwargs:SimpleNamespace(models=Models()))
    db.execute('UPDATE settings SET value=? WHERE key=?',('true','cloud_enabled'))
    settings={**db.settings(),'model':'unit-test-only-'+db.uid(),'budget_usd':0,'input_price_per_million':None,'output_price_per_million':None}
    before=set((DATA/'ai-cache').glob('*.json'))
    try:
        provider=GeminiProvider(settings,None)
        first=provider.request('Untrusted transcript fixture',['fixture'])
        second=provider.request('Untrusted transcript fixture',['fixture'])
        assert first[0].start_seconds==second[0].start_seconds and len(calls)==1
        usage=db.one('SELECT * FROM usage')
        assert usage['input_tokens']==100 and usage['output_tokens']==60
        assert usage['estimated_cost'] is None
    finally:
        for path in set((DATA/'ai-cache').glob('*.json'))-before:path.unlink()

def test_cloud_budget_blocks_unknown_prices(isolated_db,monkeypatch):
    import backend.analysis as analysis
    from google import genai
    monkeypatch.setattr(analysis,'secret',lambda:'test-only-noncredential')
    monkeypatch.setattr(genai,'Client',lambda **kwargs:SimpleNamespace())
    db.execute('UPDATE settings SET value=? WHERE key=?',('true','cloud_enabled'))
    settings={**db.settings(),'model':'unit-test-only-'+db.uid()}
    provider=GeminiProvider(settings,None)
    with pytest.raises(ValueError,match='тариф'):
        provider.request('fixture',['fixture'])

@pytest.mark.parametrize('status',['Cancelled','Paused'])
def test_real_subprocess_cancellation(source,status):
    jid=db.uid();now=time.time()
    db.execute('INSERT INTO jobs(id,source_id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(jid,source['id'],'analysis','Running','{}',now,now))
    error=[]
    def task():
        try:run([sys.executable,'-c','import time; time.sleep(20)'],job_id=jid,timeout=30)
        except BaseException as e:error.append(e)
    thread=threading.Thread(target=task)
    thread.start()
    time.sleep(.3)
    db.job_update(jid,status=status)
    thread.join(timeout=4)
    assert not thread.is_alive()
    assert len(error)==1 and isinstance(error[0],Interrupted)
