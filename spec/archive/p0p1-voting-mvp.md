# Pack 0, Pick 1 Voting MVP - Spec

---

## Goals

We will run a contest.

Participants will choose one MtG card for each of 8 slots, plus a tiebreaker slot.

Participants will be ranked according to the 17lands.com GIH win rate of their full roster of 8 cards (with tiebreaker for ties) after 6 weeks.

This spec covers the first phase of the contest - the voting phase.

---

## Basic specifications

- Logged in users only (Discord OAuth via Supabase)
  - Votes key on `auth.users.id` — participants do not need to be on the leaderboard or have a 17lands token
- The first contest is for the **Marvel Super Heroes (MSH)** set
- A new page at `/p0p1`, added to the top nav for all users
- Voting open until a hardcoded deadline, users can edit until then

### Slots

9 slots total, presented in this order:

| # | Slot key | Label | Rarity | Color constraint |
|---|----------|-------|--------|-----------------|
| 1 | `white_common` | White Common | Common | Mono-W only |
| 2 | `blue_common` | Blue Common | Common | Mono-U only |
| 3 | `black_common` | Black Common | Common | Mono-B only |
| 4 | `red_common` | Red Common | Common | Mono-R only |
| 5 | `green_common` | Green Common | Common | Mono-G only |
| 6 | `multicolor_uncommon` | Multicolor Uncommon | Uncommon | 2+ colors only |
| 7 | `wildcard_common` | Wildcard Common | Common | Any color (including multicolor, colorless) |
| 8 | `wildcard_uncommon` | Wildcard Uncommon | Uncommon | Any color (including mono, multicolor, colorless) |
| 9 | `tiebreaker` | Best Hero | Common, Uncommon, or Rare | Any color |

**Constraints:**
- No card may appear in more than one slot across a player's ballot
- Wildcard common excludes cards already picked in slots 1-5
- Wildcard uncommon excludes the card picked in slot 6
- Tiebreaker excludes all cards picked in slots 1-8
- Tiebreaker is filtered to cards with the Hero creature type
- No mythic rares in any slot (tiebreaker caps at rare)

---

## Card data

### Fixture (MVP)

A static frontend JSON fixture containing all eligible cards from MSH (256 cards: 96 common, 100 uncommon, 60 rare — no mythics).

Card shape:
```ts
{
  name: string            // primary key for voting
  manaCost: string        // e.g. "{3}{R/G}"
  cmc: number             // converted mana cost
  colors: string[]        // e.g. ["W"], ["U","B"], [] for colorless
  rarity: "common" | "uncommon" | "rare"
  typeLine: string        // full type line, e.g. "Legendary Creature — Human Hero"
  collectorNumber: string // for set-order sorting
  imageSmall: string      // Scryfall small image URI
  imageNormal: string     // Scryfall normal image URI
  imageArtCrop: string    // Scryfall art crop URI (wide, no frame)
}
```

Source: Scryfall API (`set:msh`, filtered to common/uncommon/rare).

### Future: DB table + seed script

Replace the static fixture with a `cards` table populated by `bot/scripts/seed_cards.py` (pulls from Scryfall once per set). Frontend reads via a `public_cards` view. Follows the existing `seed_sets` / `seed_local_players` pattern.

---

## Data model

### `contest_votes` table

```sql
contest_votes (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid references auth.users(id) not null,
  set_code      text not null,
  slot          text not null,
  card_name     text not null,
  last_updated  timestamptz default now(),

  unique (user_id, set_code, slot),      -- one card per slot
  unique (user_id, set_code, card_name)  -- no duplicate cards across slots
)
```

Slot values: `white_common`, `blue_common`, `black_common`, `red_common`, `green_common`, `multicolor_uncommon`, `wildcard_common`, `wildcard_uncommon`, `tiebreaker`.

### Write path

RLS + direct Supabase insert/upsert from the frontend. RLS policy: `auth.uid() = user_id` for INSERT, UPDATE, and SELECT.

No `public_contest_votes` view for MVP — picks are hidden from other users until the deadline. Users read only their own votes via RLS.

### Deadline enforcement

Frontend-only for MVP: the UI disables voting after the deadline constant. Server-side enforcement is deferred.

> **Note for maintainer:** Before the deadline, verify that no one has submitted votes by calling Supabase directly after the UI locks. If this becomes a concern, add a timestamp check to the RLS policy (e.g. `current_timestamp < '2026-08-07T23:59:59Z'`).

> **Future:** A `contests` table (`id`, `set_code`, `voting_deadline`, `tiebreaker_type`, `status`) would let deadlines and tiebreaker rules be managed without code changes.

---

## Frontend

### Routing

New route: `/p0p1` — top-level, not nested under `/leaderboard`.

### Navigation

Added to the top nav alongside Leaderboard, Pods, Tier List, About. Visible to all users (logged in or not).

### Page layout

**Header area:**
- Contest title, set name (MSH), countdown timer to deadline

**Rules section** (always visible):
- Explanation of the contest format, slot descriptions, scoring method
- Link to 17lands card data for reference

**Logged-out state:**
- Rules section + "Log in with Discord to participate" CTA

**Logged-in state:**
- The 9 slots stacked vertically, each showing:
  - Slot label (e.g. "White Common")
  - Current pick (card image + name) or empty state
  - Tap/click to open the card picker
- Progress indicator: "X/9 slots filled" — persistent, visible
  - Incomplete: warns that ballot won't count
  - Complete (9/9): confirmation message

### Card picker

Search + autocomplete in a modal/panel:
- Opens with full list of eligible cards for that slot
- Search bar at top to filter by name
- Each list item: art crop thumbnail + card name + mana cost
- Tap to select, picker closes
- Already-picked cards (from other slots) excluded from the list

### Auto-save

Each slot saves immediately on selection (upsert to `contest_votes`). No explicit submit button. The progress indicator communicates ballot completeness.

### Data layer

Follows the existing `api.ts` / `mockApi.ts` / `realApi.ts` pattern:
- Mock mode: fixture-backed, votes stored in memory
- Real mode: reads card fixture, writes votes to Supabase via RLS

---

## Out of scope for MVP

- Post-voting results/scoring UI (separate spec — will fetch full 17lands card ratings for all picked cards)
- Public visibility of other players' picks (hidden until deadline)
- Server-side deadline enforcement (frontend-only for MVP)
- DB-backed card data (static fixture for MVP)
- Multiple contests per set
- Configurable tiebreaker types (hardcoded to Hero for MSH)
- Future set support engineering (noted where low-hanging fruit exists)

---

## MSH card pool summary

| Category | Count |
|----------|-------|
| Commons | 96 (15 per color W/U/B/R/G, 0 multicolor, 21 colorless) |
| Uncommons | 100 (20 multicolor) |
| Rares | 60 |
| Hero type cards | 81 (across common/uncommon/rare) |
| **Total eligible** | **256** |
