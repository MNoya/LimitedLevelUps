# Pod Draft — Lobby Settings & Seating modes

Design note for the lobby **Settings** controls (`/pod-settings` and the lobby-embed Settings button),
with a new **Seats** control whose marquee mode is automatic **Leaderboard** seeding.

## Current state

The Settings panel (`bot/services/pod_settings_view.py`) renders two dropdowns plus one contextual button:

| Control | Options | Status |
|---|---|---|
| **Format** | Latest, Cube | Implemented, no changes |
| **Pairings** | Swiss Tournament, Fast Bracket | Implemented (Swiss pairing logic under separate review) |
| **Seats** | — (only a manual *Seat Order* button) | Becomes a real 3-option control here |

Seat order today is a single manual action: the **Seat Order** button (`pod_seating_select.SeatOrderButton`)
opens a modal to hand-reorder the players **already connected** to Draftmancer. It only appears when a live
`PodDraftManager` exists for the thread, and the chosen order is held in-memory as `manager.desired_seating`
and re-emitted once right before `startDraft` (`pod_draft_manager._reapply_seating_if_set`).

### Why seat order matters (the load-bearing fact)

Round-1 pairings are derived **from the draft-table seats**, not chosen independently
(`bot/services/pod_swiss.py:74`):

```python
if round_num == 1 and all(p.seat is not None for p in players):
    ordered = sorted(players, key=lambda p: p.seat)
    half = len(ordered) // 2
    return [(ordered[i].id, ordered[i + half].id) for i in range(half)]   # seat i vs seat i+half
```

Seat *i* plays seat *i+half* — the player **furthest across the table**, i.e. the one you had the **least
draft interaction with** (you neither fed nor starved them). Seats themselves come from the Draftmancer draft
log at start (`persist_seat_indexes_from_log` → `_load_seat_indexes`). So: **whatever we push to Draftmancer
via `setSeating` becomes the seat indices, which become the round-1 matchups.** Seating is the lever; pairing
is the consequence.

## Seats and Pairings are orthogonal

- **Seats** controls *only* how players are physically arranged in the Draftmancer table (what we push via
  `setSeating`).
- **Pairings** decides each round's matchups, consulting the seats when its mode calls for it.

A round's matchup is the product of both: the seat arrangement (Seats) *and* whether the pairing mode reads
seats (Pairings).

## Seats modes

A dropdown parallel to Format and Pairings, persisted on the event so the choice survives restarts and can be
set **before the lobby is live**.

| Mode | Draftmancer arrangement | `setSeating` |
|---|---|---|
| **Random** (default) | Draftmancer randomizes the table. Round-1 matchups then follow whatever **Pairings** mode is set. | none; `setRandomizeSeatingOrder true` |
| **Manual** | Organizer hand-arranges the connected lobby via the Seat Order button/modal (today's behavior). | `setRandomizeSeatingOrder false` + `setSeating <order>` |
| **Leaderboard** | Bot arranges the table by leaderboard rank into the seeded layout below. | `setRandomizeSeatingOrder false` + `setSeating <computed order>` |

Random stays the default — neutral baseline, no identity resolution needed.

## Pairings modes

Default is **Swiss Tournament**.

| Mode | Round 1 | Rounds 2–3 |
|---|---|---|
| **Swiss Tournament** (default) | Cross-table by seat (seat *i* vs seat *i+half*). | **Seat-proximity bracket**: R2 = play 2 seats away, R3 = adjacent. With Leaderboard/Manual seats → protected seed bracket (top seeds rewarded; #1 & #2 meet only in R3). |
| **Fast Bracket** | Cross-table by seat. | Fast: winners-play-winners / losers-play-losers the moment both finish, rematch-free. No proximity. |
| **Random** | Truly random, **seats ignored**. | Record-based. |

Swiss uses the seats **every round**; Fast Bracket and Random use them only for R1. **Engine change:** Swiss R2–3
today pairs seat-*adjacent* greedily (`pod_swiss._pairing_order`), which would sit #1 next to #2 — it must
instead pair by seat *distance* (2-away, then adjacent) within each record group.

"Cross-table by seat" = `pod_swiss.pair_round` (seat *i* vs *i+half*, furthest across the table).

Two independent shuffles: **seat order** (Draftmancer → draft adjacency) and **pairings** (opponents).
Swiss/Bracket take opponents from the seats; **Random** runs its own shuffle, ignoring seats.

| Seats + Pairings | Round-1 opponents |
|---|---|
| Leaderboard + Swiss/Bracket | Seeded — 1v8, 2v7… |
| Random + Swiss/Bracket | Random, draft-separated (PT Day-1) |
| any + Random | Random, seats ignored — may pair neighbours |

Random seats needs `setRandomizeSeatingOrder true` (shuffled, not join-order).

## Leaderboard seating — the seat layout

A conventional seeded bracket mapped onto the round table, so Swiss pairs by distance each round and top seeds
are rewarded + protected to the final: **R1 across (seat ±half), R2 two seats away, R3 adjacent.**

For 8: top half in rank order, bottom half reversed, **and** swap seeds **3↔4 / 5↔6** (so #1's R2 is the
*weakest* bracket, 4·5, not 3·6):

| Seat | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|------|---|---|---|---|---|---|---|---|
| Rank | #1 | #2 | **#4** | **#3** | #8 | #7 | **#5** | **#6** |

- **R1 (across):** 1v8, 2v7, 4v5, 3v6.
- **R2 (2 away):** W(1·8) v W(4·5), W(2·7) v W(3·6) — #1 & #2 in opposite halves, can't meet before R3.
- **R3 (adjacent):** trophy match.

Notes:
- Without the swap #1/#2 are still protected, but #1 draws the stronger 3·6 winner in R2 — the swap restores the
  conventional reward.
- **Manual** seating runs the same proximity pairing on the organizer's order. **Random** seats keep R1
  draft-separated; R2–3 proximity still applies, just unseeded.
- Optional non-determinism: flip players within a cross-table pair and/or rotate the ring — preserves every
  matchup (all relationships are symmetric about the diameter), only scrambles absolute seats.
- Clean proximity bracket is defined for **8**; 6/10 Swiss falls back to record-ordered (TBD when those sizes land).

Ranking source: active-set leaderboard (`player_stats.rank_players_for_set`), same standings as `/pod-seeding`.
Draftmancer users resolve to players by the existing name matching (`pod_drafts.players_for_names`).

### Unranked players

Anyone the lobby surfaces who isn't on the active leaderboard (unlinked, opted out, no score, or an
unresolvable handle) has **no rank**. They sort to the **bottom** of the rank order (consistent with how
`/pod-seeding` already drops unranked to the end), tie-broken randomly among themselves. They therefore land
in the lowest seeds and draw the strongest opponents — the same treatment as a low-ranked player.

## Competitive integrity rationale

- **Rewards the leaderboard.** 1vN seeding gives the top seed the weakest round-1 opponent — standard
  playoff seeding, so leaderboard standing buys a real (earned) advantage.
- **Keeps draft separation.** Opponents are still 4 seats apart, so your round-1 opponent is the player you
  had the least draft interaction with. Table politics (hate-picks, color-cutting) can't taint the match.
- **Doesn't punish weaker players unfairly.** Lowest seeds draw the strongest opponents — earned by rank, and
  the same exposure a low seed gets in any seeded bracket.
- **Accepted tradeoff:** the four strongest players sit contiguously (seats 1–4) and cut each other in the
  draft — a mild equalizer. Spreading skill around the table would scramble the clean pairing geometry, so we
  keep the contiguous layout.

## Persistence & model

Add a column mirroring `pairing_mode`:

```
pod_draft_events.seating_mode  TEXT NOT NULL  server_default 'random'   # 'random' | 'manual' | 'leaderboard'
```

- Alembic migration + `seating_mode` on the `PodDraftEvent` model.
- `set_event_seating_mode(event_id, mode)` + `persist_seating_mode` (parallel to `set_event_pairing_mode` /
  `persist_pairing_mode`), and `load_event_seating_mode_sync` for manager hydration on connect.
- `manager.seating_mode` loaded on connect (like `pairing_mode` at `pod_draft_manager.py:1116`).
- For **Leaderboard** we persist only the *mode*, never a frozen order — the order is recomputed live from the
  current roster + current standings. For **Manual** the concrete order stays in-memory (`desired_seating`),
  set live and re-applied at start, as today.

## Application lifecycle

The hooks already exist; Leaderboard generalizes the one-shot manual path into an automatic one.

- **On every lobby roster change** (`_on_session_users`, fires on each join/leave): if mode is
  `leaderboard`, recompute the seat order from the **currently present** users and emit `setSeating`. Because
  the order is computed from who's actually present, the `set_seating_order` "lobby changed since the panel
  opened" guard (`pod_draft_manager.py:860`) no longer applies — the set always matches.
- **Right before `startDraft`** (`_reapply_seating_if_set`, already called from `_start_draft`): re-assert the
  order so a late join/leave can't leave a stale arrangement. This is the authoritative application; the
  on-join updates are cosmetic-but-helpful (players see their intended seat as the lobby fills).
- **Random**: emit `setRandomizeSeatingOrder true` once; never `setSeating`.
- **Manual**: unchanged — the Seat Order button writes `desired_seating`, re-applied at start.

### Cadence note (jumpiness)

Re-applying on every join means seats visibly shuffle as people trickle in, only stabilizing once the lobby
is full. This is acceptable and arguably informative (you can see your seed), and the pre-`startDraft`
re-assert is what actually counts. If the churn proves annoying we can debounce or only apply once the roster
reaches the expected size — flagged, not decided.

## Settings-panel UX

- A **Seats** dropdown joins Format and Pairings (options: Random / Manual / Leaderboard), available
  **pre-session** since it only persists the mode. Selecting a mode posts the usual public thread notice and
  refreshes the registration embed (same pattern as Format/Pairings changes).
- The **Seat Order button** stays, but is contextual to **Manual** mode and a live lobby (≥2 connected) —
  it's the manual editor, not a general control.
- Selecting **Leaderboard** with a live lobby applies immediately; selecting it pre-session just records the
  mode and the bot applies it once players start joining.

## Edge cases & open policy choices

1. **Odd / non-8 pods.** `half = N // 2`; round-1 pairs seat *i* vs seat *i+half*; the leftover middle seat
   takes a **bye**. *Open choice:* does the bye go to the **top** seed (reward) or **bottom** seed? Recommend
   **top seed** — consistent with rewarding standing. (Fast Bracket runs at 8 and 10, the two table sizes;
   Swiss handles everything else.)
2. **Fast Bracket + Leaderboard.** Fast Bracket uses the seeded seats only for its opening cross-table round,
   then advances by record/readiness (no proximity). Seeding still gives the seeded R1; that's by design.
3. **Unresolvable handles.** A connected Draftmancer name that matches no player → treated as unranked
   (bottom seeds). Log it so organizers can `/pod-link-arena` the player.
4. **Predictability.** Public leaderboard makes seats/pairings knowable in advance. Low risk given opponents
   are draft-separated; noted, not mitigated.

## Implementation outline

1. **Model + migration:** `seating_mode` column (`random` | `manual` | `leaderboard`, default `random`).
2. **Persistence:** `set_event_seating_mode` / `persist_seating_mode` / `load_event_seating_mode_sync`;
   hydrate `manager.seating_mode` on connect (mirrors `pairing_mode`).
3. **Seat-order helper (pure):** (present userNames, standings) → ordered userNames — top-in-order +
   bottom-reversed + 3↔4 / 5↔6 swap (8-pod), unranked at the bottom. Reuses `rank_players_for_set` +
   `players_for_names`.
4. **Seating application:** in `_on_session_users`, if `leaderboard`, compute + `setSeating`; generalize
   `_reapply_seating_if_set` to recompute for leaderboard (not replay a frozen list); emit
   `setRandomizeSeatingOrder true` on Random. Manual unchanged.
5. **Swiss proximity pairing (engine change):** `pod_swiss` rounds 2–3 pair by seat *distance* (2-away, then
   adjacent) within record groups, rematch-free, replacing today's seat-adjacent greedy. Defined for 8; other
   sizes fall back to record-ordered. Fast Bracket and Random unchanged.
6. **Settings UX:** `pod_seating_select` gains a Seats mode dropdown; Seat Order button gated to Manual;
   change notices + registration-embed refresh.
7. **Tests (logic only):** seat-order helper (8 → expected table; unranked → bottom; unmatched names); Swiss
   R2–3 proximity (R2 splits #1/#2 into opposite halves; #1 draws the 4·5 winner; R3 adjacent; rematch-free);
   R1 unchanged. No tests for Draftmancer socket emits.

## Out of scope

- Multi-pod splitting when 9+ RSVP (how leaderboard seeding distributes across two pods) — separate design.
- Clean proximity bracket for 6/10-player Swiss (8 is defined here; others fall back to record-ordered).
- Frontend display of seats.
