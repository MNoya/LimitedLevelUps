# Pod lobby size spec — default 8, live bump to 10

## Context

Every pod today opens a Draftmancer room capped at 10 seats. The cap is a single global constant, `pod_draft_max_players: int = 10` (`bot/config.py:49`), pushed to Draftmancer once at ownership claim via `setMaxPlayers` (`bot/services/pod_draft_manager.py:495`). A standard draft pod is 8; the extra two seats are overflow tolerance for hot nights, but they also mean the common case runs a non-standard 9- or 10-person draft instead of a clean pod.

This change makes **8 the default cap** and adds a **live in-lobby control to raise it to 10** (and back), modeled exactly on the pick-timer control: a runtime setting on the live Draftmancer session, nothing persisted and nothing chosen in advance. A host who sees a ninth and tenth player show up bumps the cap in the Settings panel; otherwise the pod stays a clean 8.

Out of scope: a per-pod or per-guild stored size, a size choice at schedule/RSVP time, and (for now) a 6-player option — see [Open questions](#open-questions).

## Status — shipped

Built and committed to `master` (`Default pods to 8 with a live Max Players control`). Uncommitted push is the user's. File map as built:
- `bot/config.py` — `pod_draft_max_players = 8`.
- `bot/services/pod_draft_manager.py` — `self.max_players` per session, `apply_max_players`, module-level `set_event_max_players`.
- `bot/services/pod_settings_view.py` — `_MaxPlayersButton` + `_MaxPlayersSelectView` / `_MaxPlayersSelect`, `max_players_notice`, `MAX_PLAYERS_OPTIONS = (8, 10)`.
- `bot/commands/pod_draft.py` — `on_max_players` wiring + `current_max_players` gating; seeding-preview `seat_cap` reads the live manager.
- `bot/commands/testlobby.py` — `_settings_preview_view` carries the control so `!test` mirrors prod.
- `bot/tests/test_pod_lifecycle.py` — three `apply_max_players` branch tests.

## What the cap is vs what it is not

Three "8"s exist today and only one of them is the ceiling. Keep them separate:

- `pod_draft_max_players` (`config.py`, now 8, was 10) — the **hard Draftmancer ceiling**. The only global this change touches; per-session it becomes `manager.max_players`. Emitted via `setMaxPlayers`.
- `_LOBBY_FULL_THRESHOLD = 8` (`pod_draft_manager.py:99`) — the **startable-pod size** that arms the "Initiate Ready Check?" nudge (`_lobby_pod_full`, line 1518; `_maybe_schedule_lobby_full_prompt`, line 1547). This is *semantically the count at which a pod is worth starting*, independent of the ceiling. **It does not change.** With the default ceiling dropping to 8 it simply coincides with the ceiling; when a host bumps the ceiling to 10 the nudge still fires at 8, which is correct — 8 is a full pod and the last two seats are a bonus, not a requirement.
- `pod_draft_target_players = 8` (`config.py:45`) and `pod_draft_min_ready_players = 6` (`config.py:50`) — underfill-nudge target and ready-check floor. **Neither changes.**

Because the nudge/target/floor constants are already the "startable pod = 8" semantics and are decoupled from the ceiling, dropping the ceiling to 8 needs no threshold refactor. (This decoupling is exactly why a 6-player option is deferred — at a ceiling of 6 the fixed 8 nudge never arms. See [Open questions](#open-questions).)

## Behavior

- New pods open at 8 seats. `setMaxPlayers 8` at session settings time.
- The lobby **Settings** panel gains a **Max Players** control, visible pre-draft only (Draftmancer locks player count once the draft starts, same as the pick timer). It offers 8 and 10.
- The control is a button labelled **Max Players** whose emoji is the mana glyph of the current cap (`:mana8:` / `:mana10:`). Clicking it opens an ephemeral **Table Size** dropdown with **8 Players** and **10 Players** (mana-glyph options), the current value preselected.
- Changing it re-emits `setMaxPlayers` to the live session and posts a public thread notice, identical in shape to the pick-timer change notice (private ephemeral panel, public confirmation in the thread).
- Lowering the cap below the number of players already seated is rejected with an error in the ephemeral, so a 10-seat lobby with 9 present can't be squeezed to 8.
- A live bump is **not persisted**: a pre-draft reconnect re-runs session settings and resets the cap to the default 8. Acceptable by design (the user explicitly does not want DB state). The pick timer has the same non-persistence for on-demand pods; scheduled pods persist the timer via `PodSignal` and re-apply on open, and we are deliberately *not* mirroring that for size.
- All control text is Title Case ("Max Players", "Table Size", "8 Players"), per the Discord options/menus convention.
- **Known limitation:** picking a size deletes the ephemeral dropdown and posts the thread notice, but does not re-render the parent Settings panel, so its button glyph stays stale until the panel is reopened (same behavior as the Kick button, which also doesn't re-render). Reopening the picker reflects the new value.

## Implementation map

Mirror the pick-timer plumbing end to end. Reference implementation: `apply_pick_timer` (`pod_draft_manager.py:605`), `set_event_pick_timer` (line 2174), the `on_timer` wiring (`bot/commands/pod_draft.py:843`), and `_TimerButton`/`_apply_pick_timer`/`timer_notice`/`pick_timer_label` in `bot/services/pod_settings_view.py`.

### 1. `bot/config.py`
- Line 49: `pod_draft_max_players` default `10` → `8`.

### 2. `bot/services/pod_draft_manager.py`
- `__init__` (next to `self.pick_timer = settings.pod_draft_pick_timer`, line 272): add `self.max_players = settings.pod_draft_max_players`.
- `_emit_session_settings` (line 495): emit `self.max_players` instead of `settings.pod_draft_max_players`; update the log line at 505 to read `self.max_players`.
- Add `async def apply_max_players(self, n: int) -> str | None` mirroring `apply_pick_timer`: guard `self.drafting or self.draft_complete` (locked once drafting), guard `not self.sio.connected`, guard `n < len(self.player_session_users())` (can't drop below occupancy), set `self.max_players = n`, `await self.sio.emit("setMaxPlayers", n)` in a try/except, log `[LOBBY] max_players_set`, return error string or `None`.
- Add module-level `async def set_event_max_players(event_id: str, n: int) -> str | None` mirroring `set_event_pick_timer` (line 2174) — resolve the live manager, delegate to `apply_max_players`.

### 3. `bot/services/pod_settings_view.py`
- `PodSettingsView.__init__`: adds `on_max_players: Apply | None` and `current_max_players: int | None`; stores both; adds the control to the button block (`if on_max_players is not None: self.add_item(_MaxPlayersButton(current_max_players, row=3))`); threads both fields through `_render`.
- `_MaxPlayersButton` (a `ui.Button`) labelled "Max Players", emoji `emojis.get_emoji(f"mana{current}")` for the current cap, opens an ephemeral `_MaxPlayersSelectView` / `_MaxPlayersSelect` (placeholder "Table Size", options "8 Players" / "10 Players" from `MAX_PLAYERS_OPTIONS`, mana-glyph emojis, current preselected). A button-plus-ephemeral-select is used, not a fourth in-panel `ui.Select`, because the three existing selects fill rows 0–2 and a fourth select would collide with the button rows; a button shares a row.
- The select callback does **not** go through `view.apply` / `_render` (that would edit the ephemeral into a full panel). It mirrors the Kick flow instead: defer, call `panel.on_max_players`, on error surface it in a followup, else update `panel.current_max_players` in memory, delete the ephemeral, and post the thread notice via `send_settings_notice`. This is why the parent panel button glyph doesn't re-render in place (see Known limitation under Behavior).
- `max_players_notice(actor, n)` via `settings_change_message(actor, "Max players", str(n))`; the change notice keeps sentence-style "Max players" like "Pick timer", the Title Case rule applies only to the menu controls.

### 4. `bot/commands/pod_draft.py` (Settings-view builder)
- `on_max_players(inter, value)` delegates to `set_event_max_players(event_id, int(value))`.
- When a live `manager` exists and `not drafting`, `current_max_players = manager.max_players`.
- Passes `on_max_players=on_max_players if current_max_players is not None else None` and `current_max_players` into `PodSettingsView(...)`, matching the `on_timer` / `current_timer` gating.

### 5. Seeding-preview consumer
- The seeding-preview `seat_cap` (`bot/commands/pod_draft.py`, `pod_seeding`) reads the live manager's `max_players` when one exists for the event, else the config default — so a bumped pod previews 10 seats.

### 6. `!test` preview
- `_settings_preview_view` in `bot/commands/testlobby.py` passes `on_max_players` (no-op) + `current_max_players=8`, so the `!test` Settings panel shows the control and mirrors prod (per the testlobby-mirrors-prod rule).

## Testing

Per repo convention, test logic not framework — no test that Draftmancer honors `setMaxPlayers`, so the tests do **not** assert the `sio` emit. Three `apply_max_players` branch tests in `bot/tests/test_pod_lifecycle.py` against a manager with a stubbed `sio`:
- Pre-draft success sets `self.max_players`.
- Returns an error and leaves `self.max_players` unchanged when `drafting` is set.
- Returns an error and leaves `self.max_players` unchanged when the requested cap is below current occupancy.

Assert state and branch outcome (error vs `None`, `self.max_players`), never the emit or exact copy.

## Deployment notes

- No `!sync` — the control is a button/select inside the existing `PodSettingsView`, not a new or reshaped slash command. `set_event_max_players` is internal.
- No migration — nothing is stored.
- Effective immediately on deploy for pods that open after it. In-flight pods keep the cap they opened with.

## Open questions

- **6-player option.** Deferred. A ceiling of 6 breaks the fixed `_LOBBY_FULL_THRESHOLD = 8` nudge (never arms) and interacts with `pod_draft_min_ready_players = 6` (whole table must ready) and the underfill target of 8 (always "underfilled"). Adding 6 means deriving the full/target/floor from the chosen ceiling instead of leaving them as constants — real work, out of scope here. The `_MaxPlayersButton` select can take a third option later once those are relativized.
- **Scheduled-only vs universal default.** This spec makes 8 the default for *all* pod paths (scheduled, queue, poll) since they share `pod_draft_max_players`. If scheduled should differ from on-demand, that needs a per-path value, which this design does not add.
