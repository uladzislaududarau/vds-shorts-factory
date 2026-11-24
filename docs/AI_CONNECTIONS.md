# OpenAI and ElevenLabs: setup and first test

Updated November 16, 2026. Application: http://127.0.0.1:8765. Refresh the page after updating the server.

## Implemented features

- OpenAI highlight selection: transcript → candidates → selected-frame review. This requires a downloaded local source. The adapter does not send original audio or continuous video to OpenAI.
- Separate Gemini, OpenAI and ElevenLabs keys stored on the backend in `.secrets/`, with directory permissions `0700` and file permissions `0600`. API responses expose only whether a key exists. This is file storage, not macOS Keychain.
- ElevenLabs Voice ID and TTS-model settings, with access testing that does not synthesize speech.
- Short voice samples: MP3 playback/download, character alignment and caching by text/voice/model.
- An AI pilot for one library clip up to 90 seconds: six frames plus available transcript → English script → editing → speech. Results are marked **Needs review**.

The script pilot does not create a final MP4 with original commentary, a storyboard, a legal rights assessment or a YouTube publication. Ordinary clips and sources remain unchanged.

A later addition to ordinary Generate Reel creates new music and revoices the **original recognized words**, without a new script. That mode already produces MP4/ZIP: see [audio replacement](AUDIO_REPLACEMENT.md). The script pilot below remains a separate experiment.

## 1. OpenAI

1. Open [Settings → AI and models](http://127.0.0.1:8765/?settings=ai#settings).
2. Select **OpenAI · transcript + frames**.
3. Enter your API key and click Save changes or Test connection; testing first saves the entered settings.
4. Test connection retrieves models through `/v1/models`. It does not generate text, check your balance or guarantee vision/structured-output support. Restricted keys need the relevant model-read and Responses permissions.
5. Select an accessible model supporting images and structured outputs. No universal model ID is inserted because account access and capabilities differ.
6. Enable **Allow cloud processing**.
7. Enter current input/output prices per million tokens for the selected model. The initial estimated OpenAI budget is $2 and the request limit is 10 generation attempts. Both are cumulative, not daily. An active USD budget blocks generation without prices. Update prices when changing models.
8. Save settings.

Ordinary analysis also requires submission consent at launch. Without it, the application uses local heuristics. Download the source before using OpenAI; a URL alone does not grant this adapter video access.

Only the backend calls `api.openai.com`, using the Responses API, `store:false` and a strict JSON schema. With an active budget, `/v1/responses/input_tokens` counts actual multimodal input before generation, with allowances for schema/format overhead and maximum output tokens including reasoning. Local estimates do not replace provider billing. Errors, incomplete responses and unknown usage are not described as free. Generation has no automatic retries. A valid paid response is cached even if the job was paused while awaiting it.

## 2. ElevenLabs

1. Open [Settings → Voice](http://127.0.0.1:8765/?settings=voice#settings).
2. Enter your ElevenLabs API key and copy the chosen Voice ID from ElevenLabs → Voices.
3. Save and Test connection. This checks the selected voice and available TTS models without synthesis. If `voices_read` / `models_read` are disabled, the app reports that but still allows a separate synthesis sample with Text to Speech permission and access to the chosen voice. Catalog-read access is not required just to synthesize.
4. Select an available TTS model. The initial value is `eleven_multilingual_v2`; availability depends on the account.
5. Enter up to 1200 characters in Voice sample, confirm consent and click Create voice sample.
6. Listen or download the MP3.

The initial limit is 10 synthesis attempts. This is a request count, not a monetary budget. Monitor actual costs/credits in ElevenLabs. Repeating identical text, voice and model uses cached audio. Changing text or voice hides the old sample. Synthesis errors do not trigger automatic paid retries.

Check commercial-use terms for the chosen plan and voice separately. A successful voice sample does not establish a license.

## 3. Complete pilot cycle

1. Open [Settings → AI pilot](http://127.0.0.1:8765/?settings=pilot#settings).
2. Select a clip up to 90 seconds from a downloaded source. The pilot uses the candidate's start/end boundaries, rather than arbitrary segments from its editing plan.
3. Consent to sending frames/transcript to OpenAI and script text to ElevenLabs for speech.
4. Click Generate OpenAI script. Check observations and timestamps and independently verify conclusions. A real frame reference does not prove that its interpretation is correct.
5. Edit the English text and click Voice script with ElevenLabs.
6. Listen and download MP3. Combining that speech into a final video remains a later development stage.

The pilot does not research the internet, verify legal rights or publish videos. Scripts and hypotheses need editorial review. The latest generated sample persists on disk and reopens on return; matching speech is restored if the audio still exists. Manual draft edits live in the current screen, so copy them before navigating away or reloading. Audio samples are temporary: Storage → Clear temporary cache removes them. Cleanup is blocked during AI/TTS requests.

## Verification

Backend tests use isolated SQLite and mocked providers to check JSON contracts, usage/budgets, no automatic retries, paid-result preservation on pause, key redaction in responses/validation errors, consent and timestamp validation. FFmpeg actually decodes the MP3 fixture.

Browser checks at 1440/768/390 pixels cover settings, pilot consent, drafts, editing, errors and MP3 playback. Provider responses in those browser checks are simulated and spend no credits.

Historical local checks with user-provided keys exercised actual OpenAI script generation and ElevenLabs speech. A first script read timestamps aloud; a refined prompt produced a script without them and approximately 31 seconds of speech. The MP3 fully decoded. Catalog-read permission was absent on the ElevenLabs key, but synthesis using the specified Voice ID worked. These checks demonstrate integration, not factual or editorial accuracy of future scripts. Pricing must be checked for the selected model when configuring a new installation; do not rely on historical test prices. Never include keys in chat, reports or screenshots.

## Service documentation

- OpenAI: [images](https://developers.openai.com/api/docs/guides/images-vision), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create).
- ElevenLabs: [speech with timestamps](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps).
