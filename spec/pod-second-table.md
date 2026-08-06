# Second-table auto-offer

## Goal

When a scheduled pod fills and its draft fires, the players who signed up but didn't make the table of 8 shouldn't have to notice, re-count, and reorganize by hand. The bot already knows the 8 who got seated; it subtracts them from the pod's Yes/Maybe roster and offers the leftovers a ready-to-claim Table 2, so a second pod self-organizes off the same signup with no mod intervention.

This sits on top of `/pod-table` (`bot/commands/pod_table.py`), which already clones a pod into "Table N", posts a claim card with a 🪑 button and a threshold, and on materialize spins up the thread, Draftmancer lobby, and manager. The new work is a trigger and a leftover computation; the claim card, materialize flow, and lobby handoff are reused unchanged.

## When the offer happens

Fire once, when pod 1's draft actually starts — the moment the Draftmancer session locks its 8 in (the manager's draft-start path). Earlier moments are too fluid: people drift in and out of the lobby right up until the draft begins, so the "specific set of 8" isn't real until then.

Three gates, all of which must hold, or the pod says nothing at all. No consolation message, no "not enough for a second table" line.

**A roster to draw from.** Only pods born from a scheduled RSVP card qualify. Queue- and poll-born pods carry no standing roster, so there is nobody to invite.

**No table already.** A `/pod-table` card still collecting seats is this pod's table; leave it alone rather than posting a second card that splits the claims between them. A table that already fired is likewise the table. The offer exists to open the table nobody opened.

A cloned table carries no link back to its source in the database, so a fired table is known from the source pod's manager, which holds the ids of the tables opened off it and lives exactly as long as the draft-start hook that reads them. A restart between the two loses that, which is the accepted gap: the manager is gone by then anyway.

**Enough free leftovers.** See below.

## Leftover computation

The source of truth is the pod's signal roster — everyone who RSVP'd Yes or Maybe. Subtract the locked 8, Yes ahead of Maybe. Then subtract everyone already spoken for by another pod: seated in another live manager's Draftmancer lobby, claimed onto a table that has fired, or holding a seat on another join card still gathering. Only the players are subtracted, never the whole offer — a busy pod next door does not stop a genuinely free group of six getting a table of their own.

Matching the locked 8 back to roster members: prefer the linked Discord member id where a seat was linked (manager `link_seat`), and fall back to casefolded name matching (arena/display). Name-only matching is the fuzzy edge; a missed match just means someone appears on both the seated table and the leftover list, which the claim card already tolerates (a duplicate click is a no-op).

## Offer

Auto-post a Table 2 claim card in the pod's parent channel — beside Table 1, the placement `/pod-table` resolves to today — pinging the leftovers. This reuses `build_table_view` → `TableClaimView` → `materialize_table` wholesale: threshold reached → clone the source pod → new thread + Draftmancer lobby → ordinary tournament manager.

The bar is `pod_table_open_threshold`, the same count a table needs to materialize, so the card's stated open-count and the trigger line up. Below it, stay quiet and let the multi-pod notice on the RSVP card (`MULTIPOD_NOTICE`) carry the invitation on its own.

## Confirm — invited, not drafted

Leftovers are invited, not auto-seated. The card pings them and shows them as invited, but each must click 🪑 to take a seat. They RSVP'd Yes once already, but a fresh click confirms they're still around, so the second table never materializes on ghosts who logged off after the first pod filled. This is deliberately *not* the `preseeded_claims` path on `TableClaimView`, which pre-counts a claim toward the threshold — that is the opt-out model we rejected.

## Thread membership

Once the table materializes, the source pod's whole Yes and Maybe roster is added to the new thread, not only the players who claimed a seat. A table is the other half of a signup those players already answered, and coordination happens in the thread, so nobody should have to hunt for it. Claimers arrive by the mention block; the rest are added silently through `add_members_to_thread`, which asks nothing of a member seated at another table and costs a nonparticipant one dormant thread.

## Command access

`/pod-table` opens to everyone: drop the owner-only gate in `bot/commands/pod_table.py`. This matches the multi-pod notice, which already tells any player to run the command, and makes the auto-offer a convenience layer on top of a command players can fire themselves.

## Open items

- **Invited-list display.** Showing invited-but-unclaimed names on the card, distinct from claimed seats, needs a small `TableClaimView` extension. The minimum viable version pings the leftovers and shows claims as they accumulate, without a separate invited column.
- **Third pod.** A Table 3 is now the mod's call: the no-table-already gate silences the automatic offer for the rest of the pod's life, and `/pod-table` opens the next one by hand. Automating it would mean the gate counting tables instead of checking for any, and the leftover cut already reports the genuinely free part of the roster, so the pieces are there if it ever proves worth it.
- **Signal linkage.** A Table N event is cloned via `record_table_event` and isn't tied back to the originating signal, so multi-table leftover math collects seated sets from the live managers rather than from a stored link. A table's claimers are recorded on its manager at materialize, which covers the window between a table firing and its players reaching Draftmancer.
