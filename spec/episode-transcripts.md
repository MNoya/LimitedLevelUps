# Episode transcripts

Whisper-generated transcripts for talk episodes, served on the episode detail page with chapters, subtopics, click-to-seek, and card-name links. Generation is a local, zero-cost tool (`bot/scripts/generate_transcripts.py`); the site reads rows from the `public_episode_transcripts` view. This spec records the decisions taken and the open items, so the behavior is recoverable without re-reading every commit.

## Pipeline (bot/scripts/generate_transcripts.py)

`--youtube-id <id>` / `--latest N` select targets; point `DATABASE_URL` at local to test or at prod to publish. Steps per episode: download audio (yt-dlp + deno) → Whisper → sentence units → punctuation restore → subtopic structure (one Claude pass) → assemble → clean → card links → upsert.

- **Whisper**: `large-v3`, `--vad_filter True --no_repeat_ngram_size 4 --word_timestamps True --initial_prompt "Alright, welcome everybody. Let's talk about the format today, and go through it step by step."` n=4 (not 3) stops loops without eating natural repeats; the initial prompt fixes lowercase/no-punctuation drift on some episodes. Word timestamps give each sentence its first word's start time.
- **Sentence timing**: `_sentences` rebuilds sentences from the per-word stream so each sentence carries its first word's precise start (a segment-time fallback covers word-JSON-less input).
- **Punctuation restore** (`bot/scripts/punctuation.py`): some episodes lose punctuation for long stretches (a Whisper failure, unrelated to speaker count). Run-on units over 40 words are re-punctuated and truecased by a local ONNX model (`1-800-BAD-CODE/xlm-roberta_punctuation_fullstop_truecase`), then re-split. `condition_on_previous_text=False` was tested and made it far worse (83% run-on), so it is not used.
- **Cleaning** (`_clean_text`): strip muletillas (uh/um/er/hmm), collapse repeated-word stutters (`STUTTER_ANY` = any word 3+ times, `STUTTER_FILLER` = a small filler set 2+ times; "very, very" and "Fair, fair" are preserved), collapse near-duplicate consecutive sentences (char-level ratio >= 0.85, both >= 10 words). Alex's voice (like, kind of, you know) is kept. No LLM text editing.
- **Structure** (one `claude -p`, subscription not API): returns `{subtopics:[{start,title}], paragraphs:[idx]}` over numbered sentences. Subtopics get short Title-Case labels, are suppressed within 30s of a chapter, and are nudged to start on the opening sentence, never a trailing one.
- **Chapters**: from YouTube (`yt-dlp --print "%(chapters)j"`), authoritative for timestamp and boundary. `_chapter_heads` uses the strict rule: a chapter starts at the first sentence whose first word is at or after the YT mark; anything spoken before stays in the previous chapter. The displayed time is the YT time.
- **Card links** (`bot/scripts/card_links.py`, non-Claude fuzzy): scope is `Episode.set_code` (already correct in the DB, including flashback episodes) lowercased to the Scryfall set code. Fetch the set's card names from Scryfall, fuzzy-match against the transcript, correct clear mishearings to the canonical name, and store `cards: [{name}]` per segment. Accept a match when the normalized ratio >= 0.90, or >= 0.80 with an "anchored mishearing" (a distinctive >= 5-char content word matches exactly and every other word is a close mishearing). Basic lands and stopword-only windows are excluded. Only matches that resolve are linked, so the surface text corrected == the linked name. Precision-first: cards referenced by short/first name only are not linked.
- **Scope**: talk episodes with a `youtube_id`; skip categories `{Draft, Sealed, Guest}` (Guest is skipped until speaker detection exists — two-speaker episodes read poorly). Audio-only episodes deferred.
- **`head_t`**: heading segments store the matched sentence's raw spoken time alongside the displayed YT time, for boundary-review deltas.

## Dependencies

Whisper/yt-dlp/ffmpeg/claude are external local tools on PATH (not in requirements). The punctuation extras are pinned in `requirements-transcripts.txt` (local-only, never installed on the bot or in CI): `onnxruntime`, `sentencepiece`, `huggingface-hub`, `numpy`, `pyyaml`. The `punctuators` wrapper library was replaced by an inlined ~90-line reimplementation (`punctuation.py`) to drop an unmaintained dependency and torch; output is byte-identical to the wrapper. Install CPU torch only if a torch-dependent tool is ever reintroduced (it is not now).

## Site (frontend/src/pages/EpisodesPage.tsx)

- **Data**: `TranscriptSegment { t, text, heading?, subheading?, cards? }` read as-is from `public_episode_transcripts.segments`. Card images resolve by name+set through `useCardImageMap` (the app's `/api/card-images` cache) with a Scryfall named-URL fallback.
- **Episode detail layout (lg+)**: one centered column (`max-w-[1120px]`). A sticky full-width header holds `[video | chapters]`: the video is left (aspect-video, unrounded, a 1px outline drawn as an overlay div on top of the iframe so there is no inset gap), the chapters index is a square-bordered panel height-matched to the video (stretched, absolutely filled so a long list scrolls internally). A bg-to-transparent fade sits just under the header so transcript lines dissolve rather than hard-cut. Title/tags under the header; transcript full column width below. The filter/search/sort bar is hidden in the detail view. Mobile keeps the earlier verified layout (full-bleed sticky video, no chapters panel).
- **Chapters panel**: click seeks the video and scrolls to the chapter using the measured sticky-header height as the scroll offset (fixes landing under the header). The currently-playing chapter is highlighted green (playback time captured from the YouTube iframe via `postMessage` infoDelivery). Rows turn green on hover.
- **Transcript**: chapters (main sections) and subtopics are both collapsible. Chapter collapse state lives in `EpisodeDetail` so a jump can auto-expand the target chapter; subtopic collapse is local. Chapter titles are larger (19px) with a larger rotating chevron; subtopics use the smaller chevron. Titles turn green on hover. Card names render as green links: desktop hover shows a card preview (reusing `previewAnchorFor`/`PreviewShell`, image preloaded via `preloadImage` before the box appears, and lazily warmed when the link scrolls into view), mobile tap opens a full-card modal. A card links once per subsection (first occurrence); later mentions in the same subsection render italic.
- **Misc**: category counts in the library rail use the Hanken `font-num`. Timestamps use `font-num` with `leading-none` to align to title baselines.

## Locked decisions worth not relitigating

- Cost is $0: local Whisper on the GPU, `claude -p` on the subscription (keep `ANTHROPIC_API_KEY` unset), yt-dlp free.
- One Claude pass per episode (structure only). Card linking and cleanup are non-Claude.
- Deterministic cleaning only; never delete Alex's function words or voice.
- Chapters are YouTube-authoritative; the strict at-or-after rule replaced an earlier closest-sentence rule that over-reached.
- Punctuation model runs on CPU ONNX; the dependency is local-only and pinned with `==`.

## Open items

- **Existing transcripts predate the strict chapter rule.** The rule changes only new generations; stored episodes keep old boundaries because they store paragraph text, not per-sentence word-timings. Re-transcription (Whisper) is needed to apply it to the current 12.
- **Topic-intro-before-the-mark.** The strict rule keeps a topic intro spoken a few seconds before the YT mark in the previous chapter (the "Land Cyclers" case). Pulling intros forward is semantic, not timing; would need a small Claude/heuristic reassignment pass like the subtopic one.
- **Currently-playing highlight is best-effort.** It reads the raw YouTube iframe via `postMessage`; if delivery is flaky, load the YouTube IFrame Player API instead.
- **Laptop-specific layout not built.** The `[video | chapters]` header applies to all lg+; the alternative "video full-width on top, then transcript | chapters" laptop variant was not implemented.
- **Chapters sidebar summary not wired.** The frontend `Episode` type has no `summary`; only the chapter index is shown.
- **Two-speaker episodes.** Guest is skipped; Set Primers still contain crosstalk stutter artifacts. Real fix is speaker detection/diarization.
- **Near-duplicate collapse leaves one echo.** It drops pure repeats but leaves a single tail-echo of the intro sentence (containment matching is too risky to add off one instance).
- **Card recall vs precision.** Precision-first: short/first-name card references are not linked; heavier mishearings below the anchored threshold are missed.
- **head_t** is only populated on the two episodes re-run during development; a full backfill would need re-transcription.
