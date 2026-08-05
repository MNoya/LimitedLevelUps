# Pod Draft — Phase 1 Implementation Notes

Working doc for the `pod-draft-phase-1` branch. Read this together with `spec/pod-draft-spec-phase1.md` (the original brainstorm) — this file captures where the implementation diverged.

Branch is local-only and **not pushed to master**. All commit timestamps have been backdated to evening hours.

## Status at last checkpoint (commit `2bcbbe8`)

| Milestone | Status |
|---|---|
| 1 — Migration + models | ✅ |
| 2 — pod_drafts service layer | ✅ |
| 3 — sesh embed listener + parser | ✅ |
| 4 — PodDraftManager + T-5 reminder | ✅ |
| 5 — Ready check + /ready + auto-ready | ✅ |
| 6 — Bracket lifecycle + champion finalization | ✅ (rewritten as Python Swiss) |
| 7 — Read + admin commands + guest linking | ⏳ pending |
| 8 — Test suite (parser, bracket, scoring, linking) | partial (parser + swiss done) |

200 tests passing.

## Key divergences from the spec

### Bracket is Python Swiss, not Draftmancer's generateBracket

The spec assumed matches would be played inside Draftmancer (it has its own bracket UI). Reality: matches happen on MTG Arena, players just report results in Discord. We removed the entire `generateBracket('Swiss')` + `sessionOptions` diff pipeline and replaced it with:

- `bot/services/pod_swiss.py` — pure pairer + standings (no DB, no Discord). Tiebreakers follow MTR §1.6 (OMW% → GW% → OGW% → name), with the 1/3 floor.
- `bot/services/pod_tournament.py` — drives the post-draft Discord flow: one green embed per round listing all pairings, with N Discord Select dropdowns underneath (up to 5 → supports 10-player pods). Players submit results from the dropdown; the embed updates in place.

Result submission is **trust-based**: anyone can pick any result; results are editable (re-pick = overwrite). `/pod-result-edit` (admin) is still planned for correcting committed results post-round-advance.

### Identity matching — `Player.arena_name` (planned, milestone 7)

Same sesh URL is shared across all attendees (intentional — Yes/Maybe isn't a hard roster). Users are expected to type their full MTGA handle (`Name#12345`) in Draftmancer so others can send friend invites — matching has to handle the `#NNNN` suffix.

- Add `arena_name` column to `players` (stores full handle, `Name#12345`).
- Normalize for comparison: strip `#\d+` suffix and lowercase both sides before equality check. `"Noya#12345"` → `"noya"` matches `Player.display_name = "Noya"`.
- Match priority: exact `lower(arena_name)` → normalized `display_name` → normalized `discord_username`. Only the arena_name leg requires the user to have set it explicitly.
- `/pod-link-arena <Name#12345>` — opt-in fallback for users whose Draftmancer name diverges from any Discord name (e.g. `MartinTheGreat#123456`). Sets `Player.arena_name` and backfills past unlinked participations.
- Live lobby verification: on every `sessionUsers` update, refresh the pod-draft thread embed showing which Draftmancer names are linked vs unlinked. Ready check is gated on full verification — bot prompts unlinked users to run `/pod-link-arena` before the draft can start.
- Standings post renders each linked participant as `[Name](dischord.pages.dev/leaderboard/<slug>)` markdown.

### `/pod-takeover` (mutiny, not in original spec)

Ported from Amelas/DraftBot. Transfers Draftmancer session ownership to the invoker and disconnects the bot. **Refuses while a draft is in progress** because Draftmancer's protocol silently rejects `setOwnerIsPlayer(True)` and `setSessionOwner(...)` while `drafting` is true if the owner is spectator-only. Works pre-draft and post-`endDraft`.

### Auto-ready check + Not-Ready cancel

When sessionUsers fills to `max(1, expected_attendee_count)`, the bot fires the ready check automatically. If anyone clicks "Not Ready" during the auto check, it cancels and the round falls back to manual `/ready`. Manual `/ready` is unconstrained (toggle Ready/NotReady all you want).

### Identity / counter changes

- `pod_draft_events.event_number` and `pod_draft_config` table removed in commit `d470ec1`. Event identity is now name + `event_date`. `draftmancer_session` is named `{prefix}-{set}-{#N|Month-D}` with `-A`/`-B`/`-C` letter suffixes for same-day collisions.
- Title-parsed `#N` is preferred for the session name when present; otherwise falls back to `Month-Day`.

### Test conveniences (never in prod)

- `POD_DRAFT_SKIP_REMINDER_WAIT=true` — fire T-5 reminder 10s after detection instead of at event_time - 5min.
- Bot fill — off the production guild the bot pads every empty seat up to `max_players`, so a solo human can `startDraft` and run a draft through to the end. A community pod drafts the players who turned up. `_desired_bot_count` decides it, and is the seam to widen for a seat somebody drops mid-draft.
- `POD_DRAFT_PICK_TIMER=1` — 1-second pick timer so the draft auto-resolves quickly.
- `AUTO_REFRESH_ENABLED=false` — silences the 17lands auto-refresh tick on the test bot.

### Owner-only debug commands

- `!testlobby [state]` — sandbox preview of the lobby + bracket UI in any channel. No DB writes. States include `round1`, `round3`, `complete`, etc.
- `!sync` — publish slash commands to the test guild.

## Architectural notes worth remembering

- **`ACTIVE_POD_MANAGERS` is in-memory only.** After a bot restart mid-bracket, dropdown clicks still commit to DB (persistent View dispatches), but `_maybe_advance` bails because no manager exists. Real-pod recovery is manual today.
- **`RoundResultsView` is persistent.** `bot.add_view(RoundResultsView())` is called at startup, registering 5 generic Select slots with custom_ids `podmatchresult:0..4`. The match_id is encoded in each option value, so per-message state isn't tied to the registered View instance.

## Pending work (milestone 7 + 8)

### M7 — Identity matching, read commands, admin commands

1. Migration: add `players.arena_name` (nullable string, stores full `Name#12345`).
2. Name-normalization helper — strip `#\d+` suffix + lowercase. Applied to both sides of every comparison except the explicit `arena_name` leg.
3. Update `_player_for_name` (and the auto-link paths in `_add_attendee` + `upsert_participant`): exact `lower(arena_name)` → normalized `display_name` → normalized `discord_username`.
4. `/pod-link-arena <Name#12345>` — opt-in command; always-overwrites `Player.arena_name`, backfills past unlinked `pod_draft_participants` by `draftmancer_name`. Validates input contains `#\d+`.
5. Live lobby verification: on every `sessionUsers` update, edit the pod-draft thread's pinned/embedded roster message to show ✅ linked vs ❓ unlinked Draftmancer names. Block the ready check until all are linked (or admin overrides via `/ready` — TBD).
6. Unmatched-user prompt: when any name in the lobby is unlinked, post (or update) a thread message listing them with `/pod-link-arena Name#12345` instructions.
7. `/pod-leaderboard [set:]` — champion history per set, plus a Cube/Special section by `format_label`.
8. `/pod-stats [player:]` — per-player career view (lifetime trophies, in-set trophies, events played, total record).
9. `/stats` augmentation — append "Pod trophies: 2 lifetime · 1 in SOS" line when the invoker has any pod-draft trophies.
10. `/pod-result-edit <event_id> <player_name> <field> <value>` — admin, fix placement/record/winner/score/eliminated_round.
11. `/pod-result-delete <event_id>` — admin, cascade-deletes the event row. Ephemeral confirmation prompt.
12. Standings post: render each linked participant as `[Name](dischord.pages.dev/leaderboard/<slug>)` markdown.

### Deferred (handle later)

- `/join` flow Arena-name prompt — doubles as a chance to pitch the pod-drafter role. Skip-able; stores `arena_name` on the new Player row. Not blocking for M7 since `/pod-link-arena` covers the same ground post-hoc.

### M8 — Tests for remaining surfaces

- Name-normalization helper (suffix stripping, case folding, edge cases like `Name#` with no digits)
- `_player_for_name` match priority (arena_name > display_name > discord_username; normalized comparisons)
- `/pod-link-arena` behaviors (sets arena_name, backfills, overwrites, rejects bad input)
- Live lobby embed updates on sessionUsers changes
- Ready-check gating on full verification
- Admin command validation paths

## Quick reference — test runbook

```bash
# Start the test bot (local dev)
docker start dischord-pg
.venv/bin/python -u -m bot.main

# Preview the bracket UI in-memory (no DB writes, any channel):
# 1. In any channel, run:  !testlobby round1   (or round3 to jump to final round)
# 2. Pick from each dropdown to advance through R1 → R2 → R3 → champion

# Full draft flow (real sesh + real Draftmancer):
# 1. Run sesh /create in #pod-draft-coordination
# 2. Bot detects, posts a confirmation in the auto-created thread
# 3. With POD_DRAFT_SKIP_REMINDER_WAIT=true, 10s later the bot connects to Draftmancer
# 4. Join the Draftmancer URL, /ready (or wait for auto-ready), click Ready
# 5. Draft completes (POD_DRAFT_PICK_TIMER=1 keeps it snappy)
# 6. endDraft triggers Python Swiss → R1 pairings post in the thread
```

## Reference

- Amelas/DraftBot is the canonical source for Draftmancer socket protocol patterns. See `services/draft_setup_manager.py`, `cogs/draft_control.py` (`/mutiny`).
- Draftmancer server source: https://github.com/Senryoku/Draftmancer/blob/main/src/server.ts — owner-only socket events are gated by `prepareSocketCallback(..., true)`.
