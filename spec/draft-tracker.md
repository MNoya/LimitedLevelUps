# Personal Draft Tracker: handoff

A private tracker on the player profile `/player/<slug>` replacing the `Tracker` Google Sheet. Owner-gated, experimental, one user.

The build is done. **What is left is UI polish**, plus two features listed at the bottom. Everything already shipped is summarised only far enough to orient a fresh session; do not redo it.

## Start here

Paste this, or just point a session at this file.

> Read `spec/draft-tracker.md`. Bring the local stack up, confirm `/player/noya` renders the owner's tracker, then look at the open lists and ask me which item to take. Do not start changing things before we agree on what.

What the session should do, in order:

1. **Bring it up and look at it.** Postgres, proxy, dev server. Load the page for both HOB and MSH, expand a draft, open the collection. Half the items below only make sense once seen.
2. **Read "Reuse these, do not rebuild them" before writing any UI.** Every bespoke thing this tracker grew was something the site already had.
3. **Ask which item to take.** The polish list is roughly ordered but not prioritised, and the user has more items not yet written down. Start by asking whether anything new should be added to the list.
4. **For anything visual, propose before applying.** Two to four concrete options, described or mocked, then wait. The user iterates on look and wants the choice. This holds for layout, density and copy alike.
5. **Append, do not rewrite.** New dislikes go on the polish list. Settled decisions stay settled unless the user reopens them.
6. **Close by updating this file.** Move finished items out, add whatever new ones came up. The doc should always describe what is left, never what was done.

Useful to know: the tracker is one page file, so most polish is a contained edit. The user reviews every diff, never wants a push, and expects a live URL on the LAN IP at the end of a change rather than a command to run.

## Running it locally

```bash
docker start dischord-pg
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord python -m bot.scripts.local_supabase_proxy
cd frontend && npm run dev -- --host --port 5180 --strictPort
```

`frontend/.env.local` needs `VITE_DATA_MODE=local` and `VITE_DEV_DISCORD_ID` (the proxy has no auth, so that env var is the only way to reach an owner-gated page locally).

## What exists

| | |
|---|---|
| Page | `frontend/src/pages/PlayerTrackerPage.tsx`, one file, iterate freely |
| Gate | `data/trackerUsers.ts`, Discord id allowlist |
| Data | `data/trackerApi.ts` reads `public_player_draft_events` and the `tracker_*` tables |
| Tables | `tracker_draft_notes`, `tracker_match_notes`, `tracker_collection`, `tracker_set_economy`, all RLS on `auth.uid()` |
| Objective 17lands data | `draft_events.pool_rares`, `pool_mythics`, `deck_cards`, `match_results` |
| Refresh | `POST /tracker/refresh?set_code=X[&force=1]` on the local proxy: ingests new drafts through `refresh_player`, then fills deck and match detail server-side |
| Import | `bot/scripts/import_tracker_sheet.py --set MSH --user <uuid> [--apply]` |

Desktop is a split: collection left (520px), draft log right. Mobile swaps to two tabs.

## Settled decisions, do not relitigate

- **Only the main Arena account.** Account tabs come from `public_my_player_accounts`, a view scoped by `auth.jwt()` so it can only ever return the caller's own accounts. Arena account names are exposed nowhere else.
- **Pod drafts are excluded** from the tracker entirely.
- **17lands routes**: use `/api/deck/draft/` and `/data/details/`. `/data/deck` is `get_dummy_deck_data` and returns a fixed sample. Neither sends CORS headers, so the fetch runs on the proxy, not in the browser.
- **Prize tables** in `data/prizes.ts` were reconstructed from four set tabs of the spreadsheet. They are observed payouts, not estimates.
- **Completion projections** in `data/collectionProjection.ts` are the sheet's formulas verbatim, checked against its own MSH output (mythic 96.3% vs 96.3%, rare 103.8% vs 103.9%).
- Manual values override fetched ones for rares and mythics, and for match result and opponent colours.
- **The draft log is a cell grid.** Every column in the header and each row is a `Cell`, owning its own padding and right divider; `GRID_CLS` drops the divider on the last one. Content that needs alignment uses `justify-end` or `justify-center`, not `text-right`, since a cell is a flex box.
- **The 17lands link is the whole `#` cell**, not the digits. The anchor fills the cell so any part of it opens the draft. This keeps the deck name renameable in place and adds no glyph to the row. There is no button in the expanded panel and no `↗`. A draft without an `external_url` renders the number as plain text.
- **A match is one line**: number, result buttons, opponent colours, then the note filling the rest. The per-game play/draw string is gone.
- **Notes are click to edit.** A note renders as borderless text exactly as tall as its content, an empty one as a `+ note` affordance, and the editor autosizes to what is typed. No placeholder copy. `NoteField` is the one component behind both the draft note and every match note.

## Reuse these, do not rebuild them

This session repeatedly invented things that already existed. Before writing any UI:

- `components/SetCodeDropdown.tsx`, the set picker used elsewhere on the site.
- `components/Brand.tsx` → `SetGlyph`, set symbol.
- `components/TierGrid.tsx` → `PreviewShell`, `previewAnchorFor`, `PREVIEW_W`, the shared hover-preview chrome.
- `components/pod/review/ReviewCard.tsx` → `useFallbackImage`.
- `data/cardImages.ts` → `useCardImageMap`, `cardImageSources`, batched art through our own edge-cached endpoint.
- `components/ManaPips.tsx` → `Pips`.
- `components/LeaderboardTable.tsx` → `SortKey`, `SortDir`, `SortState`, and its column-header sort behaviour.
- Row idiom: CSS grid with a fixed `gridTemplateColumns`, `bg-surface` rows, `border-b border-border`, display font only for column headers at `text-[11px] tracking-[0.2em]`.

## Open: UI polish

Ordered roughly by how much they grate. Iterate with the user; none of these is settled.

1. **Muted gray on black is a bad style.** Nothing needs dimming. Everything can be a normal or subtle colour. `dim` (`#4a5163`) in particular reads as almost invisible on the tracker's background. This wants a pass across the whole page, not one element at a time.
2. **The set dropdown is in the wrong place.** Move it from top-right to the left, give it the set icon, and use `SetCodeDropdown` instead of the bare `<select>`.
3. **The summary numbers are too big**, meaning trophies, gems, packs and the rest. The collection block was already compacted into bars; the draft-log strip still uses tall tiles and should get the same treatment.
4. **Use existing site styles wherever possible.** Recurring theme: the tracker keeps drifting into bespoke chrome.
5. **The note column in the collapsed row truncates mid-word**, e.g. `Rare lands, Thanos (cut), Migthy Thor, Cloa…`. Raised by a session, not yet confirmed as a dislike.
6. **The set `<select>` offers all 41 sets**, including sets with no tracker data at all. Worth scoping to sets with drafts when item 2 replaces it with `SetCodeDropdown`. Raised by a session, not yet confirmed.

The user has more of these and wants to iterate over a later session until happy. Treat this list as append-only.

## Open: features

**Maindeck versus sideboard preview.** `deck_cards` already holds `{maindeck: [{name, rarity}], sideboard: [...]}` for every fetched draft, and nothing in the UI reads it. Hovering the rares and mythics counts should open a small panel showing those cards as images at small size, split into played and not played. `useCardImageMap` resolves the art; `PreviewShell` gives the panel its chrome.

**Column sorting on the draft log.** Default to date descending, numbered 1..N. Clicking any column header sorts by it, using the same sort system as the leaderboard (`SortState` and the header behaviour in `LeaderboardTable.tsx`) rather than a new one.

## Known gaps

- **MSH has no fetched 17lands detail**: 0 of 31 drafts have `deck_cards` or `match_results`. Its rares and mythics are the hand-typed values imported from the sheet. Press the fetch button on MSH to backfill, roughly a minute.
- **The mobile log renders five cells into four columns.** `LOG_COLS_MOBILE` declares four tracks, but the header and each row both emit five children, so the last one wraps to a second grid line. Header and row wrap identically, so they stay aligned, but every entry costs two lines. Pre-existing, and the cell dividers make it plain to see. Needs a look on a real phone before picking a fix.
- **`match_results[].games` is fetched but shown nowhere.** It carries the per-game result and who was on the play. It used to render as `Ld Wp Ld`, which read as nonsense, so it was removed. The data is still on `draft_events` if it is ever worth showing legibly.
- **Collection is manual.** untapped.gg is out, it does not run on Linux. Counts are click to add, right click to remove.
- **Prod has no refresh path.** The fetch endpoint lives on the dev proxy only. A deployed tracker needs either a bot HTTP endpoint or a Pages Function with database write access.
- **One migration is unpushed**: `tr4ck3r0001`, which carries the whole tracker schema. It was squashed from the seven this session produced and verified by building a database from scratch and diffing it against the incremental result.
- **One unexplained observation**: `pool_rares` was populated on HOB before the first refresh call ran, and the cause was never identified. Values were later recomputed with `force=1` and reconcile with hand checks.
