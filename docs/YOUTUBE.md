# YouTube → analysis → clips

## Connect an account

1. Open Add video → YouTube, or Settings → YouTube.
2. Click **Sign in to YouTube**. A separate Google Chrome window opens with the studio's dedicated profile. Sign in on YouTube; enter your password and two-factor code only in Google.
3. Return to the studio and click **I signed in — connect**. On macOS, allow Python to access Chrome Safe Storage when prompted so it can read this browser session. Only the dedicated profile is read, never your regular Chrome profile.
4. Wait for **Session connected**. This confirms that a session was saved; access to a specific video is checked by YouTube during download.

For later downloads, the studio refreshes the session automatically from the connected profile. If sign-in expires or YouTube requests verification, reopen sign-in, finish verification and click **Refresh session**. The account must be able to play the video, including any YouTube age check.

If Chrome is unavailable or session access is blocked, expand **Connect using cookies.txt** and select a Netscape-format file exported only for youtube.com. Only YouTube-domain cookies are saved; other domains are discarded. Do not send passwords, codes or cookie files in chat.

## Download and cut

1. Paste a single-video URL. Enable **Use my account** for restricted videos.
2. Keep **Download source with yt-dlp** enabled. The studio selects the best available format up to 1080p, preferring H.264 + AAC, then merges video and audio.
3. Keep **Find highlights after download** enabled. Duration, language, profile and threshold come from Settings. Cloud analysis needs separate consent; otherwise local analysis is used.
4. State the basis for your usage rights, confirm processing and click **Download and analyze**.
5. Queue shows access checking → download size/speed → merging → source import. Transcription and analysis are queued next.
6. In Video Analysis, choose a moment, open Clip Studio and create an MP4. The source is already local and does not need another download. See the [user guide](USER_GUIDE.md) for editing.

Disable automatic analysis to save only the source. Repeating a completed URL uses the existing file. Duplicate unfinished downloads of the same URL are combined into one job.

## Queue behavior

One video downloads at a time. Pause/Cancel stops the task's own yt-dlp and FFmpeg processes. Resume/Retry continues existing `.part` files when YouTube supports resuming that stream. A normal Stop leaves the job paused; after a crash, Running jobs return to Queued. Stream URLs refresh on restart and their secret values are not stored in SQLite.

Each download receives a separate private session copy, so disconnecting does not corrupt an in-flight request. Cancel that job to interrupt it. New downloads after disconnect do not use the account. **Disconnect from studio** removes the saved studio session; use YouTube's menu to sign out of Google in the dedicated window.

## Storage and limits

- Sign-in profile: `.secrets/youtube/browser/`; session: `.secrets/youtube/cookies.txt`. Directory permissions are `0700`, files `0600`. They are excluded from Git and HTTP responses. The local user and administrators can still read them.
- Temporary video: `data/temp/youtube-<job_id>/`; completed source: `data/sources/`. SQLite stores the URL, rights, status and progress, without cookie values.
- YouTube sessions are not sent to Gemini. AI transcript/preview submission requires separate consent.
- Downloads require disk space, FFmpeg, Node.js 22+ and compatible yt-dlp / yt-dlp-ejs versions. Run doctor to check these.
- Sign-in enables your account's existing access. It does not remove DRM, paid-access requirements or regional restrictions. YouTube can throttle automation or change formats; failed jobs show the specific reason.

This uses yt-dlp's cookie mechanism. Google OAuth is not suitable for its downloader: [yt-dlp OAuth documentation](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#logging-in-with-oauth). JavaScript setup: [official EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Uploading to a channel uses a separate [publishing OAuth connection](YOUTUBE_PUBLISHING.md).
