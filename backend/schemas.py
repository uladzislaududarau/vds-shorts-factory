from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import math

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Scores(StrictModel):
    hook_strength: float = Field(ge=0, le=100)
    retention_potential: float = Field(ge=0, le=100)
    emotional_impact: float = Field(ge=0, le=100)
    standalone_value: float = Field(ge=0, le=100)
    clarity: float = Field(ge=0, le=100)
    visual_interest: float = Field(ge=0, le=100)
    narrative_completeness: float = Field(ge=0, le=100)
    editing_feasibility: float = Field(ge=0, le=100)

class Candidate(StrictModel):
    source_video_id: str
    clip_id: str
    title: str = Field(min_length=1, max_length=180)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    hook: str
    summary: str
    reason: str
    scores: Scores
    language: str
    category: str
    warnings: list[str]
    confidence: float = Field(ge=0, le=1)
    titles: list[str] = Field(default_factory=list, max_length=5)
    description: str = ''
    extended_description: str = ''
    hashtags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    cover_text: str = ''

    @model_validator(mode='after')
    def boundaries(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError('end must be after start')
        return self

    def validate_duration(self, duration: float):
        if self.end_seconds > duration + .01:
            raise ValueError('Candidate exceeds source duration')
        return self

class CandidateList(StrictModel):
    candidates: list[Candidate] = Field(max_length=100)

class Segment(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Segment end must be after start')
        return self

class SubtitleStyle(StrictModel):
    enabled: bool = True
    preset: Literal['Clean Minimal', 'Bold Viral', 'Kinetic Captions', 'Premium Editorial', 'High Contrast'] = 'Bold Viral'
    font: Literal['Arial', 'Helvetica', 'Georgia'] = 'Arial'
    size: int = Field(default=66, ge=24, le=140)
    bold: bool = True
    color: str = Field(default='#FFFFFF', pattern=r'^#[0-9A-Fa-f]{6}$')
    active_color: str = Field(default='#C6F24E', pattern=r'^#[0-9A-Fa-f]{6}$')
    outline: int = Field(default=3, ge=0, le=10)
    shadow: int = Field(default=2, ge=0, le=10)
    position: float = Field(default=.76, ge=.12, le=.88)
    words_per_line: int = Field(default=4, ge=1, le=8)
    margin: int = Field(default=80, ge=24, le=250)
    animation: Literal['none', 'highlight', 'pop'] = 'highlight'

class WordTimestamp(StrictModel):
    word: str = Field(min_length=1, max_length=120)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Word end must be after start')
        return self

class AudioReplacement(StrictModel):
    mode: Literal['original','music','music_voice'] = 'original'
    music_prompt: str = Field(default='Dark cinematic electronic instrumental, tense atmosphere, steady mid-tempo pulse, restrained bass and percussion, no vocals.',min_length=10,max_length=700)
    music_volume: float = Field(default=.3,ge=0,le=1)
    voice_volume: float = Field(default=1,ge=0,le=2)
    consent: bool = False

class EditPlan(StrictModel):
    segments: list[Segment] = Field(min_length=1, max_length=50)
    aspect: Literal['9:16', '1:1', '4:5', '16:9'] = '9:16'
    fps: Literal[30, 60] = 30
    crop_mode: Literal['center', 'smart', 'blur', 'split', 'manual'] = 'blur'
    smart_fallback: Literal['center','blur'] = 'blur'
    crop_x: float = Field(default=.5, ge=0, le=1)
    crop_y: float = Field(default=.5, ge=0, le=1)
    normalize_audio: bool = True
    denoise: bool = False
    volume: float = Field(default=1, ge=0, le=2)
    remove_pauses: bool = False
    audio_replacement: AudioReplacement = Field(default_factory=AudioReplacement)
    subtitles: SubtitleStyle = Field(default_factory=SubtitleStyle)
    caption_words: list[WordTimestamp] | None = Field(default=None, max_length=10000)
    encoder: Literal['auto', 'software', 'videotoolbox'] = 'auto'
    quality: int = Field(default=20, ge=16, le=30)

    def validate_source(self, duration):
        for segment in self.segments:
            if segment.end > duration + .01:
                raise ValueError('Trim exceeds source duration')
        if sum(s.end - s.start for s in self.segments) > 600:
            raise ValueError('A clip must be no longer than 10 minutes')
        if self.caption_words:
            previous = -1
            for word in self.caption_words:
                if word.end > duration + .01 or word.start < previous:
                    raise ValueError('Caption words must be ordered and within source duration')
                previous = word.start
        return self

class AnalyzeOptions(StrictModel):
    cloud_consent: bool = False
    min_duration: float = Field(default=20, ge=3, le=180)
    max_duration: float = Field(default=40, ge=3, le=180)
    target_count: int = Field(default=5, ge=0, le=100)
    score_threshold: int = Field(default=35, ge=0, le=100)
    language: str = Field(default='auto', pattern=r'^(auto|[a-z]{2,3})$')
    profile: Literal['Podcast', 'Interviews', 'Tech Reviews', 'Educational', 'Entertainment', 'Real Estate', 'Business'] = 'Educational'
    @model_validator(mode='after')
    def ordered(self):
        if self.max_duration < self.min_duration:
            raise ValueError('Maximum duration must be at least minimum duration')
        return self

class URLImport(StrictModel):
    url: str
    rights_status: Literal['owned', 'licensed', 'permission']
    license: str = Field(min_length=1, max_length=500)
    download: bool = False
    use_account: bool = False

class YouTubeDownload(StrictModel):
    url: str
    rights_status: Literal['owned','licensed','permission']
    license: str = Field(min_length=1,max_length=500)
    use_account: bool = True
    analyze_after: bool = True
    options: AnalyzeOptions = Field(default_factory=AnalyzeOptions)

class YouTubeConsent(StrictModel):
    consent: Literal[True]

class Batch(StrictModel):
    ids: list[str] = Field(min_length=1, max_length=100)

class RenderOverrides(StrictModel):
    aspect: Literal['9:16','1:1','4:5','16:9']
    fps: Literal[30,60]
    crop_mode: Literal['center','smart','blur','split','manual']
    smart_fallback: Literal['center','blur'] = 'center'
    subtitles_enabled: bool = True
    subtitle_preset: Literal['Clean Minimal','Bold Viral','Kinetic Captions','Premium Editorial','High Contrast']
    encoder: Literal['auto','software','videotoolbox'] = 'auto'
    quality: int = Field(default=20,ge=16,le=30)

class BatchRender(Batch):
    overrides: RenderOverrides | None = None
    audio_replacement: AudioReplacement | None = None
    download_zip: bool = False
    include_subtitles: bool = False
    include_metadata: bool = False

class ApprovalBatch(Batch):
    approved: bool

class ExportBatch(Batch):
    include_subtitles: bool = True
    include_metadata: bool = True

class SettingsUpdate(StrictModel):
    values: dict
    api_key: str | None = Field(default=None, max_length=512)
    openai_api_key: str | None = Field(default=None, max_length=512)
    elevenlabs_api_key: str | None = Field(default=None, max_length=512)

class VoicePreview(StrictModel):
    consent: Literal[True]
    text: str = Field(min_length=1,max_length=1200)

class AuthorPilot(StrictModel):
    consent: Literal[True]
    clip_id: str = Field(pattern=r'^[0-9a-f]{32}$')

class PublishBatch(Batch):
    consent: Literal[True]
    channel_id: str = Field(pattern=r'^UC[A-Za-z0-9_-]{22}$')
    mode: Literal['scheduled','private'] = 'scheduled'
    start: str | None = Field(default=None,max_length=60)

class OAuthClient(StrictModel):
    client_id: str = Field(min_length=10,max_length=300)
    client_secret: str = Field(min_length=5,max_length=512)

class PublicationCopy(StrictModel):
    title: str = Field(min_length=1,max_length=100)
    description: str = Field(min_length=1,max_length=4500)
    hashtags: list[str] = Field(max_length=5)
    tags: list[str] = Field(max_length=15)
