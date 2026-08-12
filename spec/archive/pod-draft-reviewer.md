# Spec — in-site pod draft reviewer (`DraftReviewMOCS`)

The MTGO/MOCS-style full-screen pod draft reviewer, wired to live data and reachable from the pod pages. This documents the finished behavior, the data flow, and the invariants to preserve.

## What it is

A full-screen (`fixed inset-0 z-50`) reviewer that replays a pod draft pick-by-pick from any seat's vantage: the booster as that seat saw it, the running pool (curve or pick-order), the neighbors' pools, a table map of all seats, and the player's final deck. Desktop layout is `lg+`; mobile has its own bars. The component is presentational and prop-driven — it holds no router or fetch logic.

- Component: `frontend/src/components/pod/review/DraftReviewMOCS.tsx`
- Card image helper: `frontend/src/components/pod/review/ReviewCard.tsx` (`CardImage`, `scryfallImageUrl`)
- Derivations over the artifact: `frontend/src/data/draft-artifact.ts` — `reconstructDraft`, `poolBefore`, `poolByPack`, `seatColors`, `seatHandle`, `resolveDeck`

## Data flow

The reviewer renders entirely from a single `PodDraftArtifact` (`frontend/src/types/leaderboard.ts`) plus optional per-seat participant metadata the artifact doesn't carry.

```
public_pod_draft_log.draft_log ──fetchPodDraftArtifact──▶ PodDraftArtifact
public_pod_event_participants  ──usePodEventParticipants──▶ assignSeats ──▶ ReviewSeatInfo[]
                                                       │
                              PodDraftLogRoute (PodPage.tsx) assembles props
                                                       │
                                                       ▼
                                              <DraftReviewMOCS …/>
```

- `PodDraftArtifact`: `{ t? v sid? set seats[] cards[] packs[][] picks[][][] decks[] }`. Everything references the card table by index. `decks[seat] = { main, side }` are card-index lists for the final maindeck and sideboard; `null` for events drafted before deck capture.
- The reviewer never fetches. It receives the artifact, the event meta, and (when available) `seatInfo`.

### Component props

```ts
DraftReviewMOCS({
  artifact: PodDraftArtifact,
  meta: { setCode: string; name: string },
  initialSeat?: number,          // seat to open on
  onClose?: () => void,          // ✕ / header title → back to the pod
  onSeatChange?: (seatIndex: number) => void,  // fired on every seat switch (URL sync)
  eventId?: string,              // for the deck popup's Discord-CDN screenshot refresh
  seatInfo?: ReviewSeatInfo[],   // per-seat screenshot/colors/record/draftLog; absent ⇒ deck popup hidden
})
```

`ReviewSeatInfo` (exported from the component) carries `seatIndex`, `displayName` (Discord handle, modal title), `participantDisplayName` (refresh lookup), `deckColors`, `deckScreenshotUrl`, `deckScreenshotCaption`, `record`, `draftLogUrl`. `setCode`/`title` derive from `meta`; seats come from `artifact.seats`.

## Routing

Registered in `frontend/src/App.tsx`:

| Route | Behavior |
|---|---|
| `/pods/:slug/log` | Resolves the champion (placement 1, else seat 0) and `<Navigate replace>` to `/pods/:slug/log/:who`. |
| `/pods/:slug/log/:who` | Renders the reviewer on that seat. |

`:who` is the player's leaderboard `playerSlug` when they have one, else the numeric seat index (pod-only players have no slug). `PodDraftLogRoute` (`frontend/src/pages/PodPage.tsx`):

- fetches via `usePodEventBySlug` + `usePodEventParticipants` + `usePodDraftArtifact` (all cached when arriving from `PodPage`, so navigation is instant; a full-screen `bg-bg` placeholder shows only on a cold hit),
- runs the same `assignSeats` used by `PodPage` so seat indices line up with the artifact,
- resolves `:who` (slug first, then numeric seat index) → `initialSeat`,
- `onClose` → `/pods/:slug`; `onSeatChange` → `navigate(.../log/<identifier>, { replace: true })` so the URL always reflects the viewed player without polluting history or remounting the reviewer.

`seatIdentifier(seat)` and `resolveLogSeat(seats, who)` live alongside the route.

### Entry point — `PlayerSeatPanel`

`frontend/src/components/pod/PlayerSeatPanel.tsx` "VIEW DRAFT LOG" routes to the in-site reviewer when an artifact exists:

- internal `<Link>` to `/pods/${eventSlug}/log/${playerSlug ?? seatIndex}` when `hasDraftLog`,
- else the external `draftLogUrl` (no regression for older pods),
- else the disabled "NO DRAFT LOG" state.

`eventSlug` + `hasDraftLog` are threaded from `PodPage` (desktop) and `MobileSeatStack` (mobile). The mobile/desktop button markup is unified in a local `DraftLogButton`.

## Features

### Navigation

- Pack/pick chips and prev/next arrows (header on desktop, `MobileNavDivider` on mobile).
- Keyboard: **←** previous pick, **→** next pick (in click-reveal mode with a hidden pick, → reveals first, then advances), **Space** toggles SHOW PICKS. Ignored when the deck popup is open, a modifier is held, or an input/textarea/contenteditable is focused.
- Switching seats while on the **literal last pick** resets the new seat to P1P1 ("I've reviewed this player; start the next from scratch"). Mid-draft switches hold the current pack/pick for cross-player comparison.
- Header set symbol + event title (desktop and mobile bars) is a button back to `/pods/:slug`.

### Pool views (CURVE / ORDER)

- **CURVE** is the default and the first toggle option; **ORDER** second. Persisted in `localStorage` (`draftReviewDeckLayout`), global across pods.
- Active player's pool cards are sized to the midpoint between the booster picks (200px) and neighbor cards (134px) — 167px (176px when neighbors are folded). Pool height is drag-resizable (`draftReviewPoolHeight`).
- The most recent pick is marked with a green **glow** (`.review-last-pick` in `frontend/src/styles.css`), a scaled-down version of the booster's `p0p1-card-selected`. Not an outline — `cn`/`twMerge` strips the bare `outline` class, and the glow reads better at small sizes.

### Sideboard split (SB)

- The **SB** toggle appears only when the seat's final deck has a sideboard (`decks[seat].side`). When on, the running pool is partitioned: drafted cards that ended up in the final sideboard peel into a single stacked column on the right; everything else stays in the curve/order view. The column fills as you draft cut cards, so navigation stays meaningful. The last-pick glow follows the pick into whichever side it lands.
- The sideboard column's height is intrinsic (the last card sits in normal flow inside a `[display:flow-root]` container, pushed down by `(n-1) * reveal`) so it never over/under-shoots regardless of the cards' rendered width. `overflow-y-auto overflow-x-hidden`, `px-2` for glow breathing, scrollbar flush to the panel's right edge (the pool row drops its right padding so the column reaches the edge; the deck keeps `px-2` breathing and a flush scrollbar too).

### Final-deck popup (DECK)

- The **DECK** button opens the shared `DeckScreenshotModal` (`frontend/src/components/pod/DeckScreenshotModal.tsx`) for the active player: IMAGE (screenshot) + CARD POOL (decklist) tabs, prev/next cycling seats. The decklist comes from `resolveDeck(artifact, seat)`; the screenshot/colors/record from `seatInfo`.
- The modal's **DRAFT LOG** tab is hidden here (`hideDraftLog` prop) — it will eventually point back at this reviewer, which would self-redirect.
- Hidden when `seatInfo` is absent or the seat has neither a screenshot nor a built deck.

### Table map (`PlayerGrid`)

- Two columns of four seats arranged so the pass arrows trace the ring. The horizontal `»`/`«` (top and bottom rows) and the up/down chevrons (between rows) are **absolutely positioned and add no layout space** — the tiles fill the panel height with no arrow columns or chevron bands between them. The loop reverses for right-to-left packs.
- Clicking a seat switches the reviewer and updates the URL (via `onSeatChange`).

### Misc

- `select-none` on the reviewer root so the pass arrows and player names aren't drag-selectable.
- COLORS / TABLE / SHOW PICKS switches; the toggle knob is 14px, nudged within its 32×18 track.
- The decklist's stacked card view (used by the popup) uses the 17lands treatment: a tall revealed strip (`STRIP_H` 48) so the full name bar shows, with the `×N` count badge centered between card frames.

## Invariants — keep these

- **Pass direction**: `PASS_DIRS = [1, -1, 1]`; pack 2 reverses who-passes-to-whom. Neighbor columns are the **fixed** seat-1/seat+1; the `»`/`«` arrow encodes direction. Don't reintroduce from/to swapping.
- **Card outlines** use `[outline-style:solid]` (not the bare `outline` class, which `twMerge` strips). The last-pick marker is a glow, not an outline.
- **Desktop breakpoint is `lg`** (1024), not `xl`. The page disables `scrollbar-gutter` while mounted.
- **P1P1**: the neighbor band is suppressed when neighbors have no picks; the pool expands and the fold chevron hides.
- **localStorage keys** (`draftReviewDeckLayout`, `draftReviewRevealMode`, `draftReviewPoolHeight`) are global across pods, by design — they're viewing preferences, not per-draft data.
- **Floating arrows add no layout space** — they're absolute; keep them that way when touching `PlayerGrid`.
- **Scoring/formula untouched** — this is a viewer over `public_pod_draft_log`; it writes nothing.
- `npm run dev` uses esbuild (no typecheck). Run `npx tsc -b` before committing.

## Touched files

- `frontend/src/components/pod/review/DraftReviewMOCS.tsx` — the reviewer (prop-driven; popup, SB split, keyboard nav, floating table arrows).
- `frontend/src/pages/PodPage.tsx` — `PodDraftLogRoute` + seat/URL helpers.
- `frontend/src/App.tsx` — `/pods/:slug/log` + `/pods/:slug/log/:who` routes.
- `frontend/src/components/pod/PlayerSeatPanel.tsx` — "VIEW DRAFT LOG" → in-site reviewer; `DraftLogButton`.
- `frontend/src/components/pod/MobileSeatStack.tsx` — threads `eventSlug` + `hasDraftLog`.
- `frontend/src/components/pod/DeckScreenshotModal.tsx` — `hideDraftLog`; 17lands decklist strip.
- `frontend/src/styles.css` — `.review-last-pick` glow.
