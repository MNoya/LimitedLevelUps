# Opt-in DM notifications (lobby-open + ready nudge)

## Status — SHIPPED

Built as `bot/services/pod_link_dm.py` (the lobby-open link DM, its notify toggle and in-DM Link Arena button) with the preference stored on `players.dm_draft_link` (migration `d2e3f4a5b6c7`) and toggled from `/roles` (`bot/commands/roles.py`). Delivers the [[pod-personalized-link]] link; shipped in the same deploy as that button.

As-built deviations from the draft below: the preference defaults **on**, not off — every existing drafter gets the DM without a backfill, and the toggle is opt-out. v1 shipped the lobby-open link broadcast-by-DM only; the targeted straggler nudge and the ready-check nudge were not built. A closed inbox is surfaced by a test DM fired on opt-in from `/roles`.

## Kickoff prompt

> Implement opt-in DM notifications for pod drafts, per `spec/pod-dm-notifications.md`. Read that spec and `CLAUDE.md` first. Build `spec/pod-personalized-link.md` before this — this delivers that same link, so the link builder should already exist. Before writing code: pin down the open decisions with me (v1 scope — link DM vs targeted straggler nudge vs both; default off; toggle in `/roles` vs a standalone command; whether to surface "your DMs are off"), since this half carries a new preference store and is easy to over-build. Reuse the existing DM infra (`User.send` + `Forbidden` skip, `PodDraftDmMessage`, batched sends). Conventions: no inline comments, Title Case on Discord menus/options, no first-person in bot copy, test logic not framework, leave changes staged and don't commit until I ask.

## Context

Amelas DraftBot DMs every signed-up player at ready-check start and again at teams-created (the second carries the Draftmancer link); a member of theirs specifically praised this. We already DM players during the tournament phase (round pairings, submit-deck: `bot/services/pod_tournament.py`) but never at the join/ready phase.

Key reframe from the session: a thread `@mention` is already a push notification, hitting the same devices a DM would. So DMing everyone at lobby-open *on top of* the existing thread ping is double-notifying — which is exactly why DraftBot's DMs read as noisy (verified in the clone: `views.py:824-831` pings all signed-up players in-channel and *then* DMs the opted-in ones). The DM's real, non-redundant value is reaching players who tabbed away from the channel.

Framing: the link is a **broadcast** (everyone needs the same URL, belongs in the thread); "we're waiting on *you*" is a **targeted nudge** (belongs in a DM). Don't duplicate the broadcast.

## Design

- **Opt-in, default off.** True opt-in is quieter than DraftBot's effective opt-out (their DB column defaults false but the guild config default is true, `preference_service.py` + `config.py:376` in the clone). Off-by-default means no surprise DMs and no double-ping unless a player asked for it.
- **Toggle home:** fold a "DM me my draft link" toggle into `/roles` (already framed as "toggle your notifications, green means subscribed", `bot/commands/roles.py`, `bot/services/ping_roles.py`) rather than a standalone `/toggle_dm_notifications`. One place for all notification prefs.
- **Preference store:** none exists today (searched — only role-based channel-ping opt-in). Add a per-user DM preference (a column or small table, analogous to DraftBot's `PlayerPreferences.dm_notifications`).
- **What the DM carries:**
  - At lobby open: the personalized link (reuse the [[pod-personalized-link]] builder).
  - At ready-check: a "load the session and ready up" nudge. **Structural note:** our ready check is Draftmancer-native and fires *after* the link is posted (players ready inside the loaded session). DraftBot's is a Discord-native gate *before* the link exists. So our DM says "load + ready in Draftmancer," not DraftBot's "click Ready in Discord."
- **Only DM opted-in players**, so any overlap with the thread ping is consensual.
- **Reuse existing DM infra:** `User.send` with `discord.Forbidden` silent-skip, `PodDraftDmMessage` persistence (`bot/models.py:283-299`), and batched sends to avoid rate limits (DraftBot batches 8 with a 1s gap).
- **Optional extra:** a post-draft recap DM with the 17lands replay link. We already capture replays (`PodDraftReplay`, `bot/services/pod_replays.py`) but never surface them in Discord; DraftBot has no equivalent.

## Existing references

`/roles` (`bot/commands/roles.py`, `bot/services/ping_roles.py`); pairing DMs (`bot/services/pod_tournament.py`, `send_round_pairing_dms`); lobby-open posts (`bot/tasks/pod_draft_reminder.py`, `bot/services/pod_launch.py`); ready check (`bot/services/pod_draft_manager.py`, `initiate_ready_check` ~657, `_maybe_schedule_lobby_full_prompt` ~1547).

## Resolved decisions

- v1 scope: the lobby-open link DM only. The targeted straggler nudge stays a possible follow-up and needs a presence check off the manager.
- Default on, folded into `/roles` next to the role toggles, with a matching toggle inside the DM.
- The closed-inbox hole is surfaced by a test DM on opt-in from `/roles`; a `Forbidden` drop at lobby-open time is still silent, since the in-thread Join Draft button is the fallback for anyone the DM can't reach.

## Still open

- Post-draft recap DM with the 17lands replay link (`PodDraftReplay`), not built.

## Testing

Preference-gating logic (who is eligible), targeting (correct recipient set), and `Forbidden` handled without breaking the flow. Never test Discord delivery itself or exact copy.
