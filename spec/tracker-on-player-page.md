# Tracker on the player page

The tracker is not its own screen. It is the player profile with extra parts switched on when the viewer is the owner, on both widths. `/player/:slug/tracker` and `PlayerTrackerPage.tsx` are gone.

`spec/draft-tracker.md` describes the standalone page it grew out of and is stale for everything except the formulas and the known gaps. Read it for background only.

## The gate

```ts
const trackerMode = useOwnTrackerProfile(profile.slug);   // PlayerPage.tsx
```

Requires **both** `isTrackerUser(user?.discordId)` (a Discord id allowlist in `data/trackerUsers.ts`) **and** `ownSlug === profile.slug`, so the tracker never appears on someone else's profile. `Desktop()` and `Mobile()` each call it once and everything else keys off that one boolean.

## Desktop composition, inside `Desktop()`

| Slot | Public | Tracker owner |
|---|---|---|
| Header, right of the name | stat strip | `TrackerStatsBlock` then the stat strip, both in the `ml-auto` group |
| Left column header | nothing | tab row: `BREAKDOWN` / `COLLECTION`, then `AccountTabs` and `RefreshButton` pushed right |
| Left column body | `BreakdownPanel` | `BreakdownPanel bordered={false}` or `Collection narrow`, by tab |
| Right column | `DraftLogDesktop` | `DraftLog` |

Two pieces of state live in `Desktop()` and drive both columns: `leftPane` (`"breakdown" | "collection"`, defaults to `"collection"`) and `trackerAccount` (`number | null`, null meaning all accounts).

## Mobile composition, inside `Mobile()`

The mobile profile is a separate render path and shares no layout with `Desktop()`, so the wiring is its own.

| Slot | Public | Tracker owner |
|---|---|---|
| Header | avatar, name, rank, set, stat chips | unchanged, `TrackerStatsBlock` does not fit here |
| Breakdown tabs | `POINTS` / `DECK COLORS` / `PIPS` | plus `COLLECTION` |
| Collection tab body | — | `AccountTabs` + `RefreshButton` row, `TrackerStatsBlock`, `Collection` |
| Event log section | `EventLogRow` list with format and colors filters | `DraftLog` |

`trackerAccount` lives in `Mobile()` and reaches the collection tab through `MobileBreakdown`'s one `tracker` prop, which is null on every other profile. That prop is also what adds the fourth tab, so the gate hook is never called twice.

`MobileBreakdown` renders the tab row it always had. The labels shortened to fit four across a phone: `POINTS BY FORMAT` → `POINTS` and `COLORS PLAYED` → `PIPS`, for everyone, not only the owner. The tab choice still persists to `localStorage` under `player-breakdown-tab`; `collection` is a legal stored value and falls back to `deckColors` where the tab is not offered, the same way `format` already did for an unranked player.

`Collection` and `DraftLog` both read `useIsMobile()` and reshape themselves:

- **`Collection`** stacks rares above mythics instead of side by side, drops the economy inputs to two columns, stacks the toggle strip, and skips the hover card preview. `CardRow touch` grows the tap target and wraps the count 4 → 0, since a phone has no right click to walk it back down.
- **`DraftLog`** keeps `# COLORS DECK W/L R M ⌄` and cuts queue, date, gems, packs and the note preview, which the expanded row shows instead. `LOG_COLS_MOBILE` declares one track per emitted cell, so a row is one grid line. The chevron turns gold when the draft carries a note, standing in for the note column.

## Shared components

| File | Exports |
|---|---|
| `Collection.tsx` | `Collection` — economy inputs, derived cells, playset/singles toggle, completion bars, card grid |
| `DraftLog.tsx` | `DraftLog`, `DraftNotesPanel`, `CountCell` — the log, sorting, format filter, row expansion, notes |
| `AccountTabs.tsx` | `AccountTabs` — ALL plus one tab per Arena account, hidden when there is only one |
| `RefreshButton.tsx` | `RefreshButton` — the `⟳ 17L` control |
| `TrackerStatsBlock.tsx` | `TrackerStatsBlock` — rares, avg rares, avg mythics, gems, gems used, packs |
| `trackerStyles.ts` | `HEADER_CLS`, `SUBLABEL_CLS`, `COLOR_HEX` |

Data helpers live in `data/trackerDrafts.ts` (`arenaDrafts`, `useDraftRates`, `useTrackerTotals`) and `data/trackerApi.ts`. Projection maths is `data/collectionProjection.ts`.

## Known gaps, carried over

- **The `⟳ 17L` button is dev-only.** `refreshDraftData` posts to `${LOCAL_SUPABASE_URL}/tracker/refresh`, an endpoint that exists only on `bot/scripts/local_supabase_proxy.py`. In a deployed build it will fail. A real deployment needs either a bot HTTP endpoint or a Pages Function with database write access.
- **The collection is not per-account.** `tracker_collection` has no account column, so switching accounts changes the log and the projections but not the owned card counts.
- **`PickTwoDraft` filters under `QUICK DRAFT`.** That is deliberate: `scoring_buckets.json` buckets it under Quick, and the filter reads the same source of truth. Not a bug, and not worth a separate option.
- **The mastery track is per-set data covering five sets** (`MASTERY_TRACKS` in `collectionProjection.ts`). Three different track shapes exist across Arena's history; only the newest is modelled, so an older set falls back to HOB's numbers and will read wrong. Harmless while only current sets are tracked.
- **Migration `tr4ck3r0001` is still unpushed** and carries the whole tracker schema, including the `ranked_season_packs` column that was renamed in place from `future_pass_packs`.

## Verifying

There is no test suite for any of this; it is checked by looking. Run the proxy and the dev server, then on a phone-width viewport:

- The Collection tab appears for the owner and nowhere else. A second player's profile shows three tabs and no tracker chrome.
- Card counts tap up, wrap to zero past four, and the playset/singles toggle switches the bars and the colour-section counts.
- A draft row expands, a note saves on blur, it survives a reload, and the chevron goes gold.
- Account tabs change the log and the projections.

Confirm the public mobile profile is untouched by loading someone else's page at the same width.
