# Batch generation, deletion and export privacy

## One generation workflow

Select up to 100 clips in the Library, optionally filtering by source, then click **Generate Reel**. Unified settings apply the selected format, FPS, crop, no-face Smart Crop behavior, caption toggle and caption preset to every selected editing plan. Clip boundaries, segments, corrected words and audio are preserved. Previously saved individual plans also update when unified settings are enabled. With that toggle off, each plan is used as saved.

**Create and download ZIP** queues all renders persistently, followed by a ZIP job that depends on their successful completion. ZIP waits for paused renders; if a render fails or is cancelled, ZIP reports an error rather than creating an incomplete archive. Automatic download runs in the browser that started the operation and survives a page refresh. If that browser is closed, blocks downloads or has changed, use **Download ZIP** on the completed queue job.

The Selected tab and bookmark button organize a collection; selection is not required to generate a clip. Generate Reel replaces the former separate selected/approved render actions.

## Deletion

Deletion requires confirmation listing the clip names. It removes selected records and associated scores, segments, projects, render history, all owned MP4/ASS/SRT versions and sanitized-download caches. Sources, transcripts and existing ZIP files remain. Confirmed deletion cannot be undone. If the transaction fails, moved files are restored. Deletion is blocked while clips have unfinished render or ZIP jobs; finish or cancel those first. Reusing an old analysis cache does not restore deleted IDs. A new analysis with different settings may suggest new clips from the same source intervals.

## File contents

New MP4s do not copy source user tags or chapters. The exporter removes title, artist, comment, creation_time, location and software encoder tags. It does not add the studio name, AI provider, source URL or internal scores. It removes the H.264 software encoder SEI block, checks remaining tags and fully decodes the result. For older ready MP4s, downloading creates a cached sanitized copy by copying audio/video streams without re-encoding. Saved originals are not overwritten.

MP4 cannot be stripped of all technical information: container, codecs, dimensions, FPS, duration, sample tables and neutral track fields remain. The tag allowlist permits major_brand, minor_version, compatible_brands and neutral language=und, VideoHandler, SoundHandler and vendor_id=0 fields. Internal JSON/CSV reports stay in SQLite/project storage and enter ZIP only when explicitly enabled. By default, ZIP contains MP4 files only, without SRT/ASS or reports. ZIP entry dates are neutral rather than render timestamps. Existing ZIP archives are not rewritten automatically.

Tag cleanup does not make a video undetectable or replace copyright and AI-disclosure obligations. Content ID compares actual audio and images, rather than metadata alone. See [YouTube AI disclosure](https://support.google.com/youtube/answer/14328491?hl=en) and [Content ID](https://support.google.com/youtube/answer/2797370?hl=en) for platform guidance.

Implementation checks include automated QA, a live browser workflow and inspection of downloaded MP4 files.
