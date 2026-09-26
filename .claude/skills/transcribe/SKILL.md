---
name: transcribe
description: Run the LLU episode transcript pipeline on demand from the local box against the latest episodes. Fetches YouTube auto-captions, then runs the Claude structure + card-fix enhance pass, then reports a summary. Writes to prod. Defaults to episodes published in the last 30 days; pass a day count for another window, or a youtube_id for one episode. Does not drain the backlog.
---

# transcribe

Run the episode transcript pipeline against **prod**. This is the on-demand front door to the same `--auto` pipeline the nightly `llu-transcribe.timer` runs.

Captions can only be fetched from a **residential IP**. YouTube blocks datacenter IPs (Railway included) on the first request, so this always runs on the local box, never on the bot.

## Argument

`$ARGUMENTS` is optional:

- **empty**: episodes published in the last 30 days. Fetch any missing captions, then enhance every basic transcript
- **an integer N**: the last N days instead of 30
- **an 11-char YouTube id**: just that episode. Fetch its caption if missing, then enhance it

This skill never drains the whole backlog. It touches only episodes inside the day window, the same window the nightly timer uses. Draft, Guest and Sealed episodes are skipped, except Sealed titles that match `pre-?release`, so the Prerelease Guides are included. The historical backlog is handled separately.

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

Default (empty) or an integer day count N: pass N in place of 30 when given. No usage throttle: the window holds only a few pending episodes, and the caption fetch runs only for episodes missing a transcript.

```bash
unset ANTHROPIC_API_KEY
.venv/bin/python -u -m bot.scripts.generate_transcripts --auto --since-days 30
```

Single episode (`$ARGUMENTS` is an 11-char id):

```bash
unset ANTHROPIC_API_KEY
.venv/bin/python -u -m bot.scripts.generate_transcripts --auto --youtube-id "$ARGUMENTS"
```

The run is safe to repeat: it is a no-op when nothing is pending, and it skips rows already fetched or already enhanced.

### 4. Report

Read the `=== transcribe auto summary ===` block from the output back to the user: how many captions were fetched, how many are still without a caption because YouTube has not produced auto-captions yet, and how many rows were enhanced. Auto-captions land within a day of publish and a later run picks them up.

Name each fetched or enhanced episode by the site URL the summary prints under its count, `https://limitedlevelups.com/episodes/transcripts/<slug>`. Never show the YouTube id.

Leave out the `$` figures on the `structure:` and `card-fix:` log lines. They are the `claude` CLI's API-equivalent estimate, and with `ANTHROPIC_API_KEY` unset the run draws on the Claude subscription's usage. Nothing is billed.

If the caption phase logged repeated rate-limit blocks, the local IP is temporarily banned by YouTube; report that and suggest rerunning later.

## Notes

- Enhanced rows publish to the site immediately through the `public_episode_transcripts` view; no deploy needed.
- The nightly timer (`systemctl --user list-timers llu-transcribe.timer`) runs `~/.local/bin/llu-nightly-transcripts.sh` at 09:00 local. That script runs only the caption phase, `--basic --since-days 30`, so new episodes get a basic transcript on their own and stay basic until this skill enhances them.
