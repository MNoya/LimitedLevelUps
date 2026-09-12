---
name: transcribe
description: Run the LLU episode transcript pipeline on demand from the local box against the latest episodes. Fetches YouTube auto-captions, then runs the Claude structure + card-fix enhance pass, then reports a summary. Writes to prod. Defaults to the 3 most recent episodes; pass a count for more, or a youtube_id for one. Does not drain the backlog. Same pipeline the nightly systemd timer runs.
---

# transcribe

Run the episode transcript pipeline against **prod**. This is the on-demand front door to the same `--auto` pipeline the nightly `llu-transcribe.timer` runs.

Captions can only be fetched from a **residential IP**. YouTube blocks datacenter IPs (Railway included) on the first request, so this always runs on the local box, never on the bot.

## Argument

`$ARGUMENTS` is optional:

- **empty** — the 3 most recent episodes: fetch any missing captions, then enhance them.
- **an integer N** — the N most recent episodes instead of 3.
- **an 11-char YouTube id** — process just that episode (fetch its caption if missing, then enhance it).

This skill never drains the whole backlog. It always works on the newest episodes by count, whatever their age. The historical backlog is handled separately.

## Workflow

### 1. Resolve prod DATABASE_URL

```bash
cd /home/mnoya/Projects/Personal/DischordLeaderboard
export DATABASE_URL="$(grep '^SUPABASE_DB_URL=' .env.supabase | cut -d= -f2-)"
```

If `.env.supabase` is missing or the URL is empty, stop and tell the user.

### 2. Refresh the episode list first

A just-dropped episode is not in the `episodes` table until a media sync runs, so transcribe would find nothing. Always sync first (needs the YouTube key from `frontend/.env`, or it repopulates podcast-only):

```bash
YOUTUBE_API_KEY=$(grep -h YOUTUBE_API_KEY frontend/.env | cut -d= -f2- | tr -d '"') \
.venv/bin/python -m bot.scripts.sync_media
```

Safe to repeat; the feeds are the source of truth. If a brand-new episode still does not appear, its YouTube caption is usually not ready yet (captions land within a day of publish).

### 3. Run the pipeline

Unset `ANTHROPIC_API_KEY` so the `claude` CLI structure pass bills the subscription, not the API. Pick the invocation from `$ARGUMENTS`:

Default (empty) or an integer count N — the N most recent episodes, 3 when empty. No usage throttle: this only touches a few latest episodes, and the caption fetch runs only for episodes actually missing a transcript.

```bash
unset ANTHROPIC_API_KEY
.venv/bin/python -u -m bot.scripts.generate_transcripts --auto --latest 3
```

Single episode (`$ARGUMENTS` is an 11-char id):

```bash
unset ANTHROPIC_API_KEY
.venv/bin/python -u -m bot.scripts.generate_transcripts --auto --youtube-id "$ARGUMENTS"
```

The run is safe to repeat: it is a no-op when nothing is pending, and it skips rows already fetched or already enhanced.

### 4. Report

Read the `=== transcribe auto summary ===` block from the output back to the user: how many captions were fetched, how many are still without a caption (YouTube has not produced auto-captions yet — they land within a day of publish, picked up on a later run), and how many rows were enhanced.

If the caption phase logged repeated rate-limit blocks, the local IP is temporarily banned by YouTube; report that and suggest rerunning later.

## Notes

- Enhanced rows publish to the site immediately through the `public_episode_transcripts` view; no deploy needed.
- The nightly timer (`systemctl --user list-timers llu-transcribe.timer`) runs this same pipeline at 09:00 local, capped to episodes published in the last 30 days (`--since-days 30`), so recent drops land on their own. Reach for this skill to transcribe a new episode now instead of waiting for 09:00.
