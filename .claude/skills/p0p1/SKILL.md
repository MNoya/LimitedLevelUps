---
name: p0p1
description: Set up or refresh the P0P1 contest for a Magic set. Takes a set code (e.g. HOB). Pulls the card pool from Scryfall, decides whether the pool is complete enough to open voting, and schedules the contest window. Safe to re-run at any point in spoiler season. Never commits.
---

# p0p1

`/p0p1 <CODE>` is the only call needed to bring a P0P1 contest live, at any point in spoiler
season. Run it when previews start, run it again when the gallery fills in, run it the day the set
completes. It works out what the set needs each time.

## Argument

`$ARGUMENTS` is a set code, e.g. `HOB`. If none is given, ask the user and stop.

Optional, and rarely needed:

- `--deadline YYYY-MM-DD` — when voting closes. Defaults to the Arena release instant. Pass it on
  the first run of a contest whose deadline lands earlier than release, or later to move a deadline.
- `--opens YYYY-MM-DD` — schedule voting to open on a future date instead of as soon as the pool
  ships. Only needed to hold a complete pool back.
- `--results YYYY-MM-DD` — when results land. Defaults to `release + 28 days`, independent of
  `--deadline`, so an early voting deadline doesn't shorten the 17lands data window. Pass it to
  hand-pick a results date instead.
- `--hybrid-common-slots` / `--no-hybrid-common-slots` — whether hybrid cards can fill a
  mono-color common slot. Defaults on for a brand-new contest; an already-scheduled contest keeps
  whatever it already has unless you pass the flag explicitly.

Bare dates mean noon ET. A full ISO timestamp pins any other instant.

## Workflow

### 1. Confirm the set exists

The set code must be in `bot/sets.py` (`ALL_SETS`), which is where the name and the noon-ET release
instant come from. If it's missing, run the `add-set` skill first and stop.

### 2. Run it

```
.venv/bin/python -m bot.scripts.fetch_p0p1_cards --set-code <CODE> [--deadline <DATE>] [--results <DATE>]
```

The script pulls Scryfall, writes `cards-<code>.ts`, prints a slot-coverage table, and then decides
the window in `p0p1_contests.json` on its own:

| situation | what it does |
| --- | --- |
| pool short of a slot, unscheduled | adds no entry, set stays hidden on `/p0p1` |
| pool complete, unscheduled | opens voting now, contest goes live when this ships, results at `release + 28d` |
| already scheduled | leaves the window alone, only the pool is refreshed |
| `--opens` / `--deadline` / `--results` given | reschedules, keeping whichever values were not passed |
| `--hybrid-common-slots` given, new or existing contest | writes the flag as passed |

Relay its output: card count, layout breakdown, slot coverage, and which of those it did.

### 3. Report the state plainly

- **Went live** — say voting is open once committed and deployed, and give the deadline.
- **Still hidden** — name the empty slots and say the set stays invisible until a re-run with a
  fuller gallery. This is the normal mid-spoiler outcome, not a failure.
- **Window untouched** — say when voting opens or opened, so it's clear nothing was rescheduled.

Never reschedule a window that already exists unless the user asked. Players may be voting in it.

### 4. Sanity checks

- **Overlap**: if this contest's `previewsOpen` falls before the previous contest's `scoringDate`
  (which also marks when that contest loses the front page — no separate reveal-end field), warn
  that the previous contest loses the front page early. It stays reachable at `/p0p1/<prev>`.
- **Finalize ordering**: if the previous contest's `p0p1-ratings-<prev>.ts` exists and its `phase`
  is not `"final"`, warn that it never reached final results.
- **Results coverage**: `scoringDate` defaults to `release + 28d`, so results always cover a full
  four weeks of Arena play regardless of the voting deadline. Only a hand-picked `--results` can
  shorten that — flag it if the resolved `scoringDate` is less than `release + 28d`, and note that
  doing so also shortens how long the contest stays featured, since the two are the same field.
- **Ratings join**: if `p0p1-ratings-<code>.ts` already exists, compare pool names normalized via
  `name.split(" // ")[0].trim()` against the ratings names and report mismatches both ways.

### 5. Type check

`cd frontend && node_modules/.bin/tsc -b`

### 6. Hand off, do not commit

Show `git diff --stat`, tell the user to review at `npm run dev`, and let them commit and push.
Never run `git commit` or `git push`.

## Notes

- The card pool is a globbed fixture; the window is a key in the root `p0p1_contests.json`, the same
  shared-config pattern as `scoring_buckets.json`. There is no route to add.
- `write_contest` rebuilds each contest's entry from scratch on every call, so any per-contest field
  beyond the window (like `hybridCommonSlots`) must be threaded through and written explicitly there
  or it silently disappears on the next reschedule. This is the pattern for any future conditional
  field: the script owns it, hand edits don't survive a re-run.
- Windows live outside the database, so a contest resolves before its set reaches `public_sets`, and
  a deadline change is a one-line JSON edit with no migration and no query.
- `/p0p1/<code>` is the historic viewer for any contest and carries no pointer to a later set.
  Before its `previewsOpen`, that URL 404s in production and renders in dev, which is how a partial
  pool gets previewed safely.
- `p0p1-phase` is the separate skill for the results side, producing `p0p1-ratings-<code>.ts` weeks
  later (midway, then final).
