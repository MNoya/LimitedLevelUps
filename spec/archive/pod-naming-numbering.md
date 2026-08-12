# Pod Naming, Numbering, and Card Close

Status: spec agreed with the owner and implemented 2026-07-16. Closes two long-standing pod-draft rough edges: pod numbers that appeared out of chronological order (a completed `#15` sitting above an upcoming `#11`), and RSVP cards that stayed clickable for hours after a pod was over.

The root cause of the numbering half was that a pod's identity and its milestone number were both frozen at card-creation time. This splits them: the Discord name is a stable identity fixed at creation, and the website `#N` is a separate execution-ordered projection computed at read time.

---

## Discord name — identity, fixed at creation

A pod's Discord name is `SET Mon Day Slot Pod`, e.g. `MSH Jul 16 Early Pod`. It is built once when the card is posted and never renumbered or renamed. There is no `#N` in it.

The slot word (Morning / Early / Late) is derived from the pod's time of day off the existing poll buckets (`bot/services/pod_signals.py`): weekdays carry Early and Late, weekends add Morning. An exact-grid pod lands on its own slot; an off-grid `/draft` snaps to the nearest slot by start time, ties resolving to the later slot so a mid-afternoon pod reads Late rather than Early. The single builder is `pod_display_name` in `bot/services/pod_slot.py`, called from `ondemand_event_name_sync` (`bot/services/pod_launch.py`), which every bot-native path shares (daily launcher, weekly scheduled card, `/pod-schedule`, on-demand `/draft`).

Because the name is knowable and final at creation, a scheduled card posted days ahead can never carry an out-of-order number — it carries no number at all.

Overflow tables keep the existing ` - Table N` suffix machinery (`bot/services/pod_drafts.py`): the first table is unsuffixed, the second onward is `- Table 2`, `- Table 3`. Table 1 stays implicit on Discord; there is no rename of the first thread when a sibling fires.

Legacy paths left on the old `#N` naming — the sesh `/create` paste command and format-switch renaming (`renamed_for_format`) — are untouched. They coexist: the website numbers any name by time regardless of what the name says.

## Website `#N` — execution-ordered projection

The milestone number lives only on the website, as a column projected by the `public_pod_draft_events` view, never stored on the row and never parsed from the name.

It is a `ROW_NUMBER()` over pods that have already run — `event_time <= now()` or finalized — partitioned by set, ordered by `event_time`, then `table_index`, then id. Upcoming pods (future `event_time`) get `NULL`: a pod has no number until it has run, which is exactly why an upcoming pod can never show an out-of-order one. Mock drafts are excluded (`kind IS DISTINCT FROM 'mock'`) so practice never consumes a pod number.

The slug stays name-derived (`slugify(name)`) but disambiguates a true duplicate name with an id suffix, since the date+slot name is no longer globally unique the way an embedded `#N` was. Existing unique slugs are unchanged, so old `/pods/<slug>` links keep working.

## Table numbering — each table its own number

Two concurrent tables read as two numbers (`#15` base, `#16` Table 2, `#17` Table 3), not a shared number. This matches how the hub already lists tables as separate rows. The list sorts strictly `#`-descending; because extra tables fire after the base and carry the later `event_time`, they sit above their base in the list. The `table_index` column (parsed from the ` - Table N` in the name) drives only the muted suffix, not the number.

## Rendering

The hub list title reads `#N SLOT POD`: the `#N` green (matching the existing highlight), the slot as the title text, and a muted ` - TABLE N` suffix for the second table onward. Upcoming pods show the slot alone with no number. The date box stays date-only — the day is not repeated in the title.

`PodEventTitle` (`frontend/src/components/pod/EventLabel.tsx`) renders the styled version, backed by `podSlotName` and the plain-string `podEventTitle` in `frontend/src/data/utils.ts` (the string form feeds medallions and aria labels). The mock-draft row keeps its own label. The view exposes `ordinal` and `table_index`; the adapter maps them in `frontend/src/data/realApi.ts`, and mock mode mirrors the same `ROW_NUMBER` + mock-exclusion so dev parity holds.

## RSVP card close — at draft-done

An RSVP card's buttons drop the moment the Draftmancer draft finishes, not the tournament, not on a timer, and not on the next daily launcher.

The trigger is `_on_end_draft` in `bot/services/pod_draft_manager.py`, where the draft is marked `draft_done`. Draft-done is chosen over draft-start because a started draft can still be restarted back into the lobby (`restart_draft` reopens the ready check); closing at start would strand a reopened lobby with no buttons. Draft-done is the first state a restart can no longer revert. The card stays live through lobby fill and the ready check — preserving the late-joiner and drop-replacement grace — and closes only once drafting is genuinely over.

Wiring mirrors the second-table hook to avoid an import cycle: the manager exposes `set_card_close_hook` / `notify_card_close`, and `pod_launch.init_launch` registers `close_event_card`. `event_card_surfaces_sync` resolves a pod's card and thread-controls surfaces; poll/queue pods have no card and no-op.

The daily launcher sweep (`close_past_pod_cards`) remains as the backstop for pods that ran but never reached draft-done — cancelled or no-show pods, or a draft that ended while the bot was down.

## Behavior on existing data

The number is a read-time projection and no existing row is mutated, so on deploy:

- Every existing tournament pod is renumbered chronologically by `event_time`. This mostly matches the old baked numbers and straightens the out-of-order ones; mocks lose their number.
- Slugs are unchanged (names untouched), so existing pod-page URLs keep working. Only new date-named pods get new-style slugs.
- Legacy pods, whose names have no slot word, render as `#N POD DRAFT`; new pods render `#N EARLY POD` etc. History and new pods therefore differ in the descriptive word, and any pod that was out of order changes its number value.
- Multi-table history becomes distinct adjacent numbers with a muted `TABLE N` suffix.
- Numbers are stable as long as pods only append later `event_time`s. A backfill/import that inserts an earlier-dated pod shifts the numbers after it.

Optional consistency follow-up: derive the slot word from `event_time` for legacy pods too, so history also reads Early/Late/Morning instead of the generic "Pod Draft". This adds a second copy of the slot thresholds, so it is deferred rather than shipped.

## Migration

`f3g4h5i6j7k8` (the view projection) chains onto `e1f2a3b4c5d6`. The queue-column migration `a7b8c9d0e1f2` chains above it and does not touch the view. Both are separate revisions by design — distinct concerns, independently reversible, and identical end state whether run as one step or two. Re-applying the view after an edit requires `alembic downgrade e1f2a3b4c5d6` then `upgrade head`, since a plain `downgrade -1` only steps past `a7b8`.
