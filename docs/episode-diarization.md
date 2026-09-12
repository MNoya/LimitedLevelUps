# Episode diarization

Diarized transcripts for audio-only episodes (podcast episodes with no YouTube video, keyed by `guid`). Where `bot/scripts/generate_transcripts.py --audio-only` produces a flat single-voice Whisper transcript, `bot/scripts/diarize_episodes.py` separates the speakers so interviews read as a host/guest conversation. It is the intended treatment for the Guest category, which is otherwise excluded from the main pipeline via `SKIP_CATEGORIES`.

## What it does, per episode

1. Downloads the audio and runs **whisperx** (faster-whisper large-v3 + wav2vec2 alignment + pyannote diarization) on the GPU, producing word-level timestamps with speaker clusters.
2. Groups consecutive same-speaker sentences into paragraphs and labels each cluster generically by first appearance: `Host`, `Guest`, `Guest 2`. Clusters under `MIN_SPEAKER_WORDS` are folded into the previous real speaker (drops diarization noise).
3. Runs a cheap Claude pass over just the title + first ~20 turns to map the generic labels to real first names (`{"Host":"Alex","Guest":"Marc"}`) and to detect a solo monologue. For a solo it strips the speaker split entirely so the episode renders as a plain transcript. Skip this step with `--no-attribution`.
4. Applies the deterministic `KNOWN_TERMS` sweep from the main pipeline (fixes "Mark" → "Marc", "Limited Level-Ups" garbles, the Patreon URL).
5. Upserts to `episode_transcripts` with `source = whisper-large-v3-diarized`.

Segments carry a `speaker` field. The frontend transcript view renders those as color-coded lanes, with the recurring host (Alex, then Marc, Abram) pinned to the first lane color — see `HOST_PRIORITY` in `frontend/src/pages/EpisodesPage.tsx`. Transcripts with no `speaker` field render exactly as before.

Chapters are **not** produced here. Adding chapters is the separate Claude structure pass (`_subtopics_and_paragraphs` in `generate_transcripts.py`); run it against a diarized episode's stored segments when you want chapter headings.

## One-time setup

whisperx needs torch + pyannote, which conflict with the main venv's ctranslate2 + CPU-torch, so it lives in its own venv **outside** this repo. It is not a project dependency.

- **whisperx venv** (Python 3.12, CUDA torch):
  ```
  ~/.local/bin/python3.12 -m venv ~/whisperx-proto/.venv
  ~/whisperx-proto/.venv/bin/pip install whisperx
  ```
  Confirm CUDA: `~/whisperx-proto/.venv/bin/python -c "import torch; print(torch.cuda.is_available())"` should print `True`.
- **HuggingFace token** (free): create a token at huggingface.co/settings/tokens and accept the license for `pyannote/speaker-diarization-community-1` (the model whisperx's diarizer pulls). Save the token to `~/whisperx-proto/hf_token`.
- Override the defaults with `WHISPERX_BIN` and `HF_TOKEN_FILE` env vars if the paths differ.

## Running it

`DATABASE_URL` must point at the target database (prod: map `SUPABASE_DB_URL` from `.env.supabase`). The Claude pass needs the `claude` CLI on `PATH` and `ANTHROPIC_API_KEY` unset (uses the subscription).

```
# Diarize every audio-only Guest episode under 3h, resumable, skip-on-fail
DATABASE_URL=... python -m bot.scripts.diarize_episodes --category Guest

# A single episode by guid
DATABASE_URL=... python -m bot.scripts.diarize_episodes --youtube-id <guid>
```

Flags: `--category` (default Guest), `--youtube-id` (single guid), `--max-minutes` (default 180), `--redo` (re-diarize done ones), `--no-attribution` (keep generic labels).

## Notes

- Runtime is GPU-bound, roughly 5–10 min per hour-long episode. It skips episodes already in `episode_transcripts` unless `--redo`.
- Solo episodes are detected by the Claude pass, but over-split diarization on a monologue is the main failure mode; if a solo slips through as two speakers, re-run the single episode or strip its `speaker` field.
- Speaker attribution reads only the intro, so if the host is never named there it stays `Host` — pin it by hand in that case.
