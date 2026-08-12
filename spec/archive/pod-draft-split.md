# Pod Draft split — overflow Table 2

## Problem

A scheduled pod draft is one `PodDraftEvent`: one Draftmancer session (`setMaxPlayers = 10`), one thread, one flat roster. On busy nights more players show up than one pod can seat. Draftmancer fills FIFO, so late arrivals are stuck outside a full lobby and the room resorts to "someone drop so another can get in". There is no smooth way to open a second pod for the overflow.

`/pod-split` opens that second pod ("Table 2") on demand, with no Sesh RSVP. It reuses the entire existing pod lifecycle — a second `PodDraftEvent` already gets its own manager, socket, thread, tournament, standings, championship, and trophies for free, because managers are keyed by `event_id` (`bot/services/pod_active.py`), not by "the one pod".

## Scope decisions (settled)

- **Overflow relief, not rebalancing.** Table 1 keeps running as-is. `/pod-split` gives the leftover players their own pod. The bot does not try to balance Attendee lists across tables — players move themselves.
- **Draftmancer lobby is the roster.** Claims in Discord are a coordination layer to open Table 2 and pull people into its thread; the drafting roster is still whoever is linked in Table 2's Draftmancer session at draft start, exactly as today.
- **No DB link between tables.** Table 2 is a fully independent event, related to Table 1 only by name (`"<source name> Table 2"`). No parent FK, no shared group key.
- **Trophies as normal.** Two tables on one night means two independent pods and two pod winners. No special leaderboard handling.
- **Bot imposes no parity or min-size rule.** Even seating and the 6-player floor are the organizer's call. The only bot-chosen number is the materialize threshold (4 claims). Drafting still fires through the existing ready check.
- **Bot owner only, for now.**

## User flow

1. Bot owner runs `/pod-split`, either inside the source pod thread (source event inferred from `discord_thread_id`) or in `pod-draft-coordination` with an `event` param (autocomplete over recent events, mirroring `/pod-standings` at `bot/commands/pod_draft.py:378-424`).
2. Bot posts a **claim message** in the channel/thread where the command ran (the source thread by default, where the overflow players already are). It carries a "Join Table 2" button and a live count. Copy makes clear this is for players who did **not** get a Table 1 seat.
3. Players click to claim. Clicking again un-claims. Nothing heavy exists yet — just an in-memory list of `(user_id, display_name)` on the view.
4. At **4 claims**, Table 2 **materializes**:
   - Clone the source event's `set_code`, `set_id`, `format_label`, `event_date`, `seating_mode`, `pairing_mode`; `event_time = now`; `kind = "tournament"`; `name = "<source name> Table N"`.
   - Post a lobby message and open a thread off it in the source thread's parent channel (same pattern as `mock_draft.py:99-107`).
   - `start_manager(..., kind="tournament")`.
   - Ping the claimers in the thread's opening message — the mention pulls them into the thread — and post the Draftmancer link.
5. The claim button keeps taking claims after materialize; each new claim pings that player into the Table 2 thread. Count displays toward a soft cap of 8 (goal), but the button does not hard-block — the real ceiling is the Draftmancer session cap of 10.
6. Organizer starts Table 2's draft with the normal ready check (`/pod-ready`, floor 6, or manual override `MANUAL_READY_MIN_PLAYERS = 2`). From `startDraft` on, Table 2 is an ordinary pod: seating, bracket-or-swiss, reporting, standings, championship, trophies — all unchanged.

## Table numbering

Events are unrelated in the DB, so the table index is derived from the name. Given a source event whose display name is `base` (strip any trailing `Table N`), scan existing `PodDraftEvent.name` for `"{base} Table %"`, take the max N seen, and use N+1 (starting at 2). This lets a third `/pod-split` from Table 1 (or from Table 2) open Table 3. Mirror the same suffix into the Draftmancer session id via a `-Table{N}` segment so lobby URLs stay distinct (see `_build_draftmancer_session` / `build_mock_session` collision handling at `bot/services/pod_drafts.py:79-112,371-381`).

## New code

### Command — `bot/commands/pod_split.py`

New cog `/pod-split` (name pending; alternatives: `/pod-table`, `/pod-open-table`). Owner-gated via the existing `_is_owner_or_admin` style check. Resolves the source event, then posts the claim view. Structurally a sibling of `mock_draft.py`.

### Claim view — `Table2ClaimView`

- Single "Join Table 2" button, persistent enough to survive the short gather window; claimers held in memory on the view.
- Toggle semantics: click to claim, click again to release.
- Below-threshold: edits the claim message count only.
- On reaching the threshold: calls the materialize routine once (guard against double-fire), then flips to post-materialize mode (subsequent claims ping into the existing thread).
- Idempotency: if a Table 2 for this source already exists or is mid-gather, `/pod-split` points at it instead of opening a second.

### Event creation — `record_split_event` in `bot/services/pod_drafts.py`

Mirror `record_mock_event` (`bot/services/pod_drafts.py:384-406`) but `kind="tournament"`, fields cloned from the source event, `name` with the computed `Table N` suffix, `pairing_mode`/`seating_mode` copied from source. Placed next to `record_mock_event`.

### Config — `bot/config.py`

Add `pod_split_open_threshold = 4` (claims needed to materialize). Reuse `pod_draft_target_players = 8` for the soft-cap display and `pod_draft_min_ready_players = 6` for the ready check. No comment on the field (house style).

## What is reused unchanged

- `start_manager` / manager lifecycle (`bot/services/pod_draft_manager.py:1624-1666`) — second event, second manager, no changes.
- Thread + lobby message creation pattern (`mock_draft.py:99-113`).
- Ready check, seating, bracket/swiss selection (bracket at 8, auto-fallback to Swiss otherwise at `pod_tournament.py:840-841`), reporting, standings, championship, trophy scoring.
- `draftmancer_url_for`, session-id collision suffixing.

## Edge cases

- **Source event not found** (thread with no pod event, or bad `event` param) → ephemeral error.
- **Fewer than 4 ever claim** → nothing materializes; in-memory state is discarded, no cleanup. Owner can re-run later.
- **Bot restart before materialize** → in-memory claims are lost; owner re-runs `/pod-split`. Accepted limitation for v1 given owner-fired and a short window. After materialize, Table 2 is a normal event and rehydrates like any pod (`rehydrate_active_lobbies`).
- **Odd or sub-6 roster at draft time** → not blocked by the split flow; hits the existing tournament guards (Swiss rejects odd rosters, `POD_ROSTER_ODD_MSG`) exactly as a normal pod would.
- **Draftmancer cap** → Table 2 is its own session capped at 10; a fourth pod is just another `/pod-split`.

## Manual verification — `!test split`

The primary test is driving the real flow on Discord without faking a full roster. `!test split` (owner-only, local DB only) seeds a stand-in source pod, then posts the **production** claim card via the same `build_split_view` the slash command calls, preseeded to one below threshold. The invoker's single click crosses the threshold and runs the real `materialize_table2`: a real thread is created, the Draftmancer lobby opens, the manager connects, and the ordinary tournament path takes over. Fixtures own only the seeded source event and the preseeded claimers — every user-facing surface is prod code.

No drift is enforced structurally:
- The claim card, `materialize_table2`, and `build_split_view` live in `bot/commands/pod_split.py`; `!test split` imports and calls them, it does not reimplement them.
- The lobby-open body is one shared `build_lobby_open_body` in `bot/commands/messages.py`, called by both `fire_reminder` (the sesh path) and `materialize_table2` (the split path), so lobby copy stays in lockstep.

### Unit coverage (logic only, per repo conventions)

- Table numbering: `Table N` derivation from sibling event names, including a third split producing `Table 3` and splitting from an already-split table.
- `record_split_event` clones the intended source fields and sets `kind="tournament"`, `sesh_message_id=None`, `-T{N}` session id.

No tests for thread/lobby creation, the claim view, or manager socket behavior (verified by `!test split`, per `feedback_test_logic_not_integrity` and `feedback_no_tests_admin_commands`).

## Open naming decision

`/pod-split` is a placeholder. Decide the final command name before `!sync`.
