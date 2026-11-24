# Montage: combine multiple videos

Added November 21, 2026. Open Montage in the sidebar. Media processing runs locally.

## Workflow

1. Choose Montage → New montage.
2. **Clips.** Add MP4/MOV/MKV/WebM from your computer or choose from Library. A **source fragment** uses clean source video without burned-in captions; you can extend its boundaries beyond the detected moment and reuse the existing transcript. A **ready MP4** keeps its existing crop, audio and captions; additional captions default to off. Click a clip to edit. Trim using sliders, precise seconds or start/end-at-current-frame buttons. Set volume from 0–200% or mute. Reorder with arrows or drag on the bottom timeline.
3. **Audio.** Generate ElevenLabs AI music for the entire montage, or add your own MP3/WAV/M4A/AAC/OGG/FLAC. Music genres include children/cartoon, action, epic, cheerful, calm lo-fi, thriller, romance, sports, hip-hop, inspiring, comedy, horror and custom description. Choose automatic/slow/medium/fast tempo, optionally add wishes, consent to credit use and Generate music. Duration equals the sum of trimmed clips. The result starts at zero, covers the timeline at 35% volume and fades out. New variants replace the current track; previous ones remain available to audition and restore. Extending the edit afterward shows a warning. Uploaded audio starts at the playhead and supports timeline start, duration, source offset, volume and fades. Normalize loudness targets −14 LUFS.
4. **Captions.** Five templates: bold accent, word box, one word, minimal and neon. Configure text/accent colors, size, position, outline, words per screen and uppercase. Template previews use the output renderer. Recognize speech runs local Whisper using Settings → AI. Correct each clip's words afterward.
5. **Format.** Choose vertical 9:16 at 1080×1920 or horizontal Full HD at 1920×1080. Fit mismatched clips using blur, crop-to-fill or letterboxing. Choose 30/60 FPS and one of three quality levels.
6. Create video queues a render. When ready, watch/download MP4 or reveal it in the file manager. SRT is saved alongside it.

Projects save automatically. The editor player is a fast approximate browser preview; only the finished MP4 is the exact result.

## Initial limits

- Up to 40 clips, 30 audio tracks and ten minutes of output.
- Direct cuts only; no transitions, video effects or keyframes.
- Captions do not cross cuts. Words truncated by a clip boundary are omitted.
- Transcription uses the selected model. Tiny is faster but less accurate; review before publishing.
- Confirm usage rights when uploading. Responsibility for source material and music remains with the user.

## Implementation

`backend/montage.py` defines `MontagePlan`, FFprobe-validated imports, SHA-256 deduplication, transcription, FFmpeg graphs and `/api/montage/*`. `backend/montage_captions.py` implements Pillow caption templates, frames and previews, with system-font fallback including Cyrillic.

Queue kinds `montage` and `montage_words` share FFmpeg/Whisper semaphores with the studio. Tables are `montage_projects` and `montage_media`. Media, word cache and previews live in `data/montage/`; output is `data/renders/montage-*.mp4`.

Each input is trimmed with `-ss/-t`, converted to target dimensions/FPS and padded/trimmed to a frame boundary using `tpad` + `trim` to avoid audio drift at cuts. Tracks use `adelay` + `amix`, then `loudnorm`. QC shares Clip Studio's full decode, geometry, duration, FPS, audio alignment and metadata checks.

## Verification

`tests/test_montage.py` exercises actual 9:16/16:9 output, trimming, muted clips, overlaid MP3, caption-box pixels, validation, library fragments with transcripts, template previews and queued-job reporting.

`scripts/qa_montage.mjs` exercises a running browser/server: upload, trim, playback, music, actual Russian transcription, render and 1440/768/390 layouts. Local reports are `docs/montage-browser-qa.json` and `docs/browser-qa/montage/`.

## AI music internals

`POST /api/montage/projects/{id}/music` accepts genre, tempo, wishes and required consent. Before queuing it checks the ElevenLabs key and Eleven Music limits, including queued generations.

The `montage_music` job uses Generate Reel's `compose_music` in `backend/audio_replacement.py`: `music_usage` accounting, no automatic paid retries and preservation of a paid result when paused. It uses the configured model (`music_v2_5`), `force_instrumental` and montage duration.

Each deliberate generation creates a new variant. Retrying the same job after failure/pause reuses its paid file. The result enters the plan as `kind: "music"`. Revision checking returns 409 if the music job changed the plan during editing; the editor merges the AI track with user edits and saves again. Automated tests supply a mocked ElevenLabs response containing an actual MP3 of the required duration and make no paid calls.
