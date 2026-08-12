# Pack 0, Pick 1 — Results Phase

## Overview

The final phase of the P0P1 contest runs in two stages once the MSH voting deadline (2026-06-23) passes:

1. **Midway** — after a manual mid-window ratings snapshot is committed, the page switches from the popularity display to a personal comparison view: your score vs. the best-possible team vs. the most-popular team. No other players' results are shown.
2. **Final** — after the ratings JSON is updated to mark the data final (~28 days after the voting deadline), the full leaderboard, per-slot comparison, and highlights reel are revealed.

Both stages are **data-gated** off the ratings JSON (see Data approach). The popularity phase (`spec/p0p1-after-submissions-closed.md`) is replaced by midway once the JSON is present.

This is the phase deferred by `spec/p0p1-after-submissions-closed.md` ("Scoring mechanics, the results leaderboard, and the highlights reel ... are a separate phase") and is the counterpart to the voting phase (`spec/p0p1-voting-mvp.md`) and the post-submission popularity phase (`spec/p0p1-after-submissions-closed.md`), both of which are built and shipped.

**Layout is not locked.** The results leaderboard, team-comparison, and per-slot comparison UI go through `frontend-design` mockups for sign-off before implementation — not ASCII sketches. Midway content is also deferred to implementation time, since it depends on what comparison UI ends up looking like.

## Phase: Midway

Shown when the ratings JSON is present and `phase === "midway"`. Replaces the popularity display as the page headline.

Personal comparison only — no leaderboard, no highlights reel. Logged-in users see:

- Their current score (summed GIHWR of their picks, based on the snapshot)
- vs. best-possible team score
- vs. most-popular team score
- The data window the snapshot covers (from `dateRange` in the JSON)

Logged-out users see the comparison teams and their scores but no personal result.

**Does not require `public_p0p1_ballots`** — best-possible team is computed from ratings data alone (uniqueness-constrained assignment), most-popular team from `public_p0p1_pick_stats` (already public), and the user's own ballot is accessible via RLS.

## Phase: Final

Shown when the ratings JSON is present and `phase === "final"`. All surfaces inherit the existing P0P1 visual system — Bebas Neue display / Space Grotesk body / JetBrains Mono tabular numerals; the dark mat palette; the 4px colored top-rail tile idiom; the chamfer scorecard.

Sections, in order:

### 1. Hero

### 2. Your result (logged-in)

### 3. Results leaderboard

### 4. Per-slot 3-way comparison

Extends the existing 2-way `PickVersusCard` modal to three columns, now keyed on **GIHWR** (pick% demoted to a small caption).

### 5. Highlights reel

## Scoring

- **Score = summed GIHWR** of a player's 8 picks (e.g. 442.10).
- **Incomplete ballots are ranked with a partial sum** — missing slots contribute 0, so they sink naturally. No exclusion or separate listing. Consistent with the existing `hasParticipated = scoringFilled > 0` logic in `useP0P1Ballot`.
- **Sample floor**: cards below the 17lands default visibility threshold (~500 GIH) are treated as missing data — they contribute 0 to a player's score and are excluded from the best-possible team. Prevents a low-sample fluke from dominating.
- **Ranking ties** on a continuous summed float are effectively impossible; no tiebreaker slot exists (it was removed from the format).

### Comparison teams

- **Best-possible team** and **most-popular team** are **legal ballots** — they respect the contest's no-duplicate-card-across-slots constraint (a small constrained assignment over the slots, not a per-slot argmax). They are real, attainable ballots, not an unreachable upper bound.
- Note the distinction: the per-slot comparison's "best pick" is the slot-local best card, which may differ from the card the best-possible _team_ uses for that slot (because the team optimizes across slots under the uniqueness constraint). These are two different "best" numbers by design and must be presented so the difference doesn't read as a bug.

### Highlights — award feed (final only)

A top-5 mixed feed of two named award types (replaces the earlier generic per-slot rank-gap pair):

- **Traps** — cards many voters picked that underperformed the best card available in their slot.
- **Sleepers** — cards almost nobody (possibly nobody) picked that outperformed the slot's crowd favorite, computed over each slot's full eligible pool (the card fixture + slot filters, since `public_p0p1_pick_stats` omits zero-vote cards). The only voter-named highlight; personal callouts are **positive-only** — negative stories stay at the card level, never at the person.

Selection metric was chosen empirically by prototyping both candidates against the real MSH data: rank-gap over the full pool labels 0–1-vote cards as "traps" and its magnitudes are tie-noise among the 1-vote tail, while **GIHWR effect-size** surfaces coherent stories. Selection mechanics (drama formulas, thresholds, quota-then-fill) live in `highlightsFeed()` in `frontend/src/data/p0p1Results.ts`.

## Data approach

The frontend reads two data sources for the results phases:

1. **Ratings fixture** (`frontend/src/data/fixtures/p0p1-ratings-msh.ts`) — a manually committed snapshot of 17lands card ratings for MSH Premier Draft. Generated via `fetch_p0p1_ratings`, committed, and deployed. Updated once at midway and once at final. Only common/uncommon cards (the P0P1 pool) are included; rares, mythics, and bonus sheet reprints are filtered out by cross-referencing the card fixture. The fixture includes:
   - Per-card `{ card_name, gihwr, gih }` entries
   - `phase: "midway" | "final"` — gates which UI is shown
   - `dateRange: { start, end }` — the 17lands data window, displayed in the UI

2. **`public_p0p1_ballots` view** — every voter's `(slot, card_name)` plus display identity, exposed as an RLS-bypassing view (runs as owner). Used only in the final phase for the leaderboard. No time gate — voting is closed and ballots are not sensitive once the deadline has passed.

No precomputed score tables — all ranking and comparison logic is computed live in TS from these two sources.

### Public views

Opening up the ballots requires **no change to the `p0p1_entries` RLS policies** — the base table stays locked (each user reads only their own rows). Instead, add an **RLS-bypassing `public_*` view** (runs as owner) — the exact pattern `public_p0p1_pick_stats` already uses. One new view migration mirroring an existing one; low risk.

- `public_p0p1_ballots` — every voter's `(slot, card_name)` plus a **display identity** denormalized from the Supabase `auth` schema (not `models.py` — auth-managed): `auth.users.raw_user_meta_data->>'user_name'` / `'full_name'` for the name and `->>'avatar_url'` for the Discord CDN avatar (ready-to-use, no `avatar_hash`→CDN step), joined by `user_id` exactly as `bot/scripts/p0p1_voters.py` already does. **Drop that script's `email` fallback** in the view; use a neutral `Anonymous entrant` label when no Discord name exists. **Never expose `auth.users.id` (the UUID) or email.**

The frontend pulls the whole ballots view in one request (~150 voters × 8 ≈ 1,200 rows). Clicking a leaderboard row expands data already loaded — **no per-user fetch, no addressable handle** (see Open / deferred).

### Frontend — computes everything in TS

New `frontend/src/data/p0p1Results.ts` (parallel to `frontend/src/data/scoring.ts`):

- per-user summed GIHWR (below-floor cards → 0) and rank;
- best-possible and most-popular teams (constrained assignment) and their summed GIHWR;
- the Trap/Sleeper highlights feed.

Follows the existing `realApi.ts` / `mockApi.ts` / `api.ts` / `hooks.ts` data pattern. Mock mode generates synthetic ratings over the MSH card fixture.

## Open / deferred

- **Per-ballot links / public handle:** deferred. v1 is **expand-in-place** — click a leaderboard row to reveal the ballot inline, no per-user URL. A stable public handle is the hard part (many voters have no `players` row, and Discord usernames aren't stable/unique), so it's introduced later alongside the `contests` table and a real cross-contest history view, when the feature that needs it exists. Players already have `/player/{slug}` as their cross-contest home.
- **Midway content detail:** deferred to implementation — depends on what the comparison UI looks like once mocked up.
- **Results trigger:** data-gated off `phase` in the ratings JSON. No ratings JSON → popularity phase. `phase: "midway"` → midway. `phase: "final"` → full results.

## Reuse map

- `frontend/src/data/p0p1Stats.ts` — `groupBySlot`, `findExtremes`, `classifyYourPick`, `buildPickVersus` (extend for the 3-way comparison).
- Components: `PickVersusCard`, `P0P1BallotScorecard`, `PostVotingStats`, `CommunityGrid`, `FullBreakdownList`.
- `frontend/src/data/useP0P1Ballot.ts` — `isPastDeadline`, `hasParticipated`, dev presets for forcing the scored state.
- `bot/scripts/p0p1_voters.py` — identity-resolution SQL for the ballots view.

## Verification

- Confirm `/card_ratings/data?expansion=MSH&format=PremierDraft` returns GIHWR + `# GIH` without a token.
- Mock mode with synthetic ratings: verify midway view (personal comparison, no leaderboard), final leaderboard, your-result, comparison teams (uniqueness constraint respected — no repeated card), highlights, logged-out state, desktop + mobile.
- Force midway and final states via the existing p0p1 dev presets.

## Future / maybe

- Click a user to see their performance across past contests.
- DB-backed card data and a `contests` table (`set_code`, `voting_deadline`, `scoring_date`) when a second contest rotates in, replacing the MSH-hardcoded constants.
