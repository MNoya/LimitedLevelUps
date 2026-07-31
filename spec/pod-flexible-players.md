# Flexible players

**Status: not built.** The design for players who sign up for more than one format at the same time slot. Read it before touching the fire path, the pod card roster render, or any count that appears on the launcher, the pod cards or the recruiting messages. The rescue ping in `pod-rescue-ping.md` sits beside this and depends on none of it. Replaces the fire-time partition described in `allocate_fire_roster_sync`.

## Product constraints

These are fixed. The design below is derived from them, not the other way round.

1. A player can sign up for more than one format at one slot, for example MSH and Cube.
2. A player who signs up for one format only does not want the other. They may still be pinged when their own format is definitively dead and the other pod is short, which is the rescue ping and a separate document.
3. A double signup means "I will play either of these, tell me where to go".
4. A pod thread opens at the floor, six players. Six is a playable 3v3 team draft, and an open thread is what lets other players see a quorum forming and join it.
5. Twelve bodies split six for A, four for B and two for either must produce a pod of six and a pod of six. The flexible pair is what makes the second table possible, and they belong in both threads so they can read the real attendance themselves at T-10.

## The unit is the slot, not the pod

A double signup is one statement about a time, not two statements about two formats. Membership, leaving, counting, the T-10 resolution and the T-10 message are therefore all slot-scoped. The two pods keep their own identities, threads, cards and rosters; only membership moves up a level.

**Nothing is ever deleted.** Today the fire path deletes a flexible player's sibling rows to settle where they play. Under constraint 5 they belong to both pods until they physically sit down in a Draftmancer lobby, so no code writes a resolution at all.

## Two counts, everywhere

Every surface that prints a number has to print two, because the same body is counted by two pods at once and eleven humans must never render as two pods of six.

- **committed(P)**: players signed up for P and no sibling at that slot.
- **flexible(slot)**: players signed up for two or more formats at that slot.

Both numbers appear on the launcher column, the pod card, the recruiting status message and the T-1h reminder. Flexible names carry the ◈ marker the launcher roster already uses, so the marker means one thing in both places.

**Open question:** whether the headline count is `committed + flexible` with the flexible part named, or `committed` alone with the flexible players visible only as ◈ names in the roster. The first is complete and asks the reader to do arithmetic across two messages in pod chat; the second is quieter and makes a pod that will comfortably seat six read as four. To be decided from a render, not from a description.

## Firing: the slot decides

Firing stops being a property of a pod and becomes a property of a slot. Every membership change at a slot runs one function over the whole slot, which answers: given who is committed where and who is flexible, which pods should exist?

```
floor      = pod_signal_fire_threshold
need(P)    = max(0, floor - committed(P))
reserved(S)= max(0, floor - committed(S))     for each already-fired sibling S
available  = flexible(slot) - Σ reserved(S)
```

A candidate pod fires when `need(P) <= available`. When several candidates cannot all fire, prefer the one with more committed players, then the day's format order, so the answer is deterministic.

**Monotonic.** The function only ever adds pods. A pod that exists is never un-fired, whatever the numbers do afterwards: its thread is full of people. A pod left short is rallied by the recruiting beats like any other.

**Order-independence and its limit.** Before the first pod at a slot opens, the outcome does not depend on click order. After that, a fired pod holds its reservation forever, so a later configuration that would have been better is not reachable. This is inherent to constraint 4 wanting threads early and is accepted.

### Worked cases

| committed A | committed B | flexible | result |
|---|---|---|---|
| 6 | 4 | 2 | Both fire. A on its own six, B at 4+2. Constraint 5. |
| 5 | 5 | 2 | Both fire at six. Neither could alone. |
| 5 | 4 | 2 | Only A fires, at seven. B needs two, one is reserved to A, so it cannot reach six. A wins on committed count regardless of click order. |
| 3 | 3 | 2 | Neither fires. Eight bodies, no configuration reaches six. |

## What each player hears

| Beat | Committed player | Flexible player |
|---|---|---|
| Signup | Confirmation naming their pod | Confirmation naming both pods, saying they play one of them and will choose |
| Pod opens | Added to their thread | Added to **both** threads |
| T-1h reminder | One reminder | **Two**, one per thread, each naming the sibling pod and its counts |
| T-10 lobby open | DM with their link | **One** DM covering the slot: both links, recommended pod first |

The rule underneath: **duplication is fine while it is informational and must collapse when it is an instruction.** Two roster reminders at T-1h are the mechanism by which a flexible player compares the pods. Two ready-check DMs carrying two different Draftmancer links, arriving together, is the failure this rule exists to prevent.

Copy for all of these lives in `pod_launcher_copy.py` and `pod_reminder_copy.py`. This document does not carry it.

## T-10 is the resolution

Both pods open their lobbies on the same lead, so at T-10 both Draftmancer sessions exist and the bot is in both. The recommendation is computed off **seated players**, not off Yes and Maybe, because seating yourself is the only signal that is not free.

- Computed for every flexible player at the slot together, walking them in join order and decrementing each pod's gap as one is placed. Done per player independently, two flexible players are both sent to the same short pod and the other stays short.
- Sent as one DM per player: both pods named, both links, the recommended one first, and no promise that the recommended lobby is already open, since the other pod's opening may be what triggered the message.
- Live afterwards. The thread can keep showing the split as people seat themselves.
- **Nothing is recorded.** The player joins a lobby, Draftmancer has them, and that is the resolution. No resolved-format column, no state to reconcile if they move at T-3.

A per-slot claim stops the second lobby opening from sending a second DM, the same shape as `last_call_pinged_at`.

## Out of scope

- **Merging two short pods at T-10.** If real attendance is five and five, both play short. Accepted. Nothing here binds a roster before Draftmancer, so a future merge stays possible.
- **The rescue ping.** `pod-rescue-ping.md`.
- **Second tables.** Over-signups past the aim keep their current behavior.

## What this deletes

- `allocate_fire_roster_sync` and `_released_to_siblings`: the fire-time partition.
- `sibling_fire_candidates_sync`: the pass that re-checked siblings after a partition released bodies. The slot function subsumes it.
- Every test asserting that firing removes a shared player from the sibling roster.
