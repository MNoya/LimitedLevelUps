# Pod Draft — Round Robin pairing mode

Status: **built**, uncommitted. `pod_round_robin.py`, `pod_round_robin_vote.py`, the manager's offer trio, and the `pod_table_open_threshold` drop are all in the working tree; this doc is kept as the design rationale.

Two pieces ship together: the pairing mode itself, and the path that gets four leftover players to a table and asks them whether to play.

## What this is

A fifth value of `pod_draft_events.pairing_mode` (`swiss` / `bracket` / `random` / `team` / **`roundrobin`**), selectable anywhere the pairing dropdown appears. Everyone at the table plays everyone else exactly once, over the same three rounds a pod already runs. Same lobby, ready check, draft, report buttons, standings, and finalize as a Swiss pod — only the pairing function changes.

It exists for **4-player pods**, which is what Pick 2 drafts are for. At four players, three rounds is a complete round robin: every player faces all three opponents, and the pod is decided on the table instead of on tiebreakers. At six players a full round robin needs five rounds, which is a different event; this mode does not try to serve it.

Round Robin (pairings) and Pick 2 (`picks_per_pack`, a Draftmancer draft setting) stay independent switches, each changeable in Settings on its own. Together they are **the default way to play four**, so the paths below turn both on at once.

The mode is only half the feature. The other half is getting four players to a table at all, which is "How a four-player pod happens" below.

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

## How a four-player pod happens

The case this serves: twelve players show up, eight fire a full pod, four are left over. Today those four have nowhere to go, because a table needs six. Three changes get them playing.

### Second tables open at four

`settings.pod_table_open_threshold` drops from 6 to 4. It is read only by the table cards (`pod_table.py:278` and `:306`), so this is scoped to second and extra tables and does not touch how a first pod fires — that still takes six people expressing interest through the launcher, gated by `pod_draft_min_ready_players`. The one constant does both jobs it needs to do: `offer_second_table` posts the offer once four leftovers exist, and `TableClaimView` materializes the table thread on the fourth distinct claim. The card's gathering line interpolates the threshold, so its copy follows the number with no edit.

A first table is deliberately left alone. Six is the number that makes a pod worth firing when nobody is waiting; four is a rescue for players who are already here and would otherwise go home.

### The stalled-at-four offer

Four claims is not four players drafting. The offer fires on **Draftmancer presence**, the same trigger `_maybe_offer_armed_team_vote` uses, because you can only ready-check bodies that are actually in the lobby.

- **Arm** when the lobby sits at exactly four players and the pod is live, not drafting, has no ready check running, and is not already Round Robin. A mock draft plays no matches, so it is never offered.
- **Never before the pod's own start time.** Until o'clock more players are still expected and a lobby resting at four is ordinary, so asking then would talk a pod out of the table it was going to get. Same gate `_maybe_offer_team_vote_after_start` applies to the team vote. A second table carries a start time of roughly now, so it is eligible straight away, which is the case this serves.
- **Limited to the sets on `pod_format.PICK_2_SETS`** (HOB and MSH today) while the format is being tried out. A set earns its place by drafting well at two picks a pack; a mod can still set Pick 2 by hand on any pod.
- **Wait out a quiet window** on a delayed task that re-validates at fire time, exactly like `_lobby_full_prompt_after_delay`: still exactly four, still nothing else in progress. A fifth player arriving, or one of the four leaving, cancels it. The window is a couple of minutes; the constant belongs next to `_LOBBY_FULL_PROMPT_DELAY_S`.
- **Post one card** in the thread offering the pod a choice between playing now as Pick 2 Round Robin and waiting for more players. It is the Team Draft vote card in a different suit: same shape, same two-sided decision, same "change it in Settings anytime" reassurance. Retire it when a ready check starts, the way the lobby-full nudge retires. Players read the offer as the Pick 2 one, so the button and the column say Pick 2 even though the pairing mode it turns on is Round Robin.
- **Everyone has to agree.** Four of four, not a majority, which gives the card one outcome and no deadline. Wait is not a verdict, it is "not yet": the card stays open, votes stay changeable, and a player who wanted to wait can move to Round Robin once nobody else arrives. This is the one place the design departs from the team vote, where the first side to a majority closes the card either way.
- **On unanimity**, set `pairing_mode` to `roundrobin` and `picks_per_pack` to 2 in one step, pushing the pick count to Draftmancer through the existing `apply_picks_per_pack`, and flip the card to its locked state.
- **The vote target comes from the manager**, which knows the lobby size it offered at, so the card holds voters and copy and nothing else.

### The card is the tally

Voters are stored in their column as mentions, the same way the Team Draft and Format Vote cards do it, so a click reads the current votes straight off the message and the vote survives a restart with no vote table.

An anonymous version was built first and then reverted: seeing who has already committed is what makes the card useful to the people staring at it, and counts alone read as noise. Anonymity would have forced the tally off the message, since Discord's native poll exposes its voters too.

### The ready check stops arguing

`ready_check_needs_confirm` warns below `ready_check_floor()`, which is `pod_draft_min_ready_players` (6). Under `roundrobin` the floor becomes 4, so a four-player pod ready-checks clean. The odd-roster and unrecognized-seat warnings are untouched: four is even, and unlinked seats are still worth stopping for.

## What it touches

- **New** `bot/services/pod_round_robin.py` — pure functions only, mirroring `pod_bracket` / `pod_team`: `supports(roster_size)` and `pair_round(players, round_num)` returning `[(player_a_id, player_b_id), ...]`.
- **New** `bot/services/pod_round_robin_vote.py` — the offer card and its buttons, modelled on `pod_team_vote.py` but rendering counts instead of voter columns, since the tally no longer lives on the message.
- `bot/services/pod_pairing_select.py` — a fifth `PAIRING_MODES` entry. `DEFAULT_PAIRING_MODE` stays `bracket`. The dropdown is shared, so the option appears in the lobby Settings panel, `/draft`, and the scheduled signup card with no further wiring.
- `bot/services/pod_tournament.py` — the roster gate in `start_tournament`, the seat-index persist for this mode, and a pairing dispatch in `advance_to_round` beside the `pod_swiss.pair_round` call. Nothing else: gated rounds mean the report, advance, standings, finalize, and recovery paths are untouched.
- `bot/services/pod_draft_manager.py` — the arm/quiet-window/offer trio beside the team-vote and lobby-full equivalents, the vote tally and click handler, applying the outcome, and the `roundrobin` floor in `ready_check_floor`.
- `bot/config.py` — `pod_table_open_threshold` 6 → 4.
- `bot/commands/testlobby.py` — a preview state that seeds a four-player lobby and runs offer → vote → ready check → pairings end to end, added to `PRODUCTION_SAFE_TESTS` only if it renders without creating a pod.
- `spec/pod-coordination.md` — the pairing line and the four-player path, in the same commit as the behavior.
- Frontend: nothing. No view or component reads `pairing_mode`; the pod page renders whatever match rows exist.

## Decisions to confirm

1. **Gate at exactly 4, or allow any size where a full round robin fits three rounds?** Only 4 fits, so this is really "reject 6 and 8 silently (fall back to Swiss) or refuse the selection at pick time". Recommendation: silent fallback, matching Fast Bracket's existing behavior, since the pod size is not known when the mode is chosen.
2. **Does the offer fire on any pod stalled at four, or only on second and extra tables?** The trigger reads lobby presence, which knows nothing about table index, so table-agnostic is both simpler and correct for a first pod that six people signed up for and four attended. Recommendation: any pod, and accept that in practice it is nearly always a second table.
3. **Label and description** for the dropdown entry, the offer card, and whether the thread says anything when a pod falls back to Swiss for size. Copy gets proposed at implementation time, not here.
4. **Ungated rounds** (post all three at once, every report button live from the start) — worth it only if the round-to-round wait actually bites in play. Defer until a few pods have run.

## Testing

Logic tests for `pod_round_robin.pair_round`: the union of the three rounds is all six pairs, no pair repeats, and every player appears once per round. `supports` table-driven over sizes 2/4/6/8. Vote logic gets tests for the majority threshold, a repeat click moving a vote instead of adding one, and the outcome setting both `pairing_mode` and `picks_per_pack`. The arm-and-quiet-window trigger is branch-tested (fires at exactly four, cancels when a fifth arrives, never fires while drafting or ready-checking) rather than timed.

Everything visible — the offer card, the private vote answers, the clean ready check at four, the round posts — is verified by running a four-player pod on the test server.
