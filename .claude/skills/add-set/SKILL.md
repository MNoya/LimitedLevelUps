---
name: add-set
description: Add a Magic set to the DischordLeaderboard rotation. Takes a 3-4 letter set code (e.g. SOS). Looks up the official name and Arena release date, decides whether the set is the new active (rotate) or a historical backfill (insert chronologically), updates bot/sets.py, runs seed + refresh against the local DATABASE_URL, and creates a commit. User pushes manually.
---

# add-set

Add a Magic set to the leaderboard. Handles both **new** sets (rotate the active set) and **old** sets (backfill an earlier set into the tracked history).

## Argument

A 3- or 4-letter MTG Arena set code in `$ARGUMENTS`, e.g. `SOS`.

If no argument is given, ask the user for the code and stop.

## Workflow

### 1. Validate

- Strip whitespace and uppercase `$ARGUMENTS`. Must match `^[A-Z]{3,4}$`. Otherwise abort.
- Read `bot/sets.py`. If the code already appears in `ALL_SETS`, abort with `set <CODE> already exists in bot/sets.py`. Do not proceed.

### 2. Look up name and Arena dates

WebSearch for the set's official name and **MTG Arena** release date (not tabletop). Prefer these sources:

- magic.wizards.com
- mtg.fandom.com (MTG Wiki)
- mtga.untapped.gg
- draftsim.com
- cardgamebase.com

For a historical backfill you also need the **end date** (the day before the successor set's Arena release). Look it up the same way.

If the search yields a confident, single answer for everything you need, use it. Otherwise stop and ask the user for:

- Set name (full official, e.g. `Secrets of Strixhaven`)
- MTG Arena release date (`YYYY-MM-DD`)
- End date (`YYYY-MM-DD`) — only for backfill (old set); for a new set you set an *anticipated* end date yourself (see Mode NEW below)

### 3. Decide mode: NEW vs OLD

There is **no `ACTIVE_SET_CODE` constant in `bot/sets.py`** — the active set is derived from today's date by `active_set_code()`, and the current newest set is simply the last entry in `ALL_SETS`. Compare the release date to that newest entry's `start_date`:

- **release date > newest start_date** → **NEW** (rotate)
- **release date <= newest start_date** → **OLD** (backfill)

### 4. Edit `bot/sets.py`

Preserve the column-aligned formatting of surrounding rows in `ALL_SETS` (visually align the constructor arguments).

#### Mode NEW (rotate)

Rotation is automatic: `active_set_code()` flips to whichever released set holds today's date, so there is no flag to set — the dates do the work. Every set (except the permanent `CUBE`) must carry an `end_date`; `active_set_code()` skips `None`-ended seeds when matching the active window, so a normal set left open-ended would not rotate in cleanly.

1. Locate the current newest entry in `ALL_SETS` (the last one). Change its `end_date` to `(new release date - 1 day)` — it currently holds an *anticipated* rotation date that the real successor now replaces.
2. Append a new `SetSeed(...)` row immediately after it. Give it an **anticipated** `end_date` (never `None`): the next set's announced Arena release minus a day if known, otherwise roughly 7 weeks after this release. This keeps the new set inside an active window until its own successor arrives.
3. Bump the frontend fallback `ACTIVE_SET_CODE` in `frontend/src/data/constants.ts` to the new code. This is only a fallback for when the live set feed hasn't loaded — the site reads the real active set from the network — but keep it current.

#### Mode OLD (backfill)

1. Insert the new `SetSeed(...)` row at the chronologically correct position in `ALL_SETS`, sorted by `start_date`. Use the provided `end_date` (do NOT use `None`).
2. Do **not** touch the newest set or the frontend `ACTIVE_SET_CODE` fallback — a backfill never changes what is active.
3. Do **not** adjust any other row's `end_date` — existing dates are already correct for sets surrounding a backfilled entry.
4. If the user reports the set was tracked in 17lands under a non-matching expansion code, also pass `expansion_matches=("<17lands expansion string>",)`. Otherwise omit it.

### 4b. Generate the set symbol

Run:

```
python -m bot.scripts.generate_set_symbols <CODE>
```

This pulls the keyrune glyph, recolors it white (preserving the glyph's aspect ratio via `squarify`), and writes `frontend/public/set-symbols/<code>.png` (served on the site and used as the Discord-unfurl thumbnail for the set's routes). Requires `inkscape` and `pngquant` on PATH. A code keyrune lacks a glyph for borrows another set's via `KEYRUNE_ALIAS` (e.g. `SIR` → Shadows over Innistrad Remastered).

If the script reports `no keyrune glyph, skipped: <CODE>` — keyrune has no symbol for that code (e.g. `CUBE`, or a brand-new set keyrune hasn't published yet) — there is simply no symbol and the leaderboard falls back to the LLU logo. Tell the user; do **not** treat it as an error or block the commit.

**Then upload the glyph as a Discord application emoji** named by the **lowercase code** (`sos`, `war`, `mh1` …):

```
python -m bot.scripts.upload_app_emojis keyrune:<code>
```

It uploads to the application `DISCORD_BOT_TOKEN` belongs to, so the test and prod apps each need one run. The script also takes `mana:<glyph>[:<name>]` specs for Mana-font icons and `--force` to replace an existing name. `/event-scribe` and the set embeds resolve the symbol by emoji name at startup, so a set whose emoji isn't uploaded renders without its glyph.

### 4c. Add the Collector Booster Arena Direct window

Collector Booster Arena Direct Sealed pays **one box per trophy** instead of the play direct's two, so `boxes_for_event` needs the event's date range recorded. Run:

```
python -m bot.scripts.find_collector_window <CODE>
```

It resolves the range from the MTG Scribe calendar and prints paste-ready rows.

- If it prints a window, add the `CollectorBoosterWindow(...)` row to `COLLECTOR_BOOSTER_WINDOWS` in `bot/sets.py` and the matching `{ setCode, startDate, endDate }` row to the `COLLECTOR_BOOSTER_WINDOWS` mirror in `frontend/src/data/scoring.ts`. Keep both lists ordered by date (append for a new set). These two lists reimplement the same rule and must stay in sync.
- If it prints `no Collector Booster Arena Direct found ... yet`, Scribe hasn't scheduled it. Skip this step and tell the user to re-run `find_collector_window <CODE>` once the Arena Direct appears (usually partway into the set's cycle), then add the rows.

### 5. Show diff

Run `git diff bot/sets.py frontend/src/data/scoring.ts` and display it to the user.

### 6. Run scripts against the local DATABASE_URL

Sanity-check `DATABASE_URL`:

- Run `echo "$DATABASE_URL"`. Confirm it is set.
- If it points at `localhost` or `127.0.0.1`, warn the user that the changes will only land in their local Postgres and ask whether to proceed anyway (they may be testing).

Then run, in order:

```
python -m bot.scripts.seed_sets
python -m bot.scripts.refresh_stats
```

`seed_sets` registers the new set and **claims any orphan `draft_events`** whose expansion already matches it (rebuilds `player_stats` and scores for those players). For OLD-mode backfills this is usually enough on its own. `refresh_stats` then fetches any drafts 17lands has that we haven't ingested yet. If either script fails, stop. Do not commit. Report the error verbatim and let the user fix it.

### 7. Commit (do not push)

After both scripts succeed:

```
git add bot/sets.py frontend/public/set-symbols/<code>.png
git commit -m "<subject>"
```

Omit the PNG from `git add` if no glyph was generated (the `skipped` case above). Also `git add frontend/src/data/scoring.ts` if a collector window row was added in step 4c, and `frontend/src/data/constants.ts` if you bumped the `ACTIVE_SET_CODE` fallback (Mode NEW).

Subject lines (must start with uppercase — memory: `feedback_commit_subject_uppercase.md`):

- Mode NEW, no end_date adjustment on the previous active → `Add <NEW CODE> set`
- Mode NEW, previous active end_date adjusted → `Add <NEW CODE> set and close <PREV CODE>`
- Mode OLD (backfill) → `Backfill <CODE> set`

### 8. Report

Tell the user:

- The new commit's short SHA and subject.
- Mode used (rotate vs backfill).
- `Push when ready: git push` — Railway redeploys on master push. For NEW mode the leaderboard rotates on its own once the new set's `start_date` arrives (date-derived by `active_set_code()`); for OLD mode the new row just becomes available for stats lookups.

Never push automatically.

## Notes

- Dates are MTG Arena release dates, not tabletop release dates.
- Set name is the full official name (e.g. `Secrets of Strixhaven`, not `Strixhaven`).
- The seed script is idempotent and updates `name` / `end_date` on existing rows, so re-running is safe if anything went sideways.
- If `DATABASE_URL` is unset, ask the user for it rather than guessing.
