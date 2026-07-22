---
name: p0p1-phase
description: Flip the P0P1 results reveal phase (midway/final/none) by regenerating the ratings fixture from 17lands, or refresh the current phase's data without changing it. Runs sanity checks on the new fixture and hands off for the user to review and commit — never commits or pushes itself.
---

# p0p1-phase

Flips or refreshes the P0P1 contest's results reveal. The reveal depends on two things:
the `phase` field in `frontend/src/data/fixtures/p0p1-ratings-<set>.json` and the clock
(`P0P1_SCORING_DATE` in `p0p1Slots.ts`). A `"final"` fixture merged before the scoring date
is suppressed until the date arrives, so the branch can ship ahead of the reveal.

Expected lifecycle: `voting` → `postVoting` → `midway` → `final`.

## Argument

One of `midway`, `final`, `none`, `refresh` in `$ARGUMENTS`.

If no argument is given, ask the user which one and stop.

## Workflow

### 1. Read current state

- `frontend/src/data/p0p1Slots.ts`: `P0P1_SET_CODE`, `P0P1_VOTING_DEADLINE`,
  `P0P1_SCORING_DATE` (= voting deadline + 28 days).
- `bot/sets.py`: the matching `SetSeed`'s `start_date` (the set's Arena release date — this
  is also the 17lands query window's start).
- `frontend/src/data/fixtures/p0p1-ratings-<set_code_lower>.json`: current `phase`,
  `dateRange`, and `cards.length`.

Print a short summary: set code, current fixture phase, current `dateRange`, current card
count, today's date, voting deadline, scoring date.

### 2. State-machine reference

The site phase is derived from the fixture `phase` + clock in `deriveP0P1Phase`
(`useP0P1Ballot.ts`):

| Fixture `phase`            | Clock                              | Site phase     |
| -------------------------- | ---------------------------------- | -------------- |
| any                        | before voting deadline             | `voting`       |
| `null`                     | past deadline, before scoring date | `postVoting`   |
| `"midway"`                 | past deadline, before scoring date | `midway`       |
| `"final"`                  | past deadline, before scoring date | `postVoting`   |
| `null` or stale `"midway"` | past scoring date                  | `finalizing`   |
| `"final"`                  | past scoring date                  | `final`        |

`phase: null` is the kill switch — regresses to `postVoting` or `finalizing` depending on
the clock.

### 3. `none` — kill switch

Edit the fixture's `"phase"` field to `null` in place. Do not refetch from 17lands, do not
touch `dateRange` or `cards`. Skip to step 5.

### 4. `midway` / `final` / `refresh` — fetch

Resolve the target phase and end date:

- `midway` → phase `midway`, end date = today.
- `final` → phase `final`, end date = `P0P1_SCORING_DATE` (`YYYY-MM-DD`).
- `refresh` → keep the fixture's current phase, end date = today. If the current phase is
  `null`, abort — there's nothing to refresh; tell the user to pass `midway` or `final`
  instead.

Run:

```
.venv/bin/python -m bot.scripts.fetch_p0p1_ratings --set-code <CODE> --phase <phase> --end-date <end date>
```

This overwrites `frontend/src/data/fixtures/p0p1-ratings-<code>.json` with a fresh 17lands
pull. The pull itself uses `time_period=ALL_TIME` (the script's default — always correct here
since the set's Arena release is the natural start of "all time" for a fresh set); `--end-date`
only feeds the fixture's display `dateRange`, not the query.

### 5. Sanity checks (abort on any failure, do not proceed to step 6)

- The fixture is valid JSON.
- `setCode` matches `P0P1_SET_CODE`.
- `phase` equals the target phase from step 4 (or is `null` for the `none` path).
- `dateRange.start` equals the set's Arena release date from `bot/sets.py`.
- `cards.length` is within ~10% of the previous card count recorded in step 1 (skip this
  check for `none`, which doesn't refetch).
- A healthy share of cards (rough eyeball, not a hard threshold) have `gih >= 500`
  (`GIH_SAMPLE_FLOOR` in `frontend/src/data/p0p1Results.ts`) — enough of the set has been
  drafted for ratings to mean something.

If anything fails, report exactly what and stop. Do not hand off a broken fixture.

### 6. Hand off — do not commit

Show `git diff --stat` for the fixture and the diff of just the header fields (`setCode`,
`phase`, `dateRange`, `cards.length` before/after — not the full card array).

Tell the user to verify with `npm run dev` (dev presets in the P0P1 dev panel can preview
each phase without waiting on the real clock) and commit/push themselves when satisfied.
Never run `git commit` or `git push` as part of this skill.

## Notes

- `fetch_p0p1_ratings` takes `--set-code` (not `--set`), `--phase midway|final`,
  `--end-date YYYY-MM-DD` (defaults to today if omitted — always pass it explicitly here), and
  `--time-period ALL_TIME|LAST_TWO_WEEKS` (defaults to `ALL_TIME`; leave it alone here).
- `dateRange` is display-only — it drives the "ratings from X to Y" intro copy, not the 17lands
  query (17lands takes a `time_period` enum now, not a date range). The sanity check on
  `dateRange.start` still catches a wrong `--set-code`, since it's still derived from
  `bot/sets.py`.
- The script is a straight overwrite; there's no need to delete the old fixture first.
- If `DATABASE_URL`-dependent steps aren't involved here — this skill never touches the
  database, only the static fixture JSON and a public, unauthenticated 17lands endpoint.
