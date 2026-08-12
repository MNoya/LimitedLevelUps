# Roster on committed launcher slots

## Problem

The Daily Pod Launcher shows the Yes roster only while a slot is **lazy** (still gathering signups). The moment a slot commits — a lazy pod graduates to a thread, or a scheduled/sesh pod is reflected — the slot collapses to a jump-link and the names disappear (`_committed_slot` returns `names=[]`, and the committed render path shows only `<#thread>`). A player looking at the launcher after graduation can no longer see who is in the pod without opening the thread.

We want the Yes roster to stay visible on a committed slot, kept current as people RSVP on the scheduled card.

## Key insight: this is a projection, not a sync

Once a slot commits, `PodPollView` replaces the slot's toggle button with a **link button** to the thread. The launcher stops accepting RSVP writes entirely — the only writable surfaces are the scheduled card and (until phase-out) sesh. So there is exactly one source of truth for a committed slot's roster: the `PodSignalMember` `RSVP_YES` rows behind the scheduled signal (bot-native pods) or the sesh embed (sesh pods).

That means the feature is a **one-directional, read-only projection** of the card onto the launcher — not a two-way sync. There is no dual-write and therefore no race: the `set_rsvp` DB transaction already serialises concurrent clicks, and the launcher only reads the committed state at render time.

## Design

1. **Populate names.** `_committed_slot` (`bot/services/pod_launch.py`) already loads the RSVP roster to compute the Yes count. Feed the same `RSVP_YES` list into `LauncherSlot.names` instead of leaving it empty.

2. **Render.** The committed-slot body (`build_poll_embed` in `bot/tasks/pod_daily_poll.py`) keeps its header (slot emoji, time, count, ✅) and the jump-link, and lists the roster below it, reusing the existing `> {member}` line format the lazy path uses.

3. **Freshness.** Re-render the launcher when the scheduled card's Yes roster changes, so the committed slot tracks late Yes/No churn:
   - `launcher_message_id_for_date_sync` resolves the day's launcher message from any poll-bucket signal for that date; `refresh_launcher_for_date` rebuilds the embed through the existing `_rerender_poll` and no-ops when no launcher was posted.
   - `_handle_rsvp` (`bot/commands/pod_rsvp.py`) calls it after a card RSVP, keyed off the card's slot date. The daily-poll task registers its refresh through `register_launcher_refresh` in `pod_rsvp` so `pod_rsvp` never imports the task module and cycles back.
   - The edit fires only when Yes membership actually changed. `set_rsvp` returns `yes_changed` (the clicking member's Yes state flipped), so a fresh Maybe/No, a Maybe↔No move, or removing a Maybe/No costs no Discord call — the committed slot projects Yes only, so nothing visible changed.

4. **Concurrency.** None needed beyond what exists. The launcher edit is a projection of committed DB state; no locking, no debounce.

## Sesh

Sesh pods have no `PodSignalMember` roster — their roster lives in the sesh embed, which would need an async `fetch_sesh_rsvps` call inside the otherwise-sync snapshot. Sesh committed slots stay **link-only**: `_committed_slot` finds no scheduled signal for a sesh event, so `names` resolves empty on its own with no special-casing. This caveat disappears once sesh is retired — every committed slot is then bot-native and carries an `RSVP_YES` roster.

## Decisions (resolved)

- **Yes only.** The committed slot projects the Yes roster, matching the lazy slot's signup-list semantics. Maybe/No never appear.
- **No truncation cap.** The full roster renders; the three-slot weekend layout holds a capacity roster without wrapping badly, confirmed against the live preview, so no line cap was added. Revisit if multi-pod overflow ever pushes a single slot well past capacity.

## Cost

One launcher message edit per card RSVP that changes Yes membership; Maybe/No churn that leaves the Yes set untouched edits nothing. Negligible at pod scale, no rate concern.

## Previewing

`!test launcher` stages a real committed pod, seeds a Yes roster on it through the production RSVP path, and posts the live launcher — the committed-slot roster renders exactly as production does, so the preview can't drift.
