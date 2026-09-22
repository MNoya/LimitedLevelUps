---
name: tier-list
description: Add or refresh a set's tier list and archetype skeletons on the DischordLeaderboard site. Takes a set code plus the reviewers' 17lands tier_list URLs and up to ten sealeddeck archetype pool URLs. Edits frontend/src/data/constants.ts and skeletons.ts, bakes each pool's cards with cmc from Scryfall, and typechecks. Never commits.
---

# tier-list

Wire up a Magic set's tier list (Alex + Marc grades) and archetype skeletons on the site. Run it during spoiler season when the reviewers publish their 17lands grades and the sealeddeck archetype pools go up. Safe to re-run: adding a consensus list later, or replacing pool URLs, just edits the same entries.

This is a frontend-only change. The set itself is added to the rotation by the separate `add-set` skill; this skill assumes `bot/sets.py` already carries the set (it reads the name and start date from there).

## Arguments

A set code in `$ARGUMENTS`, e.g. `FRA`. If no code is given, ask for it and stop.

The reviewer URLs and pool URLs usually come in the same message. If any are missing, ask for them before editing:

- **Reviewer grades** (one 17lands `tier_list` share URL per reviewer): `https://www.17lands.com/tier_list/<uid>`
- **Archetype pools** (one sealeddeck URL per color pair): `https://sealeddeck.tech/sets/<set>/<poolId>` labeled by color, e.g. `UW: https://sealeddeck.tech/sets/fra/bWzk9SpyZv`
- **Consensus list** (optional): a single 17lands `tier_list` uid that drives grid placement. With none, the first reviewer's list stands in and the page runs in comparison mode.

## Workflow

### 1. Validate

- Uppercase `$ARGUMENTS`, must match `^[A-Z]{3,4}$`.
- Read `bot/sets.py`. Find the `SetSeed("<CODE>", "<Name>", date(...start...), ...)`. Note the official name and the start date. Abort if the set is not in `ALL_SETS` (run `add-set` first).

### 2. Tier-list entries in `frontend/src/data/constants.ts`

- `TIER_LIST_GRADERS`: prepend a `<CODE>: [...]` block at the top of the object (map is newest-first). One `{ name, uid }` per reviewer, `uid` is the id from each `tier_list/<uid>` URL. The two reviewers are `Alex` and `Marc`.
- `TIER_LIST_PREVIEW_SETS`: if the set is not yet live in the DB feed (its Arena start date is in the future, so `/leaderboard` does not list it), add `<CODE>: { name: "<Name>", startDate: "<YYYY-MM-DD>" }` using the name and Arena start date from `bot/sets.py`. A future `startDate` renders a PREVIEW badge. Remove this entry once the set goes live (optional cleanup; a live set overrides the preview).
- `TIER_LIST_UIDS`: only if a consensus list was given, add `<CODE>: "<uid>"`.

### 3. Bake the archetype skeletons

Write the pool lines to a temp file, one `COLORS: URL` per line, then run the baker with the repo venv:

```bash
.venv/bin/python .claude/skills/tier-list/assets/bake_skeletons.py <CODE> < /tmp/<code>_pools.txt
```

It fetches each `sealeddeck.tech/api/pools/<poolId>?columns=true`, flattens `deck.columns` into `cards` and `deck.splitColumns` into `splitCards`, resolves each card's mana value from the Scryfall collection API, normalizes color codes to WUBRG order, and prints a `<CODE>: [ ... ],` block. Any card Scryfall cannot find prints `NOT FOUND` to stderr; resolve it by hand before inserting.

Paste the printed block at the top of `SKELETON_SEEDS` in `frontend/src/data/skeletons.ts` (newest-first, above the current top set).

### 4. Typecheck and hand off

- `cd frontend && npx tsc -b` must pass.
- Start the dev server if it is not already running (prod data mode shows the live sets), bound with `--host`.
- Close with a `**Check on the site:**` line: the LAN URL at `/tier-list/<CODE>` (first address from `hostname -I`, never localhost), noting the reviewer toggle and the ARCHETYPES button.

Do not commit. The user reviews the diff and commits.

## Notes

- The site discovers a set for the tier-list dropdown only if it is live in the DB feed **or** listed in `TIER_LIST_PREVIEW_SETS`, and `hasTierList` is true for it (has graders or a consensus uid). A pre-release set needs the preview entry.
- The skeleton layout re-buckets cards by cmc, so the row order inside a block does not affect display; correct cmc values do.
- Double-faced names keep the full `Front // Back` string; cmc comes from the front face.
