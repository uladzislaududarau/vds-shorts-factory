# VDS Shorts Factory: technical documentation

See [README](../README.md) for installation.

The local studio supports macOS, Windows and Linux. Its stack includes React, TypeScript, Vite, Tailwind, a Radix-based button, FastAPI, SQLite, MLX Whisper, OpenCV, PySceneDetect and FFmpeg. The server listens at **http://127.0.0.1:8765**.

## Developer setup

From the project directory, use `./start.command`, `./stop.command` and `./doctor.command`. On macOS the server runs through launchd, independently of Terminal. `./scripts/setup.command` creates a Python 3.11 development environment with uv, installs `backend/requirements-runtime.lock` and builds the UI. It requires Node.js 22.12+ and FFmpeg/FFprobe on PATH. `.venv/bin/python scripts/build_app.py` creates a launcher application for this checkout.

Production UI files in `frontend/dist` are committed so users do not need to build the UI. After editing `frontend/src`, run `npm --prefix frontend run build` before committing. Dependency sets are `backend/requirements-runtime.lock` for Apple Silicon, `backend/requirements-macos-intel.lock` for Intel Mac, and `backend/requirements-portable.lock` for Windows/Linux. Each lockfile header documents regeneration. GitHub Actions runs unit tests and fresh-install checks on all three operating systems through `.github/workflows/tests.yml`.

The marketing website is maintained in a separate private repository. It must not be added to this application repository.

## Main workflow

For YouTube, use Add video → YouTube → Sign in to YouTube, finish sign-in in the dedicated Chrome profile, then connect. Paste a URL, confirm rights and choose Download and analyze. Download and downstream analysis use the persistent queue. See [YouTube](YOUTUBE.md).

1. Import MP4/MOV/MKV/WebM files, multiple files or a folder; state usage rights.
2. Configure duration, language, profile and threshold. Local Whisper and heuristic ranking work without an API key.
3. Review a candidate in its source context and open Clip Studio.
4. Set segments, format, crop, captions and audio, then Generate Reel.
5. Wait for QC and watch the **ready MP4**. Download MP4/ASS/SRT; batch ZIP supports optional CSV/JSON reports.

Whisper weights download from Hugging Face to `data/models/` on first analysis. Afterward that model can process locally without network access. Local mode does not send source material to the cloud. Allow a 512 MB reserve plus space for the source, WAV and expected output; dependencies and weights require additional space.

## Cloud integrations

Gemini: save the key, test the connection, choose an account-accessible model and enable cloud processing. Each analysis requires separate consent to submit transcripts/previews. The key is stored in `.secrets/gemini.key` with file mode `0600` and directory mode `0700`, excluded from Git and never returned to the UI. This is local file storage, not macOS Keychain, and does not prevent local administrator access.

OpenAI supports transcript analysis and selected-frame review. ElevenLabs supplies voice samples and the separate script/voice pilot, plus music/voice replacement in Generate Reel. See [AI connections](AI_CONNECTIONS.md) and [audio replacement](AUDIO_REPLACEMENT.md).

An active USD budget requires user-supplied pricing. Unknown prices block new requests. Token estimates do not replace provider billing; request-count limits are separate. Test connection checks authorization/model access, rather than actual multimodal generation.

## Batch library

Select clips → Generate Reel → unified settings → Create and download ZIP. Audio replacement can generate independent AI music or revoice recognized words without writing a new script. Collection and deletion actions preserve source videos. Downloads sanitize user metadata; ZIP contains MP4 only by default. See [library/export behavior](EXPORT_AND_LIBRARY.md).

## Storage

| Data | Path |
|---|---|
| Originals | `data/sources/` |
| Word timestamps | `data/transcripts/` and SQLite |
| AI cache | `data/ai-cache/` |
| Editing plans and scenes | `data/projects/` |
| Checked MP4 / ASS / SRT | `data/renders/` |
| ZIP exports | `data/exports/` |
| Database and queue | `database/factory.sqlite3` |
| Server log | `.run/server.log` |

Do not move `.venv` separately: its Python links depend on the installation path. Recreate the environment after moving. For backup, stop the server and copy `data/` and `database/`; protect secrets separately.

## Practical limits

- Local ranking uses phrases, pauses, speech density and language features, rather than LLM-level meaning. Its Visual Interest score is zero and confidence is low. Gemini uses overlapping text windows followed by actual audio/video previews; OpenAI reviews transcript text and selected images.
- Smart Crop tracks the largest visible face with a Haar detector and smooths motion. It does not identify the active speaker or important objects, and cannot guarantee all faces remain visible. Review the finished file and choose the appropriate no-face fallback.
- Editing supports precise trims, segments, long-pause shortening, loudness normalization and denoising. Cuts are direct; there is no general automatic creative direction or complex transition system.
- Word-level captions can be burned in through Pillow RGBA and FFmpeg overlay without libass. MP4/ASS support highlights and a short pop-scale. Clip-specific text correction and SRT/ASS export are available. The editor preview is approximate.
- QC fully decodes files and checks duration, dimensions, FPS, audio and timing alignment. It does not certify meaning, transcript accuracy, face framing or subjective quality.
- The persistent queue limits Whisper/AI/FFmpeg concurrency. Pause/Cancel stops owned subprocesses; Resume reruns unfinished stages while preserving completed caches. Crashes requeue Running jobs; normal shutdown pauses them.
- yt-dlp supports public videos or an explicitly connected session. Authentication does not bypass DRM or account restrictions. Gemini URL analysis alone does not produce a local file or word timestamps.
- YouTube publishing uses a separate OAuth channel connection, OpenAI text, resumable upload and an hourly schedule. A local LLM adapter and the complete author-commentary workflow remain unimplemented.

## Verification

```sh
.venv/bin/python -m pytest
npm --prefix frontend run build
.venv/bin/python scripts/e2e_local.py
.venv/bin/python scripts/e2e_batch.py
```

The E2E scripts require a running server and create explicitly authored test material with synthetic macOS speech. They exercise real local transcription, analysis, rendering and export. These are test fixtures, not user videos. Reports such as `docs/e2e-result.json` are generated locally and may not be committed.

Further reading: [architecture](ARCHITECTURE.md), [providers](AI_PROVIDERS.md), [user guide](USER_GUIDE.md), [troubleshooting](TROUBLESHOOTING.md), and [YouTube publishing](YOUTUBE_PUBLISHING.md).
