---
name: update-schedule
description: Refresh the bundled event calendar that /event-schedule, the format-schedule tick and the set channel's pinned schedule serve. Captures MTG Scribe for tabletop events, coverage and Constructed, merges the set's official MTG Arena event schedule article for the Arena queues, reports drift past the code that reads them, fixes what is mechanical, and stages for review. Run it when Wizards posts a set's Arena schedule, each set rotation, when either source corrects a window, and mid-season once Scribe backfills flashback tags. Never commits or pushes.
---

# update-schedule

Rebuild `event_calendar.json` from two sources and reconcile the code with whatever they changed.

## Two sources

- **Wizards' MTG Arena event schedule article** owns the Arena queues: Premier, Pick-Two, Traditional, Quick, Sealed, Flashback, Contender, Arena Direct, Cube, Omniscience, Mixed-Up and the Arena Championship Qualifiers. Wizards posts it weeks before release, and when the two disagree it is the one that is right.
- **MTG Scribe** keeps everything else: Pro Tours, Worlds, Regional Championships, Spotlight Series, prerelease and release dates, and Constructed events.

`event_calendar.json` keeps Scribe's shape for both sources, because every reader parses Scribe-style titles and tags.

## Why this is a skill and not just the scripts

Each source is one command. The work is what comes after: Scribe hand-enters its calendar, so every capture brings renamed formats, new tags, mistags and untagged reruns, and a Wizards article can phrase a line the parser has not seen. Those render wrong without anything failing, so the result has to be read, not just run.

## Prerequisites

- **The Scribe capture must run from a residential IP** (the user's laptop). mtgscribe.com is on SiteGround, whose account-level anti-bot challenges datacenter egress with a 202 HTML page. Railway cannot do this. The Wizards article fetches from anywhere.
- No `DATABASE_URL` needed. Nothing here touches Postgres.

## Workflow

### 1. Keep the outgoing calendar as a baseline

```
git show HEAD:event_calendar.json > /tmp/scribe_prev.json
```

If that fails because the file is new to `HEAD`, skip it and run step 4 without `--previous`.

### 2. Capture Scribe

```
.venv/bin/python -m bot.scripts.snapshot_scribe
```

It requests ~150 days back (long enough to catch in-progress queues, whose start has already passed), stores only events still running or upcoming, and prints how many it dropped plus how far forward the calendar now reaches. A short reach is fine at this point, since step 3 fills the Arena season. If it prints `no events kept`, the request was challenged; retry, and if it persists the IP is blocked.

### 3. Merge the Arena event schedule

Find the incoming set's article. Its URL is usually `https://magic.wizards.com/en/news/mtg-arena/<set-name>-event-schedule`, for example `star-trek-event-schedule`; when that 404s, search the web for `<set name> MTG Arena event schedule`. Then:

```
.venv/bin/python -m bot.scripts.arena_schedule <article URL>
```

It reads the article's **Full Event Calendar** section, writes each Arena queue in Scribe's shape (queues open 11 AM ET and close at 11 AM ET the day after their last listed day; play-ins 9 AM to 6 AM ET; qualifier weekends midnight to midnight; Midweek Magic 5 PM ET), and merges them over the capture. A queue with the same title as a captured one stretches that window instead of duplicating it, so the article's dates win.

**Read the `skipped` lines.** Constructed events are expected there (Scribe covers them), and so are the Arena Limited Championship events, whose format the article does not state. Anything Limited in that list means the article phrased a line the parser does not know: extend `bot/scripts/arena_schedule.py` and its tests rather than hand-writing the event.

If Wizards has not posted the article yet, say so. With fewer than ~30 days of Arena queues left in the calendar, stop rather than committing a calendar that will run dry.

### 4. Report drift

```
.venv/bin/python -m bot.scripts.scribe_drift --previous /tmp/scribe_prev.json
```

Exits 1 when anything needs a look. Each line is one of:

| Finding | What to do |
|---|---|
| `format label 'X' looks like a draft family but is in neither FORMAT_SHORT_NAMES nor DRAFT_FORMATS` | **Fix.** Add the spelling to `FORMAT_SHORT_NAMES` (`bot/services/scribe_formats.py`) and, if it is a mainline draft queue, to `DRAFT_FORMATS` (`bot/commands/event_scribe.py`). Keep the old spellings — Scribe reverts. |
| `set label 'X' matches CODE, CODE — resolves to CODE` | **Verify only.** `seed_for_label` takes an exact set name first, then the longest matching name. Confirm the resolved code is the intended set. |
| `set label 'X' matches no seed in ALL_SETS` | **Judge.** An Arena-only product (`Mixed-Up`) legitimately has no seed and renders without a symbol; a real set means it belongs in `ALL_SETS` via the `add-set` skill. |
| `reruns rotated-out CODE with no flashback tag` | **Expected, no code change.** Scribe tags only the next rerun or two at publish. These render as their own set headers and do not announce until it backfills. Report the list so the user knows a mid-season re-run of this skill is worth it. |
| `tag 'X' looks competitive but is not in COMPETITIVE_TAGS` | **Fix.** Add it to `COMPETITIVE_TAGS` (`bot/services/mtgscribe.py`). Then check `build_competitive_reminder` names the right format — `_limited_format` reads Sealed-vs-Draft off the tags, so a Draft-tagged event must not be called Sealed. |
| `set CODE has no frontend/public/set-symbols/...png` | **Fix.** `generate_set_symbols CODE`, then `upload_app_emojis keyrune:code` against **both** the test and prod apps (it targets whichever app `DISCORD_BOT_TOKEN` belongs to). |
| `premier event 'X' has no PREMIER_SCHEDULES entry` | **Fix.** Look up the event's official schedule on magic.gg, the fact sheet or viewer's guide, and add a `PremierSchedule` to `PREMIER_SCHEDULES` (`bot/services/watch_party.py`): its timezone, each day's start, end and subject, and for a Pro Tour its `ordinal` such as `first PT of 2027`. With no published times, add an estimate and say so in the report. The watch party channel builds its Scheduled Event and announcement from this row. |
| `Arena Powered Cube <dates> is missing from cube_variants.json` / `has different dates in` | **Fix.** Add or correct the printed row in that cube's `seasons` in `cube_variants.json`. The bot syncs `cube_seasons` from the registry on every startup, so the season board fills in on deploy with no seed step, and a season stays hidden until its first draft. |
| `title 'X' still carries an HTML entity` | **Investigate.** `_parse_event` unescapes once; a survivor means upstream double-encoded. |
| `new tag 'X'` / `new format label 'X'` | **Read.** Most are harmless. A rename shows up as one new label plus its old one going quiet, so cross-check against the render in step 6. |

Apply the mechanical fixes yourself. Ask the user before anything that changes copy or announce routing.

### 5. Flashback season starts

A set's LLU flashback season starts the day before Arena's first flashback queue inside the set's window, and it drives the daily Bonus Pod, the format vote and the format allocator. Two checks:

- **Freeze seasons that have started.** Captures drop finished events, so a season derived from them shifts on the next run. Every set whose season has already begun needs its start pinned in `SEASON_START_OVERRIDES` (`bot/services/championship_dates.py`), taken from the baseline calendar before the capture dropped it.
- **Check the incoming set.** Print `season_start(<CODE>)`. When Arena's flashbacks begin right at release, the derived start ends the set's daily Bonus Pods within days. Ask the user whether LLU's season should follow Arena or start later; TRK was pinned to Dec 1 to keep three weeks of daily Star Trek pods.

### 6. Align the test fixtures

`!test scribe` and `!test formatschedule` render synthetic events, so they only mirror production if their labels match what the calendar actually holds now. When step 4 reported a renamed format or a new title shape, update `bot/commands/testscribe.py` and `bot/commands/testformatschedule.py` to use the current spelling. Draw the exact strings from the new calendar, not from memory.

Both files deliberately keep some shapes the calendar no longer shows — a legacy `Arena Championship Qualifier Weekend` title, a mistagged Quick Draft, an oddly-named cube. Those are regression fixtures. Do not "correct" them.

### 7. Eyeball the render

The drift report cannot see layout. Render the schedule and read it:

```
.venv/bin/python -c "
from bot.commands.event_scribe import build_schedule_embed, process_events
from bot.services import mtgscribe
in_progress, upcoming = process_events(mtgscribe.load_events())
print(build_schedule_embed(in_progress, upcoming, {}).description)
"
```

Check the incoming set's block specifically: its main draft line should name the formats correctly (`Pick2, Premier, Trad Draft`), its Arena Direct lines should carry a booster suffix, and no tree line should be empty of both a format and a date. The same render is what the set channel's pinned schedule shows.

### 8. Collector Booster window for the incoming set

A Collector Booster Arena Direct pays one box per trophy instead of two, and the window has to be recorded or trophies pay the wrong amount.

```
.venv/bin/python -m bot.scripts.find_collector_window <INCOMING CODE>
```

If it prints a window, add the two paste-ready rows it emits — `CollectorBoosterWindow(...)` in `bot/sets.py` and `{ setCode, startDate, endDate }` in `frontend/src/data/scoring.ts`. These reimplement one rule and must stay in sync. If it prints `no Collector Booster Arena Direct found ... yet`, neither source has scheduled it; note that a later run is needed.

### 9. Verify

```
.venv/bin/pytest bot/tests/
```

### 10. Stage, do not commit

```
git add event_calendar.json
```

Plus `cube_variants.json` and any code, fixture, set-symbol and spec file touched. The user reviews before committing — never commit or push here.

If `bot/config.py` or another file also holds unrelated working-tree changes, stage only your hunks (write a patch and `git apply --cached`) so the user's other work stays separate.

### 11. Report

- Event count and how far forward the calendar reaches, from each source.
- Every drift finding, split into **fixed** and **no action needed** (the untagged reruns belong in the second group).
- Anything left for the user: a season-start decision, a copy decision, a missing set, an emoji upload against the prod app.
- Close with the `!test` invocations that show the change, per the repo convention.

## Notes

- `event-scribe-handoff.md` beside this file is the reference for Scribe's tag taxonomy and its known upstream inconsistencies. Update its taxonomy section when a capture teaches something new about how Scribe behaves — not when it merely adds an event.
- Nothing reaches players until the user pushes. `event_calendar.json` is served from the repo, so a correction ships on deploy, not on a tick.
- `load_events` logs a warning once the calendar runs out within 14 days. If the user reports seeing that in `logs/bot.log`, this skill is the answer.
