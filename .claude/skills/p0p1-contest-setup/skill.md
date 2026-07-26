---
name: p0p1-contest-setup
description: Set up a new P0P1 contest for an upcoming set — generates the card fixture from Scryfall, registers the contest in the frontend, and runs sanity checks. Never commits.
---

# p0p1-contest-setup

Registers a new P0P1 contest for an upcoming Magic set. Generates the card pool fixture
from Scryfall and adds the contest entry to the frontend registry.

## Argument

`$ARGUMENTS` should be a set code (e.g. `HOB`) and optionally a previews-open date
(`--previews YYYY-MM-DD`). If no set code is given, ask the user and stop.

## Workflow

### 1. Validate the set

- Confirm the set code exists in `bot/sets.py` (`ALL_SETS`). Print name + release date.
- Confirm the set code is NOT already in `P0P1_CONTESTS` in
  `frontend/src/data/p0p1Slots.ts`. If it is, tell the user it's already registered and stop.

### 2. Generate the card fixture

Run:

```
.venv/bin/python -m bot.scripts.fetch_p0p1_cards --set-code <CODE>
```

This writes `frontend/src/data/fixtures/cards-<code_lower>.ts`. Print the card count
and any skipped layouts.

### 3. Register the contest

Add an entry to `P0P1_CONTESTS` in `frontend/src/data/p0p1Slots.ts`:

```ts
  <CODE>: { previewsOpen: "<date>" },
```

The `previewsOpen` date comes from `--previews` or, if omitted, ask the user. This is
typically the date official card previews begin (usually ~2 weeks before Arena release).

If the voting deadline should differ from the default (noon ET on release day), add
`votingDeadline: "<ISO timestamp>"` — but only if the user specifies one.

### 4. Overlap checks

- If `previewsOpen` falls before the previous contest's `revealEnd` (release + 28 days),
  warn: "Voting windows overlap — the newer contest's voting window will take priority
  per Decision 3, but the older contest's reveal phase will be interrupted."
- If the previous contest's ratings fixture (`frontend/src/data/fixtures/p0p1-ratings-<prev>.ts`)
  exists and its `phase` is not `"final"`, warn: "The outgoing contest hasn't reached
  final results yet."

### 5. Card-name join check

If a ratings fixture exists for this set (unlikely for a new contest, but possible if
ratings were generated before cards), compare:
- Card names in the card fixture (normalized via `name.split(" // ")[0].trim()`)
- Card names in the ratings fixture

Report any mismatches (cards in pool but not in ratings, or vice versa).

### 6. Type check

Run `cd frontend && npx tsc --noEmit` to verify the new fixture compiles.

### 7. Hand off — do not commit

Show `git diff --stat` and tell the user to review with `npm run dev`, then commit
and push themselves. Never run `git commit` or `git push`.

## Notes

- The card fixture uses `export default [...] satisfies Card[]` with the Card type
  imported from `../../types/p0p1`.
- `fetch_p0p1_cards.py` handles all Scryfall layouts (normal, adventure, saga,
  transform, modal_dfc, split, prepare, class, case, etc.).
- The contest entry alone is enough — the featured-contest resolver picks it up
  automatically based on dates. No other files need editing.
