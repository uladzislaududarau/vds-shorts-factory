# Original video commentary: implementation plan

Date: November 16, 2026. Status: design proposal, not a list of implemented features. This document does not authorize public uploads.

Later updates added OpenAI/ElevenLabs settings and a separate frames → English script → voice pilot. That is not the complete production workflow described here. See [AI connections](AI_CONNECTIONS.md) for the pilot. A separate general-purpose [publishing module](YOUTUBE_PUBLISHING.md) was also implemented later; the commentary-specific editorial gate below remains proposed.

## Goal and boundaries

Create original English-language Shorts with observations, arguments and explanatory graphics from authorized material. The result should add editorial value. Image changes, new speech or metadata cleanup alone do not guarantee freedom from copyright claims, strikes, restrictions or monetization issues.

Keep ordinary clipping as a separate mode. Add Original commentary: source → verified observations → script → voice → storyboard → edit → review → publishing queue.

## Baseline when this plan was written

| Area | Existing foundation | Missing in the proposed workflow |
|---|---|---|
| Material | Authorized YouTube download, local originals, SHA-256 and rights fields | Validation of legal basis and supporting documents |
| Analysis | MLX Whisper, scenes, local heuristics and Gemini preview review | Evidence-backed observations, fact checking and editorial topics |
| Scripts | Candidate titles/descriptions | Independent scripts linking claims to evidence |
| Speech | Source audio and synthetic macOS voices in test fixtures | Production TTS provider and licensed voice selection |
| Editing | FFmpeg, segments, crop, captions, normalization and MP4/QC | Script-based storyboard, new speech and meaningful callout/comparison templates |
| Review | Technical QC and declared rights fields | Editorial rules, usage documents and manual review states |
| Publishing | Agreed hourly Asia/Nicosia concept | At the time, OAuth upload, calendar and actual automated publishing |

This table is historical. Subsequent TTS, audio replacement and publishing are documented separately; they do not implement the full commentary workflow.

Local heuristics are not a visual-fact analyzer: `visual_interest` is zero. Existing Gemini review assesses candidate fragments rather than researching an entire trailer. Model access and quality require a real pilot.

## First version

- One topic area: gaming trailers/gameplay with an established usage basis.
- One English voice and script language.
- Vertical 9:16, approximately 30–60 seconds, one independent topic per video.
- Several short illustrative excerpts plus original captions, explanation and emphasis. Aim for 70–120 script words, then measure actual speech duration.
- Three limited graphic templates: detail highlight, annotated freeze frame and comparison of two authorized sources.
- No new photorealistic scene generation or imitation of someone else's recognizable voice.
- Do not carry original trailer music by default. Use new speech and additional music only under established terms.
- Do not force a topic count. Five supported topics should produce five videos rather than dozens of near-duplicates.

## 1. AI Video Analyzer

Process images together with audio and scene boundaries. Store observations rather than only free-form model prose. Each observation needs a source ID/version, exact timestamps, a saved frame/segment reference, an optional image region, an observed fact separated from interpretation, an external source for claims beyond what is visible, review status, uncertainty reason and analysis/model version.

A topic template might be: a construction is visible → show the detail → explain its possible significance. This must not become a claim of confirmed gameplay functionality without evidence. Label hypotheses as hypotheses.

For the first version, external evidence is editor/user-supplied primary material. Autonomous web research belongs to a later stage. Comparisons require the second source itself and permission to use it. The output is topic cards with evidence. Frame references do not by themselves establish interpretation accuracy.

## 2. Original Script Generator

Build scripts from verified topics rather than paraphrasing source dialogue. Structure: thesis/question → observation → explanation/comparison → conclusion. Link every checkable claim to evidence. Do not add unsupported dates, game features, developer intentions or release promises.

Store English text, version, claims, sources, phrase-to-frame mapping and planned duration. Check repeated channel topics and similarity to source speech or other scripts. Similarity is an editorial signal, not legal proof of originality.

## 3. AI Voiceover

Connect one TTS provider with suitable commercial terms for the chosen voice. A service returning speech alignment can support the prototype; for example, ElevenLabs character timestamps can be grouped into word timestamps.

Store text, voice/model IDs, settings, audio, duration and alignment. Cache identical generation. A changed script/voice creates a new version. Captions use the approved script rather than a second speech recognizer's transcription.

Include a game-name pronunciation dictionary, auditioning, spending limits and bounded retries. Verify plan and voice terms before selecting a provider; catalog availability is not a usage license.

## 4. Smart Video Editor

Create a new editing plan using actual speech duration and the existing FFmpeg renderer. Add illustration selection for each claim, trims/freezes/pans to relevant regions, frames/arrows/short annotations, comparisons of real sources, source-speech replacement, new-speech caption alignment and readability/duration/QC checks.

Use regions of interest for environmental details; face tracking cannot identify arbitrary objects. New layouts need not use blur by default. Validate all coordinates and timestamps. Uncertain detail localization needs review rather than a random crop. Start with limited templates; general automatic directing is a later research goal.

## 5. Rights and Editorial Gate

Check documented conditions and editorial/technical signals. This is not a legal certificate or Content ID predictor.

The current rights checkbox is a user declaration. Add a permissions register containing authorization type, document/link, scope, commercial terms, attribution, expiry and manual confirmation. Public availability on YouTube is not permission.

Before expensive generation, check the established basis for source/audio use and the intended use. Before release, check evidence, original analysis, repetition, images/voice usage and QC.

| State | Action |
|---|---|
| READY | Configured checks passed and a person already confirmed the usage basis; eligible for an authorized publishing queue |
| REVIEW | Unclear rights, doubtful fact, questionable illustration or another explained concern; remains local pending review |
| BLOCKED | A mandatory check failed or a known prohibition applies; do not upload |

Do not show “0% risk” or “legally safe.” Do not decide fair use from a percentage of changed pixels or excerpt duration. Disputed legal exceptions require qualified human assessment; AI must not automatically mark those cases READY.

Keep decision reasons and evidence inside the project. Meet attribution requirements in publication descriptions. MP4 tag removal does not cancel attribution. Choose AI disclosure based on content and applicable rules, rather than attempting to hide it through file changes.

## Automatic publishing

The planned cadence is hourly, 24/7, in Asia/Nicosia. Only READY videos enter an authorized schedule. REVIEW/BLOCKED do not become eligible merely to fill slots. Leave empty slots when nothing qualifies.

Channel OAuth, resumable private-first uploads, video IDs, scheduling, deduplication and cancellation are a separate module. Download sessions do not replace upload OAuth. That general module was implemented after this plan; commentary-specific READY/REVIEW/BLOCKED integration remains to be built.

## Data, queue and spending

Add separate commentary entities for evidence, script versions, voice tracks, storyboards, gate decisions and publishing links. Do not silently convert ordinary clips into script projects.

Queue stages: analysis → script → review → TTS → storyboard → render → final gate. Save and independently retry each stage. New input versions invalidate only dependent results. API/upload credentials must never enter logs or exports.

Track visual analysis, text generation and TTS separately. Add per-project and daily limits, caching and budget stops. Measure price/speed during the pilot; do not promise fixed costs or time before selecting models, voices and sources.

## Implementation sequence and acceptance

1. **Content pilot.** Choose 2–3 authorized sources and create evidence/script cards. A person checks every claim and topic's independence. No public uploads.
2. **First complete slice.** Produce one English MP4 from a checked topic using TTS, synchronized captions and one graphic template; then test 5–10 distinct videos. Assess pronunciation, meaning, imagery, readability, cost and time.
3. **Product workflow.** Add UI, batches, versions, limits, all three templates, a REVIEW queue and permission-register rules. Verify pause/restart recovery without unnecessary paid repeats.
4. **Publishing integration.** Connect the channel separately and verify an authorized test upload, scheduling and REVIEW/BLOCKED rejection before enabling READY batches.

Acceptance requires claims checked against actual sources, an independent script rather than a paraphrased monologue, graphics showing the intended details, speech/caption alignment, complete audio and successful MP4 QC. Correct/remove unsupported claims or send them to review. Do not promise numeric accuracy without measurement.

Tests must prevent uploads for missing usage basis, damaged files, invalid coordinates, incomplete speech, exhausted budgets or REVIEW/BLOCKED states. Restart must not create duplicate uploads.

## Feasibility

Engineering confidence is high for queues, TTS integration, timestamp synchronization, limited graphics, versions, technical checks, review states and API publication. Observation quality, interpretation, script originality and relevant image selection require a content pilot. Complete discovery of important details and professional direction without review are not guaranteed.

Claims/strikes, legality of each excerpt, automatic fair-use decisions, monetization approval and audience success cannot be guaranteed. Before implementation choose a licensed provider/voice, visual-analysis model and API access, authorized pilot sources, budget and initial template. Start with one genre, one voice and one channel.

## Source references

- [YouTube monetization policies](https://support.google.com/youtube/answer/1311392?hl=en): reused/inauthentic content and copyright are distinct; meaningful commentary does not automatically clear rights.
- [Fair use on YouTube](https://support.google.com/youtube/answer/9783148?hl=en): applicability depends on circumstances and jurisdiction.
- [AI disclosure](https://support.google.com/youtube/answer/14328491?hl=en): substantial realistic synthetic changes may need disclosure.
- [ElevenLabs timed speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps) and [TTS capabilities/commercial use](https://elevenlabs.io/docs/overview/capabilities/text-to-speech).

These references describe rules and capabilities; they do not approve a particular future video or license a particular trailer.
