# Architecture

A single FastAPI process on loopback serves the API and production frontend. Optional Vite development runs separately and proxies `/api` to port 8765. React periodically refreshes actual server state.

SQLite uses WAL, foreign keys and transactions. Entities include Sources → RightsMetadata; Transcripts; Analysis with cache keys; Clips → Scores, Segments, Projects; Jobs → RenderTasks; Settings; and Usage. Migrations are idempotent and recorded in `migrations`; later modules add their own tables and migrations.

The queue has three control threads, with at most one analysis and one render task at a time. Separate Whisper, AI and FFmpeg semaphores each allow one operation. FFmpeg, PySceneDetect and Whisper run without a shell in owned process groups. Pause/Cancel checks run every 200 ms and terminate only the task's group. An SDK network request may continue until its timeout. Completed stages are checkpointed; transcript and AI-cache files are replaced atomically.

`IMPORT → PROBE/THUMBNAIL → AUDIO → MLX/WORDS → SCENES → ANALYSIS → SCORES → PROJECT → CROP/CAPTIONS → RENDER → QC → ZIP`

Sources are identified by SHA-256. Transcript caching includes model and language. Analysis keys include the source hash, text, model/mode and selection settings. AI requests are also cached by model, schema and request content. Cached results do not require another paid request. Editing projects and render jobs hold a plan snapshot and revision. A completed render is marked stale if its plan changed while it was running.

`Running` means execution; `stage` identifies Transcribing, Analyzing, Scoring, Preparing, Rendering or QC. Percentages describe completed stages, rather than exact frame or token progress. Jobs survive restarts: interrupted Running jobs return to Queued, while Paused jobs stay paused.

Security controls include a localhost Host allowlist, Origin validation, a required non-simple client header for mutations, no CORS, media access by ID, FFprobe type checks, extension allowlists, streaming size limits and reserved disk space. FastAPI FileResponse supports Range requests. CSV exports guard against formula injection. Archiving a source does not automatically delete its file.

Frontend paths are never concatenated into subprocess commands. Folder import requires an explicit absolute user path and skips file symlinks. YouTube import accepts a single HTTPS video ID, rejects playlists, embedded credentials and other hosts. An explicitly connected YouTube session is stored separately in `.secrets/youtube/` and passed to yt-dlp through a private file copy; cookie values do not enter argv, SQLite or HTTP responses. AI prompts mark transcript content as untrusted. Pydantic validates structured responses and checks timestamps against duration.

`backend/youtube_auth.py` manages a dedicated Chrome sign-in profile and filtered session. `workers/youtube_cookies.py` reads only that profile. `POST /api/import/youtube` creates a persistent download job with a nullable source ID. `workers/youtube_fetch.py` runs yt-dlp with Node/EJS and writes bounded JSON progress/results. The farm handles Pause/Cancel, imports the completed source and queues analysis. Stream merging shares the FFmpeg semaphore with rendering. Partial downloads survive pause/restart. The saved source and downstream analysis ID are checkpointed to prevent repeated downloading or analysis.

OpenAI implements transcript analysis plus selected-frame review; Gemini supports its two-pass video workflow. Implement additional providers through `AnalysisProvider.analyze(...)` and add a schema migration when separate model fields are needed. Semantic QC remains a human decision until an independently validated analysis exists. See [AI providers](AI_PROVIDERS.md) and [YouTube publishing](YOUTUBE_PUBLISHING.md) for module details.
