import json
import threading
import time
import pytest
from pathlib import Path
from backend import db
from backend.config import DATA,FFMPEG
from backend.media import run,probe
from backend.render import render,SIZES
from backend.schemas import EditPlan

@pytest.mark.parametrize('aspect,crop_mode,fps',[('9:16','blur',30),('4:5','split',30),('1:1','center',30),('16:9','manual',60)])
def test_real_import_render_subtitles_qc_and_export(client,isolated_db,tmp_path,aspect,crop_mode,fps):
    file=tmp_path/'authored.mp4'
    run([FFMPEG,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=0x222222:size=640x360:rate=30',
         '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','4','-c:v','libx264','-preset','ultrafast','-c:a','aac',
         '-metadata','title=Private source title','-metadata','artist=Private source author','-metadata','comment=Private comment','-shortest',file])
    with file.open('rb') as handle:
        response=client.post('/api/import/files',data={'rights_status':'owned','license':'Procedurally authored integration fixture'},files={'files':('authored.mp4',handle,'video/mp4')})
    imported=response.json()[0]
    assert not imported.get('error'),imported
    source=db.one('SELECT * FROM sources WHERE id=?',(imported['source']['id'],))
    with file.open('rb') as handle:
        duplicate=client.post('/api/import/files',data={'rights_status':'owned','license':'Test fixture'},files={'files':('authored.mp4',handle,'video/mp4')}).json()[0]
    assert duplicate['duplicate']
    clip=client.post(f'/api/sources/{source["id"]}/manual-clip',json={'start':0,'end':3}).json()
    # Authored timing fixture for subtitle rendering, not a claimed transcription of the sine wave.
    transcript={'segments':[{'words':[{'word':'Проверка','start':.2,'end':.8},{'word':'субтитров!','start':.9,'end':1.6}]}]}
    plan=EditPlan(segments=[{'start':0,'end':1.8},{'start':2,'end':3.2}],encoder='software',crop_mode=crop_mode,aspect=aspect,fps=fps)
    jid=db.uid();now=time.time()
    db.execute('INSERT INTO jobs(id,source_id,clip_id,kind,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(jid,source['id'],clip['id'],'render','Running','{}',now,now))
    destination=DATA/'renders'/f'test-{jid}.mp4'
    try:
        qc=render(source,transcript,plan.model_dump(),jid,destination,threading.Semaphore(1))
        assert qc['passed'] and qc['full_decode']
        assert qc['word_count']==2
        assert (qc['width'],qc['height'])==SIZES[aspect]
        assert qc['fps']==fps
        assert qc['metadata_clean'] and qc['unexpected_metadata_fields']==[]
        raw=probe(destination)['raw']
        assert 'title' not in raw['format'].get('tags',{})
        assert all('encoder' not in s.get('tags',{}) for s in raw['streams'])
        assert b'Private source' not in destination.read_bytes() and b'x264 - core' not in destination.read_bytes()
        assert destination.with_suffix('.srt').exists()
        assert destination.with_suffix('.ass').exists()
        # Subtitle engine changes actual video pixels inside the safe caption band.
        frame=tmp_path/'actual.png'
        run([FFMPEG,'-hide_banner','-loglevel','error','-y','-ss','0.4','-i',destination,'-frames:v','1','-update','1',frame])
        from PIL import Image
        im=Image.open(frame).convert('RGB')
        pixels=list(im.crop((30,round(qc['height']*.65),qc['width']-30,round(qc['height']*.9))).get_flattened_data())
        assert sum(1 for r,g,b in pixels if g>170 and r>120 and b<140)>100
        db.execute('UPDATE clips SET render_path=?,render_revision=1 WHERE id=?',(str(destination.relative_to(DATA)),clip['id']))
        exported=client.post('/api/exports',json={'ids':[clip['id']]}).json()
        import zipfile
        export_id=exported['url'].split('/')[-1]
        with zipfile.ZipFile(DATA/'exports'/f'{export_id}.zip') as z:
            assert f'{clip["id"]}.mp4' in z.namelist()
            assert 'metadata.csv' in z.namelist()
            assert z.testzip() is None
    finally:
        for cached in (DATA/'exports').glob('clean-'+clip['id']+'-*.mp4'):cached.unlink(missing_ok=True)
        for ext in ('.mp4','.srt','.ass'): destination.with_suffix(ext).unlink(missing_ok=True)
        for rel in (source['path'],source['thumbnail']): (DATA/rel).unlink(missing_ok=True)
