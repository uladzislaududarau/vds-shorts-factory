# Troubleshooting

**Not enough disk space.** Free space manually or cancel the queue and use Settings → Storage → Clear temporary cache. The studio does not delete originals automatically. The default reserve is 512 MB; rendering also estimates up to 3 MB per second of output. Do not reduce the reserve to zero.

**Whisper takes a long time to start.** First use downloads model weights. Check network access to Hugging Face and the queue error. Retry reuses the saved WAV. Tiny uses less space; Base/Small are more accurate. Weights are in `data/models/`. On Apple Silicon, `doctor.command` checks native Metal support. Run the application on the Mac itself rather than in a container.

**No strong candidates.** Local heuristics do not provide LLM-level semantic understanding. Lower the threshold, adjust minimum/maximum duration, check language, select a fragment manually or connect a cloud provider. The application does not substitute evenly spaced cuts when no candidate qualifies.

**Gemini will not run.** Configure the key, Gemini provider, an available model, global cloud toggle and per-job consent. An active USD budget requires actual pricing; unknown pricing blocks requests. Check model permissions, quota and structured-video support. 429/5xx errors retry with backoff up to three times. Connection testing alone does not verify analysis.

**YouTube video unavailable.** Check that the dedicated studio Chrome window can play it with your account. Connect the session in Settings → YouTube and enable **Use my account** when downloading. Refresh an expired session. Sign-in does not remove DRM or restrictions applying to the account. See [YouTube setup](YOUTUBE.md).

**YouTube: Sign in to confirm your age.** Use an age-verified account: Sign in to YouTube → finish Google's sign-in/verification → I signed in — connect → retry with your account. If it still fails, refresh the session and verify playback in the dedicated Chrome window. Downloading does not require a Gemini key. Technical details are recorded in `.run/server.log`.

**Cannot read the Chrome session.** Close the dedicated sign-in window and reconnect. On macOS, allow access to Chrome Safe Storage when prompted. If access remains blocked, import a Netscape-format youtube.com `cookies.txt`. The studio does not read your regular Chrome profile.

**No captions or recognized words.** Rendering with captions enabled requires words. Run transcription or explicitly disable captions. Style changes require a new render; the editor preview is not the output file. FFmpeg without libass uses an actual RGBA caption fallback, including Cyrillic support.

**Render failed.** Read the FFmpeg/QC error in Queue. Auto encoder attempts VideoToolbox and falls back to libx264 if incompatible. Select Software for reproducibility. Blurred Background is a conservative crop option. Reduce segment count for very long plans.

**Clip not found during batch generation.** An old routing bug treated `batch` as a clip ID. Update and refresh the page, then use Generate Reel in Library. If another tab deleted a selected clip, refresh and select existing clips. The whole batch is validated before jobs are queued.

**ZIP did not download automatically.** Wait for the ZIP job to complete and click Download ZIP in Queue. Fix/retry a failed render before retrying ZIP or creating a new batch. ZIP waits while a render is paused.

**Deletion is blocked.** Selected clips are part of unfinished generation or ZIP jobs. Finish or cancel those jobs first. Deleting clips preserves sources and existing ZIP archives.

**Server will not start or the browser shows an error.** For source/command-line installations, open `start.command` and refresh http://127.0.0.1:8765. Start the server again after restarting the Mac. Check `.venv/bin/python scripts/launcher.py status`, `.run/server.log` and `doctor.command`. macOS launchd keeps this server independent of Terminal and restarts it after a crash. Pre-Python errors go to `/private/tmp/local.ai-shorts-factory.<identifier>.bootstrap.log`. `stop.command` stops only this project's service; legacy PID handling verifies the command and path before stopping a process. The server binds to 127.0.0.1 and is not exposed to other devices by default.

**Native app says the port is already in use.** Another Shorts Factory server may still be running, including the browser-based installation. Do not run both against the same data directory. Finish or pause active work, stop the old installation using its own stop command, then reopen the native app. Native startup details are in `~/Library/Application Support/VDS Shorts Factory/.run/desktop.log`.

**The Python environment was moved.** Recreate `.venv` through setup, preserving `data` and `database`. Do not delete unrelated user directories. API keys live outside the environment: Settings stores `.secrets/gemini.key` with `0600` permissions; `GEMINI_API_KEY` is also supported. `.env.example` is not loaded automatically.

**Resume immediately after Pause reports a stopping task.** Wait briefly for the owned subprocess to exit before resuming.
