# Pod Draft — Round Robin pairing mode

Status: **designed, not built**. No code exists yet. This doc is the design; implement it as written or push back on a specific point before starting.

## What this is

A fifth value of `pod_draft_events.pairing_mode` (`swiss` / `bracket` / `random` / `team` / **`roundrobin`**), selectable anywhere the pairing dropdown appears. Everyone at the table plays everyone else exactly once, over the same three rounds a pod already runs. Same lobby, ready check, draft, report buttons, standings, and finalize as a Swiss pod — only the pairing function changes.

It exists for **4-player pods**, which is what Pick 2 drafts are for. At four players, three rounds is a complete round robin: every player faces all three opponents, and the pod is decided on the table instead of on tiebreakers. At six players a full round robin needs five rounds, which is a different event; this mode does not try to serve it.

Round Robin (pairings) and Pick 2 (`picks_per_pack`, a Draftmancer draft setting) are independent switches that happen to suit the same table size. Neither implies the other.

## Core mechanics

- **Roster gate: exactly 4.** `pod_round_robin.supports(n)` returns `n == 4`, and `start_tournament` falls back to `swiss` for any other size, exactly as `bracket` falls back today (`pod_tournament.py:1026`). The organizer can select the mode on any pod; a pod that fires with 6 or 8 players quietly plays Swiss. The fallback persists through `persist_pairing_mode`, so the stored mode always matches what was actually played.
- **The schedule is fixed and results-independent.** From the draft-seat order `s0..s3`:

  | Round | Matches |
  |---|---|
  | 1 | `s0` vs `s2`, `s1` vs `s3` |
  | 2 | `s0` vs `s1`, `s2` vs `s3` |
  | 3 | `s0` vs `s3`, `s1` vs `s2` |

  Round 1 pairs across the table, which is the convention `pod_swiss.pair_round` already uses for round 1 (seat `i` vs seat `i + half`), so a Round Robin pod opens with the same matchups a Swiss pod of the same seating would. Rounds 2 and 3 complete the circle. No rematch is possible by construction, so there is no pairing failure path to alert on.
- **Seat order comes from the draft log, resolved once.** `start_tournament` persists seat indexes from the log (`manager.persist_seat_indexes_from_log()`, the same call `start_team_tournament` makes) before pairing round 1, so all three rounds read one stable order out of `pod_draft_participants.seat_index`. When seats are unknown the pairer falls back to `manager.tournament_players` order, which still yields a valid round robin. The order must be resolved the same way in every round: if round 1 pairs on seats and round 3 falls back to roster order, players get rematched.
- **Rounds stay gated, as in Swiss.** Round 2 pairings post once both round 1 matches are reported, through the existing `advance_to_round` / `_advance_locked` path. The schedule is known up front and could be posted all at once (team mode does exactly that), but ungating costs more than it buys here: `_post_or_update_live_standings`, `mark_trophy_match`, the championship post, and trophy hype all key off "round 3 is complete" meaning "the pod is over", which stops being true when rounds can close out of order (`pod_tournament.py:4123` is the no-op team mode needed). With four players a round is one other match, the same wait every Swiss pod already has. Ungating is a later change, not a prerequisite.
- **Nothing about scoring changes.** Each player plays three matches, so 3-0 is a trophy and 2-1 is 2 pod points through the existing finalize path, bot and frontend, with no formula change. Standings stay `pod_swiss.compute_standings` (wins → OMW% → GW% → OGW% → name). A 3-0 player is the champion. When the table cycles and nobody goes 3-0, the existing tiebreakers resolve it: OMW% is near-degenerate in a round robin because everyone faced the same field, so in practice game win percentage decides. That is acceptable for v1 — head-to-head as an explicit tiebreak would mean a second standings implementation for one mode.
- **`mark_trophy_match` needs no change.** It stamps any final-round pairing containing a genuinely undefeated player, which is still the right reading in round 3 of a round robin.
- **Draftmancer is not involved.** Pairings are ours; nothing is emitted to the session.

## What it touches

- **New** `bot/services/pod_round_robin.py` — pure functions only, mirroring `pod_bracket` / `pod_team`: `supports(roster_size)` and `pair_round(players, round_num)` returning `[(player_a_id, player_b_id), ...]`.
- `bot/services/pod_pairing_select.py` — a fifth `PAIRING_MODES` entry. `DEFAULT_PAIRING_MODE` stays `bracket`. The dropdown is shared, so the option appears in the lobby Settings panel, `/draft`, and the scheduled signup card with no further wiring.
- `bot/services/pod_tournament.py` — the roster gate in `start_tournament`, the seat-index persist for this mode, and a pairing dispatch in `advance_to_round` beside the `pod_swiss.pair_round` call. Nothing else: gated rounds mean the report, advance, standings, finalize, and recovery paths are untouched.
- `bot/commands/testlobby.py` — a preview state that arms a 4-player lobby and runs the mode end to end, added to `PRODUCTION_SAFE_TESTS` only if it renders without creating a pod.
- `spec/pod-coordination.md` — a line under pairings, in the same commit as the behavior.
- Frontend: nothing. No view or component reads `pairing_mode`; the pod page renders whatever match rows exist.

## Decisions to confirm

1. **Gate at exactly 4, or allow any size where a full round robin fits three rounds?** Only 4 fits, so this is really "reject 6 and 8 silently (fall back to Swiss) or refuse the selection at pick time". Recommendation: silent fallback, matching Fast Bracket's existing behavior, since the pod size is not known when the mode is chosen.
2. **Label and description** for the dropdown entry, plus whether the mode says anything in the thread when a pod falls back to Swiss for size. Copy gets proposed at implementation time, not here.
3. **Ungated rounds** (post all three at once, every report button live from the start) — worth it only if the round-to-round wait actually bites in play. Defer until a few pods have run.

## Testing

Logic tests for `pod_round_robin.pair_round`: the union of the three rounds is all six pairs, no pair repeats, and every player appears once per round. `supports` table-driven over sizes 2/4/6/8. The end-to-end path (thread posts, report buttons, standings, finalize) is verified by running a 4-player pod on the test server, not by tests.
