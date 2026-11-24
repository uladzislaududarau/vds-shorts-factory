# Automatic Shorts publishing

Connect your channel once through Google OAuth. A Chrome download session and OpenAI/ElevenLabs keys do not authorize channel uploads.

## Connect a channel

1. Open `http://127.0.0.1:8765/?settings=publish#settings`.
2. Select a Google Cloud project and enable **YouTube Data API v3**.
3. Configure Branding and Audience in Google Auth Platform. In Testing mode, add your account to Test users.
4. Create a **Web application** OAuth client, such as `VDS Shorts Factory Local Publisher`, with this authorized redirect URI:
   `http://127.0.0.1:8765/api/publishing/oauth/callback`
5. Download the client JSON. In the studio, choose Add OAuth JSON, then Connect channel. Select the intended channel and consent in Google. The application shows its actual name and ID.
6. Set text language, category, made-for-kids audience and realistic altered/synthetic-content disclosure. Save changes. MP4s with AI music require the synthetic-content flag.

Uploading and changing schedules uses `youtube.force-ssl`. Google defines this broadly, including access to videos, comments and captions and the ability to delete them. This module does not delete YouTube videos. Disconnecting removes the local refresh token but does not cancel schedules already saved to YouTube. Revoke Google authorization through your Google account security settings when needed.

External + Testing refresh tokens generally expire after seven days. For persistent use, configure Production and satisfy Google's requirements. Expiry or revocation may require signing in again. Saving JSON alone is insufficient; complete consent and channel selection.

## A batch of 50 videos

1. Select clips in Library and run Generate Reel with the desired framing and AI audio. Wait for MP4s.
2. Select current, ready MP4s → To YouTube.
3. Verify the channel. Choose Hourly schedule or Private for review.
4. Optionally set a start in Cyprus time. Without a date, the app selects the next whole-hour slot at least 10 minutes ahead, continuing existing schedules.
5. Click Generate text and schedule. This consents to sending three output frames and clip context to OpenAI, automatically generating text and uploading selected MP4s to the displayed channel.
6. Publishing shows text, progress, Asia/Nicosia times, errors, Studio links and schedule cancellation.

Each video gets its own title, description, up to five hashtags and up to fifteen tags. Publishing does not change MP4 boundaries or audio. This queue requires 9:16 MP4s up to three minutes. YouTube determines whether they appear as Shorts.

Fifty videos can require up to 50 new OpenAI text requests. The application includes used requests and pending publications in its shared limit. Raise an initial limit of 10 in Settings → AI and models before a larger batch. This does not automatically raise the monetary budget. Budget is checked before each request; insufficient budget stops the job while preserving ready text. Publishing uses the configured OpenAI model even if highlights were selected locally or with Gemini.

## Upload and schedule behavior

- A batch snapshot fixes the channel, MP4 revision, checksum, editing plan and publishing profile.
- Initial uploads are always private. The returned YouTube video ID is saved before scheduling.
- Scheduling sets `privacyStatus=private` and a future `publishAt`. Past times are not submitted because YouTube treats them as immediate publication.
- Slots are 3600 seconds apart, around the clock. Cyprus daylight-saving changes preserve the actual hourly interval.
- Late uploads move to a future free hour; there is no burst of immediate catch-up publications.
- YouTube executes confirmed schedules. Before confirmation, generation and upload require the host computer, local server and internet. Publication status refreshes every minute while the screen is open and through Check YouTube.
- Uploads use 8 MiB chunks and persist checkpoints. Resume checks the upload session and known video ID instead of blindly sending the file again.
- SHA-256 prevents requeuing the same MP4 to the same channel. An expired session with uncertain completion blocks automatic reupload until Studio is checked.
- Pause uploads stops further preparation/transmission, but leaves confirmed schedules intact. An in-flight network request may finish before the pause takes effect.
- A cancelled job can Resume if no video chunk was sent. If transmission started, the app requires a Studio check and avoids creating a duplicate upload.
- Remove schedule leaves the video private. Manage published videos in Studio. If cancellation happens during a request and the result cannot be confirmed, check Studio manually.
- Quota exhaustion pauses uploads while other processing continues. After quota recovery, clear the global upload pause and resume failed jobs. Project and channel limits can differ.

OAuth client JSON, refresh tokens and upload-session URLs are stored only in `.secrets/publishing`, with directory mode `0700` and files `0600`. They do not enter UI API responses, SQLite, logs or ZIP exports. Text and publishing history live in SQLite. Originals are preserved.

This API module does not reproduce every Studio setting. It configures privacy/scheduling, language, category, standard license, audience and AI disclosure, and disables subscriber notifications for batch uploads. Copyright clearance, YouTube processing, Shorts eligibility and monetization are not guaranteed. Replacing audio or removing tags does not establish rights to the images.

## Verification

Automated tests cover batches of 50, atomic rejection of unprepared files, limits, deduplication, OAuth PKCE/state, secret permissions, channel binding, upload-URL validation, resume, ID recovery, private initial upload, scheduling/removal, cancellation during requests, quotas and API contracts. Browser checks at 1440/768/390 pixels cover empty/populated queues, settings and batch dialogs. Populated QA queues are isolated fixtures; these tests publish nothing to a real channel.

A particular user's channel is not verified until OAuth and an actual private test upload succeed. Network uploads in automated tests are mocked.

References: [video insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert), [update](https://developers.google.com/youtube/data/reference/rest/v3/videos/update), [resumable uploads](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol), [OAuth](https://developers.google.com/identity/protocols/oauth2), [AI disclosure](https://support.google.com/youtube/answer/14328491?hl=en).
