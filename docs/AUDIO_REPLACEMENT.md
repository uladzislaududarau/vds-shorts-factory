# Generate Reel with new music and voice

Implemented November 16, 2026. This mode is part of normal clip generation and does not require a new commentary script.

## Workflow

1. Import a YouTube URL and analyze it normally.
2. Select one to 100 clips in Library. A batch of 50 requires 50 existing candidates; analysis is not guaranteed to find 50 strong moments in every source. Analysis count supports up to 100 and the former eight-candidate visual-review cap was removed. Large cloud analyses also need sufficient provider request limits.
3. Click Generate Reel. Shared framing and caption settings remain available.
4. Under Soundtrack, choose the existing per-clip audio settings, original audio, new AI music replacing all original sound, or new AI music plus a chosen voice reading the same recognized words.
5. Set mood, tempo, instruments, music level and voice level.
6. Confirm ElevenLabs generation and credit use. Keep ZIP download enabled if desired.
7. Create and download ZIP. Queue handles speech preparation, music generation, rendering and QC. ZIP waits for all selected renders.

For a single clip, choose the same modes in Clip Studio → Audio, save the plan and Generate Reel. New music/voice uses the ElevenLabs key and Voice ID saved in Settings.

## What changes

Both replacement modes exclude the original audio completely, including music, speech, noise and effects. Revoicing reads recognized words in the chosen TTS voice; it does not clone original actors. Original intonation, character-specific voices and lip synchronization are not retained.

Whisper errors become speech errors. Review transcripts and clip-specific corrections before large batches. Base/Small can improve difficult transcription. Captions for the new voice use its new alignment rather than original speech timestamps.

Music generation receives a textual mood/tempo/instrument description only. It does not receive the original song as an audio reference. It creates an independent composition; automatic reproduction of the original music's character is not implemented. Choose a similar mood manually through presets.

## Plans, limits and caching

Settings → Voice has a separate Eleven Music section for model, cumulative request limit and requested seconds. Initial limits are 60 requests and 1800 seconds. Music API and TTS permissions/credits are separate ElevenLabs capabilities. A historical local Music API check succeeded with a user-provided key.

Fifty 30-second clips can require 50 music requests and approximately 1500 generated seconds. New speech can add up to 50 TTS requests. Include previously used samples when raising limits: five used plus 50 new requests needs at least 55, for example 60. Raising local limits does not increase provider credit or plan limits.

Before queuing, the whole batch is checked for clips, key, Voice ID, words, local limits, existing queued batches and cache hits. Insufficient limits reject the batch atomically. Monitor credits and commercial terms in ElevenLabs; the app does not assume a monetary music/voice price.

These modes support clips up to 180 seconds and 1200 speech characters per clip. Video duration is preserved. Speech may be moderately accelerated without changing pitch. If it requires more than 1.4× acceleration, rendering stops before generating new music. Shorter speech leaves music through the end. Original pauses are not reproduced exactly.

Each clip has a separate music request. An unchanged audio plan reuses music; changing crop alone does not order music again. TTS is cached by text, voice and model. Confirmed paid results survive pause. Network errors do not cause automatic paid retries. Failed replacement never silently restores original audio.

Existing MP4s and sources are not overwritten; rendering creates a new version. Internal QC records the model, song ID when available, music prompt and Eleven Music terms reference. ZIP contains MP4 only by default.

## Usage rights

Changing or replaying an identical song does not automatically remove rights restrictions. This mode generates independent music from a description under the selected [Eleven Music terms](https://elevenlabs.io/music-terms). Check plan terms and rights to source video/speech separately.

The application does not promise Content ID bypass or freedom from claims/strikes. YouTube compares both audio and images: [Content ID](https://support.google.com/youtube/answer/2797370?hl=en).

## Verification record

- A real eight-second instrumental `music_v2_5` generation was completed with a user key.
- A separate 1080×1920 music-and-voice test MP4 was created through the ordinary queue, with new music, speech and captions. Existing clips remained intact and nothing was published.
- FFmpeg fully decoded the sanitized MP4, and Chrome played it.
- Automated tests cover batches of 50 audio plans, atomic limit rejection, queued-batch accounting, strict failure without original-audio fallback, Music API contracts and caching. Spectral checks on actual fixture MP4s verify removal of the original tone and presence of new music/voice.
- Fifty actual paid generations were not run. Browser batch checks at 1440/768/390 intercepted submission without spending additional credits.
