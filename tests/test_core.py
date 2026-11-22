import math
import pytest
from pydantic import ValidationError
from backend.schemas import Candidate, EditPlan, AnalyzeOptions, Scores, SubtitleStyle
from backend.analysis import score, deduplicate, local_candidates, transcript_words
from backend.subtitles import remap_words, timestamp, export_text, raster_captions
from backend.media import validate_youtube, check_space
from backend.config import safe_path

def candidate(**updates):
    values=dict(source_video_id='test',clip_id='c',title='A complete idea',start_seconds=1,end_seconds=25,
                hook='Why?',summary='A self contained test idea',reason='test',scores={k:60 for k in Scores.model_fields},
                language='en',category='Educational',warnings=[],confidence=.5)
    values.update(updates)
    return Candidate(**values)

@pytest.mark.parametrize('start,end',[(10,9),(-1,10),(1,float('nan')),(1,float('inf'))])
def test_invalid_candidate_boundaries(start,end):
    with pytest.raises(ValidationError): candidate(start_seconds=start,end_seconds=end)

def test_ai_duration_and_unknown_fields():
    with pytest.raises(ValueError): candidate(end_seconds=130).validate_duration(120)
    with pytest.raises(ValidationError): candidate(secret_instruction='ignored')
    with pytest.raises(ValidationError): candidate(scores={k:101 for k in Scores.model_fields})

def test_scoring_and_deduplication():
    assert score(candidate().scores)==60
    a=candidate(clip_id='a')
    b=candidate(clip_id='b',start_seconds=5,end_seconds=28)
    c=candidate(clip_id='c',start_seconds=40,end_seconds=65,summary='Entirely different discussion about camera batteries')
    assert len(deduplicate([a,b,c]))==2

def test_local_analysis_uses_real_words_and_flags_limits(source,transcript):
    candidates=local_candidates(source,transcript,AnalyzeOptions(min_duration=10,max_duration=25,target_count=5),[])
    assert candidates
    words=transcript_words(transcript)
    for item in candidates:
        assert item.scores.visual_interest==0
        assert item.confidence<.5
        assert any(abs(item.start_seconds-max(0,w['start']-.06))<.01 for w in words)
        assert item.warnings
        item.validate_duration(source['duration'])
    assert local_candidates(source,{'segments':[]},AnalyzeOptions(),[])==[]

def test_remap_multiple_segments(transcript):
    plan=EditPlan(segments=[{'start':.2,'end':3.9},{'start':12,'end':17}])
    words=remap_words(transcript,plan.segments)
    assert words
    assert all(0<=w['start']<w['end']<=8.7 for w in words)
    assert words==sorted(words,key=lambda w:w['start'])

def test_subtitle_timestamps_and_cyrillic(tmp_path):
    assert timestamp(59.9996)=='00:01:00,000'
    assert timestamp(59.9996,True)=='0:01:00.00'
    words=[{'word':'Привет,','start':.1,'end':.6},{'word':'мир!','start':.7,'end':1.1}]
    style=SubtitleStyle()
    dest=tmp_path/'captions.mp4'
    export_text(words,style,1080,1920,dest)
    assert 'Привет' in dest.with_suffix('.ass').read_text()
    assert '00:00:00,100' in dest.with_suffix('.srt').read_text()
    concat=raster_captions(words,style,540,960,2,tmp_path/'frames')
    assert concat.exists()
    from PIL import Image
    image=Image.open(tmp_path/'frames/g0-0.png')
    box=image.getbbox()
    assert box and 0<box[0]<box[2]<540 and 0<box[1]<box[3]<960

def test_plan_validation():
    with pytest.raises(ValidationError): EditPlan(segments=[{'start':5,'end':3}])
    with pytest.raises(ValueError): EditPlan(segments=[{'start':1,'end':200}]).validate_source(120)
    with pytest.raises(ValidationError): AnalyzeOptions(min_duration=60,max_duration=20)

@pytest.mark.parametrize('url',['http://youtube.com/watch?v=abcdef12345','https://youtube.com.evil.com/watch?v=abcdef12345','https://user:pass@youtube.com/watch?v=abcdef12345','https://127.0.0.1/private','https://youtube.com/playlist?list=123'])
def test_url_security(url):
    with pytest.raises(ValueError): validate_youtube(url)

def test_paths_and_disk():
    with pytest.raises(ValueError): safe_path('../../etc/passwd')
    with pytest.raises(ValueError): check_space(10**20)
    assert validate_youtube('https://youtu.be/abcdef12345')=='https://www.youtube.com/watch?v=abcdef12345'
