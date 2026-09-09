# Episode transcripts — generating and publishing

Transcripts are produced by a **local, zero-cost** pipeline and written straight into the `episode_transcripts` table. The bot never runs this; it is a manual publisher you run on your machine (it needs a GPU, a logged-in browser-free `yt-dlp`, and the `claude` CLI). The site reads the `public_episode_transcripts` view and renders a transcript under any episode that has a row; episodes without one stay unchanged.

## What runs

`bot/scripts/generate_transcripts.py`, one episode at a time:

1. `yt-dlp` downloads the audio (no cookies, no account — a `deno` JS runtime on PATH is all YouTube needs).
2. `whisper-ctranslate2` (large-v3, GPU) transcribes.
3. Sentences group into blocks, YouTube chapters become section headings, and one `claude -p` call decides paragraph breaks (structure only, never touching words).
4. A deterministic clean pass strips muletillas (`uh`, `um`, `er`) and collapses exact repeated-sentence loops. Nothing else is edited: Alex's `you know` / `kind of` / `like` and all word choices stay verbatim.
5. The paragraphs upsert into `episode_transcripts`, keyed on `youtube_id`.

Cost is zero: Whisper is local, `claude -p` runs on the Claude subscription (not the metered API — keep `ANTHROPIC_API_KEY` unset so it can never switch).

## Locked Whisper config (do not lower)

`--no_repeat_ngram_size 4 --initial_prompt "<a punctuated sentence>"`

- `no_repeat_ngram_size 4` stops the decoder's repetition-loop hallucinations. `3` is too aggressive — it also suppresses natural repeats like "you want to … you want to" and eats a word.
- The punctuated `initial_prompt` seeds the decoder's style. Without it, some episodes come out as a lowercase wall with no punctuation (a known faster-whisper drift), independent of the ngram value. The seed fixes it across episodes.

## Prerequisites (one-time)

- The repo venv at `.venv`.
- `yt-dlp` on PATH, plus a `deno` binary on PATH (the JS-challenge solver). Install deno to a stable location (e.g. `~/.deno/bin`), not `/tmp`.
- `whisper-ctranslate2` (the uv tool) with CUDA; the script finds the bundled CUDA libs automatically.
- `ffmpeg` on PATH.
- The `claude` CLI, logged in. Confirm no `ANTHROPIC_API_KEY` in the environment.

## Running it

Local test (writes to the docker Postgres):

```bash
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord \
  .venv/bin/python -m bot.scripts.generate_transcripts --youtube-id <YOUTUBE_ID>
```

Publish to prod (map the Supabase URL onto `DATABASE_URL`):

```bash
DATABASE_URL="$(grep '^SUPABASE_DB_URL=' .env.supabase | cut -d= -f2-)" \
  .venv/bin/python -m bot.scripts.generate_transcripts --youtube-id <YOUTUBE_ID>
```

Selection flags:

- `--youtube-id <id>` (repeatable) — specific episodes.
- `--latest N` — the N most recent eligible episodes not yet transcribed.
- neither — every eligible episode not yet transcribed (a full backfill).
- `--redo` — overwrite episodes that already have a transcript.
- `--no-structure` — skip chapters + the Claude paragraph pass (raw blocks only).
- `--restructure` — re-run only the structuring stage from the local cache, no download or Whisper. Restructures every cached episode, or just the `--youtube-id` ones. Use it after a structuring change to republish without paying for GPU time.
- `--whisper` — force the Whisper audio path, ignore captions (for A/B against the caption source).
- `--no-card-fix` — skip the Claude card-name correction pass, keep only the deterministic linker.
- `--workers N` — backfill in N parallel worker processes, staggered to spare YouTube. Not combined with the usage limit.
- `--usage-limit 248` — serial only: before each episode, read the active 5-hour window's cost via `ccusage blocks --active --json` and stop once it reaches this many USD. Stops if usage cannot be read, so a paced cron never overshoots the session limit.

## Usage tracking

Both Claude passes run with `--output-format json` and append cost and token counts per call to `logs/transcript_usage.jsonl` (gitignored), so a backfill's consumption is auditable after the fact. The `--usage-limit` check reads the live 5-hour window with `ccusage` (run via `npx`, nothing to install). ccusage reports an API-equivalent cost, not the plan percent the Claude app shows, so calibrate the limit once: read the app's percent at a moment, read the same window's cost from ccusage, scale to the percent you want to stop at. A nightly cron scheduled at the session reset with `--usage-limit` drains the fresh window to that ceiling and resumes the next night, so it never blocks your own usage.

## Raw-unit cache and restructuring

Each transcribe run writes the Whisper output it feeds into structuring to `cache/transcripts/<youtube_id>.json` (the sentence units plus the YouTube chapter list, gitignored on this machine). That is the input to the chapter-head and paragraph logic, so `--restructure` can replay structuring from it: it re-runs chapter heads, the Claude paragraph pass and card linking, then overwrites `segments`. No yt-dlp, no Whisper, no GPU — only the `claude -p` paragraph call. An episode transcribed before the cache existed has no file yet; re-transcribe it once with `--redo` to populate it, and every later structuring tweak is a cheap `--restructure`.

Chapter headings snap to the sentence that opens a topic, not the raw chapter timestamp: the host often speaks the intro sentence a few seconds before the marker, so a head pulls back up to two sentences (within 12s) when the preceding sentence is a transition opener or names a word from the chapter title.

Episodes with no editor chapters (most before 2026) get headings from the Claude pass instead: each subtopic carries a `section` flag the model sets only for a major, self-contained part it is highly confident about, and when an episode has no real chapters those promote to headings, spaced at least 60s apart. The rest stay subtopics. Seek is still accurate on these: every sentence carries its Whisper timestamp, so no chapter markers are invented.

Eligible = has a `youtube_id` and is not in the `Draft` / `Sealed` gameplay categories. The run is idempotent and resumable: it skips anything already in `episode_transcripts` unless `--redo`.

## Timing and memory

- About 5-8 minutes per episode on the RTX 3060 (~7.5x realtime), plus ~1-2 minutes for the Claude paragraph call.
- Run it as a normal foreground process or a cron job. (Driving it through Claude Code specifically, put the Whisper step in the foreground — Claude's background-task memory guard will kill a long background job. A plain shell or cron run is unaffected.)

## Backfill and new episodes

- **Backfill:** run with no `--youtube-id` / `--latest` to sweep every eligible episode. Safe to run overnight and re-run; interruptions lose nothing.
- **New episodes:** `--latest 3` after a drop, or a nightly cron that runs the same. The cron needs `deno`, `yt-dlp`, `whisper-ctranslate2`, `ffmpeg` and `claude` on PATH and `SUPABASE_DB_URL` available, and must not set `ANTHROPIC_API_KEY`.

## Not covered yet

Audio-only episodes (podcast entries with no `youtube_id`) are out of scope here. They have no YouTube chapters and their podcast timeline differs from any video, so they will transcribe from `audio_url` directly when that backfill is taken on. Video episodes always transcribe from YouTube so the transcript timeline matches the embedded player and its chapters.
