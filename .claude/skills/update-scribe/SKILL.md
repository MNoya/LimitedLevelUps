---
name: update-scribe
description: Refresh the bundled MTG Scribe event calendar that /event-scribe and the format-schedule tick serve. Recaptures scribe_calendar.json from mtgscribe.com, reports where Scribe's labels and tags have drifted past the code that reads them, fixes what is mechanical, and stages for review. Run it each set rotation, when Scribe corrects a window, and mid-season once it backfills flashback tags. Never commits or pushes.
---

# update-scribe

Recapture the MTG Scribe calendar and reconcile the code with whatever Scribe changed.

## Why this is a skill and not just the script

`snapshot_scribe` is one command. The work is what comes after: MTG Scribe hand-enters its calendar, so every capture brings renamed formats, new tags, mistags and untagged reruns. Those render wrong without anything failing, so the capture has to be read, not just run.

## Prerequisites

- **Must run from a residential IP** (the user's laptop). mtgscribe.com is on SiteGround, whose account-level anti-bot challenges datacenter egress with a 202 HTML page. Railway cannot do this.
- No `DATABASE_URL` needed. Nothing here touches Postgres.

## Workflow

### 1. Keep the outgoing calendar as a baseline

```
git show HEAD:bot/services/scribe_calendar.json > /tmp/scribe_prev.json
```

If that fails because the file is new to `HEAD`, skip it and run step 3 without `--previous`.

### 2. Capture

```
.venv/bin/python -m bot.scripts.snapshot_scribe
```

It requests ~150 days back (long enough to catch in-progress queues, whose start has already passed), stores only events still running or upcoming, and prints how many it dropped plus how far forward the calendar now reaches.

**Read the coverage line.** If it reports fewer than ~30 days out, Scribe has not published the next season yet — say so and stop rather than committing a calendar that will run dry. If it prints `no events kept`, the request was challenged; retry, and if it persists the IP is blocked.

### 3. Report drift

```
.venv/bin/python -m bot.scripts.scribe_drift --previous /tmp/scribe_prev.json
```

Exits 1 when anything needs a look. Each line is one of:

| Finding | What to do |
|---|---|
| `format label 'X' looks like a draft family but is in neither FORMAT_SHORT_NAMES nor DRAFT_FORMATS` | **Fix.** Add the spelling to `FORMAT_SHORT_NAMES` (`bot/services/scribe_formats.py`) and, if it is a mainline draft queue, to `DRAFT_FORMATS` (`bot/commands/event_scribe.py`). Keep the old spellings — Scribe reverts. |
| `set label 'X' matches CODE, CODE — resolves to CODE` | **Verify only.** `_seed_for_label` takes the longest matching name. Confirm the resolved code is the intended set. |
| `set label 'X' matches no seed in ALL_SETS` | **Judge.** An Arena-only product (`Mixed-Up`) legitimately has no seed and renders without a symbol; a real set means it belongs in `ALL_SETS` via the `add-set` skill. |
| `reruns rotated-out CODE with no flashback tag` | **Expected, no code change.** Scribe tags only the next rerun or two at publish. These render as their own set headers and do not announce until it backfills. Report the list so the user knows a mid-season re-run of this skill is worth it. |
| `tag 'X' looks competitive but is not in COMPETITIVE_TAGS` | **Fix.** Add it to `COMPETITIVE_TAGS` (`bot/services/mtgscribe.py`). Then check `build_competitive_reminder` names the right format — `_limited_format` reads Sealed-vs-Draft off the tags, so a Draft-tagged event must not be called Sealed. |
| `set CODE has no frontend/public/set-symbols/...png` | **Fix.** `generate_set_symbols CODE`, then `upload_app_emojis keyrune:code` against **both** the test and prod apps (it targets whichever app `DISCORD_BOT_TOKEN` belongs to). |
| `title 'X' still carries an HTML entity` | **Investigate.** `_parse_event` unescapes once; a survivor means upstream double-encoded. |
| `new tag 'X'` / `new format label 'X'` | **Read.** Most are harmless. A rename shows up as one new label plus its old one going quiet, so cross-check against the render in step 5. |

Apply the mechanical fixes yourself. Ask the user before anything that changes copy or announce routing.

### 4. Align the test fixtures

`!test scribe` and `!test formatschedule` render synthetic events, so they only mirror production if their labels match what Scribe actually publishes now. When step 3 reported a renamed format or a new title shape, update `bot/commands/testscribe.py` and `bot/commands/testformatschedule.py` to use the current spelling. Draw the exact strings from the new calendar, not from memory.

Both files deliberately keep some shapes the calendar no longer shows — a legacy `Arena Championship Qualifier Weekend` title, a mistagged Quick Draft, an oddly-named cube. Those are regression fixtures. Do not "correct" them.

### 5. Eyeball the render

The drift report cannot see layout. Render the schedule and read it:

```
.venv/bin/python -c "
from bot.commands.event_scribe import build_schedule_embed, process_events
from bot.services import mtgscribe
in_progress, upcoming = process_events(mtgscribe.load_events())
print(build_schedule_embed(in_progress, upcoming, {}).description)
"
```

Check the incoming set's block specifically: its main draft line should name the formats correctly (`Premier, Pick2, Trad Draft`), its Arena Direct lines should carry a booster suffix, and no tree line should be empty of both a format and a date.

### 6. Collector Booster window for the incoming set

A Collector Booster Arena Direct pays one box per trophy instead of two, and the window has to be recorded or trophies pay the wrong amount.

```
.venv/bin/python -m bot.scripts.find_collector_window <INCOMING CODE>
```

If it prints a window, add the two paste-ready rows it emits — `CollectorBoosterWindow(...)` in `bot/sets.py` and `{ setCode, startDate, endDate }` in `frontend/src/data/scoring.ts`. These reimplement one rule and must stay in sync. If it prints `no Collector Booster Arena Direct found ... yet`, Scribe has not scheduled it; note that a later run is needed.

### 7. Verify

```
.venv/bin/pytest bot/tests/
```

### 8. Stage, do not commit

```
git add bot/services/scribe_calendar.json
```

Plus any code, fixture, set-symbol and spec file touched. The user reviews before committing — never commit or push here.

If `bot/config.py` or another file also holds unrelated working-tree changes, stage only your hunks (write a patch and `git apply --cached`) so the user's other work stays separate.

### 9. Report

- Event count and how far forward the calendar reaches.
- Every drift finding, split into **fixed** and **no action needed** (the untagged reruns belong in the second group).
- Anything left for the user: a copy decision, a missing set, an emoji upload against the prod app.
- Close with the `!test` invocations that show the change, per the repo convention.

## Notes

- `event-scribe-handoff.md` beside this file is the reference for the tag taxonomy and the known upstream inconsistencies. Update its taxonomy section when a capture teaches something new about how Scribe behaves — not when it merely adds an event.
- Nothing reaches players until the user pushes. `scribe_calendar.json` is served from the repo, so a correction ships on deploy, not on a tick.
- `load_events` logs a warning once the calendar runs out within 14 days. If the user reports seeing that in `logs/bot.log`, this skill is the answer.
