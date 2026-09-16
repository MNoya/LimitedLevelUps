# P0P1 12-slot ballot

Status: shipped (commit `a53e37fe`, 2026-09-16). Live for FRA once its `comingSoon` flag is dropped at launch.

Starting with FRA, the P0P1 ballot is 12 slots instead of 8. This is a per-contest change: HOB, MSH and every earlier contest keep the 8-slot layout and their frozen results; FRA and every later contest use the 12.

## The ballot

Twelve slots, in this order (each color's common then uncommon, then the two spanning slots):

| # | slot key | label | filter |
| --- | --- | --- | --- |
| 1 | `white_common` | White Common | mono-color **or hybrid-of-color** common |
| 2 | `white_uncommon` | White Uncommon | mono-color **or hybrid-of-color** uncommon |
| 3-10 | `blue_*` … `green_*` | Blue/Black/Red/Green Common then Uncommon | same, per color |
| 11 | `multicolor_uncommon` | Gold Uncommon | any 2+ color uncommon |
| 12 | `best_card` | Best Card | any rare or mythic |

The WWUUBBRRGG order keeps a color's two slots adjacent, which reads well in the one-row ballot and carries through the breakdowns and results.

Hybrids count for their color in both the common and uncommon rows, so the old `hybridCommonSlots` toggle is gone. A two-color gold (non-hybrid) uncommon lands in Gold; a hybrid uncommon is eligible for each of its colors' slots and, carrying 2+ colors, also for Gold — ballot-level uniqueness stops it filling more than one. The Gold slot keeps the key `multicolor_uncommon`; only its label changed.

Best Card is any rare or mythic, matching the community poll in `bot/commands/p0p1_poll.py`. Its GIHWR feeds the ranked total like every other pick and is usually the highest single contribution.

## Per-contest layout version

`ContestConfig` carries `layout?: number` (default 1; the JSON import widens the literal to `number`). `buildSlots(config)` returns the v1 8-slot set for `layout` below 2 and the v2 12-slot set for 2 and up. `slotsForSet(setCode)` resolves a set code to its slot list, the per-contest replacement for the retired module-level `SLOTS` constant. FRA is `layout: 2`; earlier contests are 1.

`SlotKey` is the superset of both layouts: the five uncommon keys and `best_card`, plus `wildcard_common` and `wildcard_uncommon` which only v1 renders. Every UI site that iterated the global `SLOTS` now iterates the contest's own slots (threaded from `useP0P1Ballot`'s `contestSlots` or from `slotsForSet`).

No database migration: `p0p1_entries.slot` is free text with no CHECK or enum, and the `public_p0p1_*` views aggregate by slot generically. Old ballots keep their old keys and only ever render on their old (v1) contest pages.

## Backend

- `bot/scripts/fetch_p0p1_cards.py`: the Scryfall query drops the rarity filter so rares and mythics come through. `report_pool_coverage` reports per-color common and uncommon counts (mono + hybrid) plus a rare/mythic count, and flags a shortfall when any of the twelve slot classes is empty. `hybridCommonSlots` is replaced by `layout`, written as 2 on a new contest.
- `bot/scripts/p0p1_voters.py`: the full-ballot size is read per-contest from `p0p1_contests.json` (8 or 12) so the incomplete-ballot flag counts against the right total.
- `bot/tests/test_p0p1_contest.py`: tests `resolve_layout` in place of the old hybrid-default cases. No test pins the slot list; the coverage report and the live ballot are the check.

## Frontend

### Core

- `types/p0p1.ts`: `Card.rarity` gains `"mythic"`; `SlotKey` is the superset above; `ContestConfig` swaps `hybridCommonSlots` for `layout`.
- `p0p1Slots.ts`: `monoOrHybridColor` takes the rarity it gates on; `buildSlots` branches on `layout`; `slotsForSet` is exported; the `SLOTS` constant is gone.
- `slotVisuals.tsx`: `SLOT_ACCENT`, `MONO` and `SlotPip` carry every key. Best Card gets a rare/mythic (gold) glyph; the color uncommon slots reuse their color pip.
- `CardSelectionGrid`: the color-filter chip row shows on the color-spanning slots — `wildcard_common`, `wildcard_uncommon` and `best_card`. The color-locked slots and Gold do not show it.

### Ballot UI

- **Desktop default is one compact row of twelve**: art-only tiles (color bar + set/rarity pip, category label under the pip on empty tiles), so nothing truncates at laptop widths and the card picker below keeps full height. Picked tiles show the art.
- An **EXPAND** chevron under the PICKS bar toggles to a **two-row, six-wide** layout with full tiles (category label, card name, mana cost). The desktop/mobile split is at 1024px.
- The collapsed strip is **sticky under the hero**. An `IntersectionObserver` gives it more bottom padding at rest and keeps it compact once pinned. The expanded view is not sticky (a pinned two-row bar covers too much).
- **Mobile is three rows of four** (`grid-cols-4`).
- Pool art crops **preload in the background** when the pool loads, so a pick paints instantly instead of flashing a blank frame.

### Dev / mock

`mockApi.ts` no longer seeds the viewer's own ballot with synthetic picks (removed `buildSyntheticPicks` and the `P0P1_SLOT_KEYS` array), so the voting ballot starts empty and fills one slot at a time. Synthetic pick-stats, ratings and crowd ballots for the results phases are unchanged; dev result presets still fill "your picks" from the top pick per slot.

## Scoring: no logic change

`scoreBallot`, `bestPossibleTeam`, `mostPopularTeam` and `highlightsFeed` iterate `slots` generically and handle twelve without change. The greedy assignment stays near-optimal: identical-filter slots resolve to distinct top cards. Stale wildcard-era comments in `p0p1Results.ts` were updated.

## Launch checklist (FRA, 2026-09-18)

- Re-run `/p0p1 FRA` to regenerate `cards-fra.ts` from the fuller spoiled pool.
- Remove `"comingSoon": true` from FRA in `p0p1_contests.json`. Voting then opens on its own at `previewsOpen` (noon ET Friday); the date gate handles timing, `comingSoon` is the "not yet" banner that overrides it until dropped.

## Results timing

Results land four weeks after **voting closes**, not four weeks after release. FRA's `scoringDate` (2026-10-21) is its `votingDeadline` (2026-09-23) plus 28 days, which is the intended window.
