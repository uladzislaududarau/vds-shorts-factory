# User guide

Launch the installed application, or use `start.command` for a source installation. Dashboard shows actual counts, queue state, engine and free disk space. Switch light/dark themes at the bottom of the navigation.

**YouTube.** Open Add video → YouTube. Click Sign in to YouTube, sign in through the dedicated Chrome window, then return and connect the session. Paste a URL, keep downloading and automatic highlight analysis enabled, confirm your usage rights and click Download and analyze. Queue shows download and later processing stages. Account controls are also in Settings → YouTube. See the [YouTube guide](YOUTUBE.md).

**Sources.** Drag files into import or select a folder using an absolute path. State usage rights and confirm processing. Videos are copied to `data/sources`; SHA-256 prevents duplicate import. Removing a source from the library archives it and preserves the original file.

**Analysis setup.** Queue 1–100 videos. Set minimum/maximum duration, candidate count or Auto, threshold, profile and language. Count is a maximum; weak moments are not added to fill it. For cloud analysis, save a key and model, enable cloud processing and confirm submission in the analysis dialog. Leave consent off for local processing. Downloading local model weights does not send your recording or text.

**Video Analysis.** Review the original player, scenes and timeline candidates. Click a transcript row or candidate timestamp to seek. Expand scores, read warnings, check context and mark approval. Create a manual fragment without analysis by setting start/end times. If no recognized words exist, explicitly disable captions before rendering.

**Clip Studio.** Set start/end with numbers or range handles. Add segments in playback order, optionally shortening word-level pauses. Crops include full frame on a blurred background, center, face tracking, left/right split and manual x/y. Choose aspect ratio, FPS, audio filters and caption style. Correct individual caption words while preserving real timestamps; this does not change the source transcript or AI analysis. Check Whisper's output. Save and click Generate Reel. Changing caption style does not repeat AI analysis.

The source preview is approximate. After rendering, switch to **ready MP4** and watch the complete file. Re-render after plan revisions; an old file is not updated automatically. Download MP4/SRT/ASS from the editor.

**Queue.** Pause stops the current stage; Resume reruns it using cached prior results. Cancel keeps completed stages; Retry restarts a job. Each row exposes errors and logs. Normal shutdown pauses work for later Resume. After a crash, Running jobs return to Queued.

**Library.** Select clips → Generate Reel → set unified format, FPS, crop and caption style → Create and download ZIP. Each clip keeps its boundaries and segments. Disable Unified settings to preserve individual settings. Smart Face Crop offers Center Crop without blur or a blurred background when no face is detected. Renders run sequentially, then ZIP is created. With the application open, download starts automatically; Queue keeps a download link. Each batch supports up to 100 clips. Already rendered selections also offer Download ZIP.

**Selected collection.** This is an organizational collection, not a mandatory approval gate for generation. Select clips and add them to Selected, or click a card's bookmark. Remove them from the collection in the Selected tab. Use the same Generate Reel action there.

**Delete clips.** Select unwanted clips → Delete → review the list → confirm. This removes records, MP4 versions, SRT/ASS files and editing plans. Source videos and existing ZIPs remain. Confirmed deletion cannot be undone. Wait for or cancel unfinished render/ZIP jobs first. Cancelling the confirmation dialog deletes nothing.

**Export metadata.** ZIP contains MP4 only by default. Separate captions and internal JSON/CSV reports are opt-in. MP4 user tags, chapters and software encoder names are removed; required technical container/codec information remains. Older renders are sanitized on download without overwriting stored originals. This does not guarantee concealment of a video's origin or prevent platform claims. See [export details](EXPORT_AND_LIBRARY.md).

**New music and voice.** Library → select clips → Generate Reel → Soundtrack. Choose independent AI music or music plus a new voice reading the recognized words. All original audio, including effects, is removed. This creates MP4/ZIP without a new script. See [audio replacement](AUDIO_REPLACEMENT.md).

**Find the output file.** Queue → completed job → Show in Finder opens the folder and selects that job's file. Render jobs offer Download MP4; ZIP jobs offer archive download. The filename appears below the job title and the full path in a tooltip. Renders are in `data/renders`, ZIPs in `data/exports`. Missing files do not silently open another version.

**Settings.** AI and models offers Local, Gemini and OpenAI. Voice holds the ElevenLabs key, Voice ID, model, voice limits and a separate Eleven Music section. AI pilot is a separate script experiment. See [API connections](AI_CONNECTIONS.md). Test connection submits no material and does not guarantee multimodal analysis support. Supply actual prices for estimated USD budgets. Storage can clear temporary audio, frames and previews, including ElevenLabs samples, after stopping the queue. Originals, AI cache, words, projects and clips remain.

## YouTube publishing

Settings → Publishing: add Google OAuth JSON, connect a channel and save its profile. Library → select ready MP4s → To YouTube → Generate text and schedule. The hourly schedule runs around the clock in Cyprus time. OpenAI generates text within configured request and budget limits. See the complete [publishing guide](YOUTUBE_PUBLISHING.md).
