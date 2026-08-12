# Daily Pod Launcher — surface off-grid /draft pods as custom entries

## Context

The Daily Pod Launcher (`bot/tasks/pod_daily_poll.py` + `bot/services/pod_launch.py`) shows the day's fixed time slots (weekday Early/Late, weekend Morning/Early/Late) and reflects any locked scheduled pod that sits exactly on a slot's time. A `/draft` pod scheduled at an off-grid time (any time that is not a fixed slot, e.g. 7:30 PM) matches no slot, so today it appears nowhere on the launcher — it lives only as its own standalone RSVP card in the channel. Players watching the launcher never see it.

The goal: surface each off-grid `/draft` pod as its own extra committed entry on the launcher, alongside the fixed slots, with its own Yes/No toggle and roster. It must read as a custom one-off, and it must never merge into or displace a fixed slot's reflection.

Read `spec/pod-workflow.md` for the pod-draft lifecycle (daily poll, RSVP, format preference, nudges, launch) before implementing this.

## Current behavior (why off-grid pods drop off)

- `launcher_snapshot_sync(message_id, signal_date)` (`bot/services/pod_launch.py`) iterates only the day's fixed buckets from `pod_signals.poll_buckets_for(signal_date)`. For each bucket it computes the slot instant via `slot_event_time(signal_date, bucket.key)` and asks `_event_id_for_slot(session, slot_time)` for a locked pod at that exact instant.
- `_event_id_for_slot` matches the newest `PodDraftEvent` whose scheduled-card `PodSignal` (`kind == KIND_SCHEDULED`) has `slot_time == slot_time` — an exact equality join. An off-grid pod carries its own `slot_time` (its arbitrary start), which equals no bucket instant, so it is never returned and never reflected. This is deliberate today ("lives as its own card and is never swallowed into a launcher slot").
- Everything downstream is keyed by `bucket_key`: the embed field builder in `build_poll_embed` and the button view `PodPollView` both call `bucket_by_key(slot.bucket_key)` and `continue` when it returns `None`; the toggle custom_ids are `pod_poll:{bucket_key}` and `pod_slot_rsvp:{bucket_key}`. There is no notion of a slot keyed by pod id.

An off-grid scheduled pod is a `KIND_SCHEDULED` `PodSignal` (bucket `SCHEDULED_BUCKET`) with `signal_date == today` and a `slot_time` matching no fixed bucket. Created via `/draft` → `_schedule_pod` → `post_scheduled_card` → `create_scheduled_signal_sync`, which stores `slot_time = event_time` verbatim.

## Locked design decisions

- **Label**: each off-grid entry reads as `emoji + format + time` — a dedicated custom-pod emoji (a module constant, distinct from the bucket emoji so it never reads like a fixed slot), the format label (`"Latest Set"` when the pod's `set_code` is the active set, else the flashback set code via `format_display(set_code)`), and the `<t:…:t>` start time. No role mention (off-grid pods ping nobody by design — see `slot_role_name_for_event_time`).
- **Ordering**: chronological. After appending off-grid entries, sort all launcher slots by `slot_time` so the board reads top-to-bottom in clock order. Fixed slots stay in their existing relative order (already chronological); an off-grid entry sits between the fixed slots by time. This never displaces a fixed slot's own reflection — off-grid entries are separate `LauncherSlot`s keyed by `event_id`.

## Implementation

### 1. Data layer — `bot/services/pod_launch.py`

- **Extend `LauncherSlot`**: add `event_id: str | None = None` and `custom: bool = False`. A custom slot is a committed off-grid pod; its `event_id` keys the Yes/No toggle instead of a bucket. Update the dataclass docstring to describe the custom variant.
- **`_committed_slot(session, bucket_key, event_id, *, custom=False)`**: populate `event_id=event_id` (harmless for fixed slots) and `custom=custom` on the returned `LauncherSlot`. Existing positional callers stay valid.
- **New `_offgrid_event_ids(session, signal_date) -> list[str]`**: the day's off-grid scheduled pods, newest-wins per distinct off-grid time (reuse `_event_id_for_slot` per off-grid `slot_time` so the newest-wins and no-second-table semantics match the fixed-slot reflection exactly). Compute the excluded set as `{slot_event_time(signal_date, b.key) for b in poll_buckets_for(signal_date)}`; select distinct `PodSignal.slot_time` for `KIND_SCHEDULED` signals on `signal_date` that are not in that set; for each, resolve `_event_id_for_slot` and dedupe by event id. Datetime set membership compares by instant, so a SCHEDULE_TZ bucket time and a UTC-stored slot time match correctly; a fixed-slot (or postponed) pod's slot time equals a bucket instant and is excluded here — it still reflects into its fixed slot.
- **New `_offgrid_slots(session, signal_date) -> list[LauncherSlot]`**: `[_committed_slot(session, SCHEDULED_BUCKET, eid, custom=True) for eid in _offgrid_event_ids(...)]`.
- **`launcher_snapshot_sync`**: after the fixed-bucket loop (inside the `with SessionLocal()` block), `slots.extend(_offgrid_slots(session, signal_date))`; then sort the full list by `slot_time` (guard `None` with a late sentinel, though all paths set `slot_time`).
- **Toggle ref by event**: factor a session-taking `_committed_rsvp_ref(session, event_id, discord_user_id) -> (card_message_id, current_rsvp) | None` and have both the existing `committed_slot_rsvp_ref_sync` (resolves event id from `slot_event_time` + `_event_id_for_slot`) and a new `committed_slot_rsvp_ref_by_event_sync(event_id, discord_user_id)` call it. Refactors the current duplication.
- **`_launcher_day_signal_ids`**: also include each off-grid pod's scheduled signal id (from `_offgrid_event_ids`), so a saved Format Preference propagates to off-grid rosters the launcher shows, consistent with reflected fixed slots.

### 2. Rendering + view — `bot/tasks/pod_daily_poll.py`

- **Header**: extract a `_slot_header(slot, guild, closed)` from `build_poll_embed`. For `slot.custom`, build `emoji + label + time + count + ✅` with the custom emoji constant and `_custom_slot_label(slot)` (returns `INTEREST_LABEL[LATEST]` when `slot.set_code == active_set_code()`, else `format_display(slot.set_code)`). For fixed slots keep the current bucket path (returns `None` to skip when `bucket_by_key` is `None`). The roster/body block (`_roster_lines`, thread link, `-`/`MARKER_CLOSED`) is unchanged and shared. Add a module-level `CUSTOM_SLOT_EMOJI` constant (a plain unicode emoji; candidate 🎲).
- **`PodPollView`**: in the slots loop, when `slot.custom` add an `OffGridSlotRsvpButton(slot.event_id, label=_custom_slot_label(slot))` (fall back to a thread link button if a card is somehow absent), then `continue`. The no-slots startup path is unchanged (fixed bucket buttons + interest button); off-grid dispatch after restart comes from the dynamic-item registration, not from this path.
- **New `OffGridSlotRsvpButton`** (a `discord.ui.DynamicItem[discord.ui.Button]`, template `pod_slot_rsvp_event:(?P<event_id>.+)`, near `_slot_rsvp_button`): mirrors `JoinDraftButton`/`FormatPollButton`. The event id rides the custom_id so one registration dispatches every custom entry and the button survives restart. `from_custom_id` reconstructs from the event id alone (label irrelevant to dispatch; emoji constant satisfies the button-needs-label-or-emoji rule).
- **New handler `_handle_offgrid_rsvp_click(interaction, event_id)`**: mirror `_handle_slot_rsvp_click` but resolve the card via `committed_slot_rsvp_ref_by_event_sync(event_id, user_id)`; toggle Yes↔No; `apply_card_rsvp(interaction, card_message_id, target, refresh_launcher=False)`; then re-render the launcher. Extract the shared re-render tail (fetch guild → `launcher_snapshot_sync` → `message.edit(embed, view)`) into a helper used by both this and `_handle_slot_rsvp_click`.

### 3. Persistence — `bot/main.py`

- Import `OffGridSlotRsvpButton` from `bot.tasks.pod_daily_poll` and register `bot.add_dynamic_items(OffGridSlotRsvpButton)` alongside the other dynamic items, so clicks on off-grid toggles dispatch after a restart before any re-render.

### Refresh path (already works)

A direct RSVP on an off-grid pod's own card calls `apply_card_rsvp` → `_refresh_launcher(slot_time)` → `refresh_launcher_for_date(slot_time.date())` → `_rerender_poll`, which rebuilds via `launcher_snapshot_sync`. Once the snapshot includes off-grid entries, a card-side RSVP updates the launcher entry with no extra wiring.

## Edge cases

- **Off-grid ≠ displacement**: a fixed-slot pod's `slot_time` equals a bucket instant, so it is excluded from `_offgrid_event_ids` and still reflects into its fixed slot; the off-grid entry is a separate `LauncherSlot` keyed by `event_id`.
- **Split second tables** carry no scheduled-card signal, so they are not picked up as off-grid entries (matches `_event_id_for_slot`).
- **Two pods at the same off-grid time**: newest-wins per distinct time (via `_event_id_for_slot`), avoiding test-run stacking; genuine distinct off-grid times each get their own entry.
- **Component cap**: a Discord view holds 25 components / 5 per row. Fixed buttons + interest button leave headroom for a handful of off-grid toggles (realistic daily volume). If off-grid entries could ever exceed the cap, bound them and `log()` what was dropped rather than silently truncating.
- **Closed board**: off-grid entries render in the closed (greyed, no-buttons) state the same as committed slots.
- **Interest picker Confirm buttons**: off-grid entries are committed, so they are excluded from `open_slots` in `_send_interest_prompt` (which filters non-committed with a valid bucket) — no change needed.

## Verification

- Unit tests in `bot/tests/test_pod_rsvp.py` next to the existing reflection tests, reusing the `_pod_event` / `_scheduled_pod` fixtures (add a variant that takes distinct card message ids and an explicit signal date, since `(message_id, bucket)` is unique). Test with the fixture `session` against the session-taking `_offgrid_slots` / `_event_id_for_slot` (not the `_sync` wrappers, which open their own `SessionLocal`). Names from the `HALL_OF_FAME` tuple. Cover:
  - an off-grid scheduled pod surfaces as one `custom`, `committed` `LauncherSlot` carrying its event id and Yes roster;
  - an off-grid pod does not displace a fixed slot's reflection — the fixed slot still reflects its own pod (`_event_id_for_slot(fixed_time)` unchanged) and the off-grid entry appears separately;
  - `_offgrid_slots` returns entries sorted by time;
  - no copy assertions (per project convention — visual check is the copy test).
- Manual: run the bot locally (`dchord-bot watch`), `!test poll` to post a launcher, `/draft` a pod at an off-grid time on the same day, confirm it appears as a custom entry with a working Yes/No toggle and roster, that toggling from the launcher and from the card stay in sync, and that the fixed slots are unchanged. Restart the bot and confirm the off-grid toggle still dispatches.
- `.venv/bin/pytest bot/tests/test_pod_rsvp.py`.
