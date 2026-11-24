# AI providers

## Local

Apple Silicon uses native MLX Whisper (`mlx-whisper` 0.4.3) with Metal and `word_timestamps=True`; other supported platforms use faster-whisper. Model weights download on first use. PySceneDetect ContentDetector identifies scene changes. Local selection groups phrases using sentence endings and pauses, scores language features, and suppresses excessive overlap or similar text. Scenes are saved and shown on the timeline. Local analysis does not invent a Visual Interest score.

## Gemini

The adapter uses the official `google-genai` SDK and Pydantic structured outputs. Available models come from `client.models.list()`. Users select a model after checking account access; the application does not rely on a fixed default model ID.

Pass A uses 180-second transcript windows with a 150-second stride to select a limited number of complete candidates. Pass B reviews actual audio/video previews at 384 px, 2 fps and AAC, reassessing completeness and eight criteria. Requests use model/schema/content caching and retries for 429/5xx responses. Responses are checked for source video ID, numeric ranges, ordering and time bounds; word timestamps refine boundaries.

A public YouTube URL can be passed as `Part.from_uri(..., mime_type='video/mp4')` without downloading in cloud mode. Support depends on the model, account and video visibility. Local rendering still requires a local source file. Only download material you have permission to use.

Cloud processing requires the global toggle, selected provider and per-job `cloud_consent`. Local mode sends neither video nor transcript to Gemini. Connection testing requests models only. HTTP timeouts, request/token limits, usage metadata and user-provided pricing support estimated costs; these estimates are not an invoice. Provider errors may consume tokens without returning usage. Configure a hard financial limit with the provider.

The secret is stored in a backend file with `0600` permissions, never in SQLite, the frontend, manifests or API responses. Error messages redact its value. Keys are never shell arguments.

## OpenAI

OpenAI analyzes the transcript and then selected frames from promising clips. It requires a downloaded local source; this adapter does not send continuous video or original audio. Requests use the Responses API, `store:false` and a strict JSON schema. Model access, cloud consent, request limits and estimated budgets are configured separately. See [AI connections](AI_CONNECTIONS.md) for setup, token accounting and the separate script/voice pilot.

## References and verification limits

Official implementation references: [Gemini video and YouTube](https://ai.google.dev/gemini-api/docs/video-understanding), [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), [Python SDK](https://github.com/googleapis/python-genai), [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper), and [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing). Availability changes; the account's model list and actual requests determine compatibility.

Mock unit/integration tests verify contracts and persistence, not cloud response quality. Real Gemini analysis is not verified for a user's installation until it has succeeded with that user's key.
