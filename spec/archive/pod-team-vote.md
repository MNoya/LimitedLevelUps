# Pod Team Draft: by size, and by vote

## Goal

Six players is what Team Draft is for, so a pod that size drafts in teams without being asked. The community defaults to 8-player Swiss (Fast Bracket as an optimization); nothing about a six-player pod makes a bracket the better shape, so there is no question to put to the room. Any other size keeps the default. The vote card survives as `/pod-team`, the manual way to propose Team Draft to a pod the size rule does not cover.

## The size rule

`PodDraftManager._sync_auto_pairing` runs at the two moments the size is known: inside the lobby repaint, so it re-reads on every join and leave, and at the head of `initiate_ready_check`, which is the last moment before the draft.

- **The size a pod reads as** is `_auto_pairing_size`: the roster it was drawn for (`expected_attendee_count` — the Yes and confirmed roster at lobby open, the claim count for a table built by a split) or the Draftmancer lobby when more players than that turned up, held down to `max_players`. A pod drawn for eight is not a six-player pod while it sits at six; a table capped at six is one however many signed up.
- **At the ready check** it reads the lobby alone (`present_only`). Whatever the pod was drawn for, the six players in the room are the six about to draft, so a pod that reached its check as a bracket with six present is moved then. This is the backstop that makes Team Draft the default for six rather than something the room has to arrange.
- **At exactly 6** the pod goes to `team`, remembering the mode it displaced in `auto_team_from`. That field is also the record that the bot is the one holding the pod there, so a team pod it did not set is never taken off.
- **At any other size** the displaced mode comes back. A lobby that fills to 8 is a bracket again.
- **Guards**: pre-draft only (`current_round == 0`, not drafting or complete), never a mock, and never once `pairing_set_by_user` is set. Every call to `set_event_pairing_mode` sets it — the Settings panel, the `/draft` launcher presets, a Team-Draft or Round Robin vote — so anything anyone picked outranks the pod's size, permanently. **Turning it back is the only way out**: six players who want something else set it in Settings, and neither the lobby nor the ready check moves it again.

Each change persists through `persist_pairing_mode`, pushes `teamDraft` to the live session (`apply_team_draft_setting`), refreshes the pod card (`notify_card_refresh`), and posts a thread notice.

### Notice

The same line a player's own Settings change posts, with no actor, since nobody chose it: `⚙️ Set **Pairings** to **Team Draft**` over the mode's description. Built by `pairing_change_message(None, mode)`; `settings_change_message` drops the actor prefix when it gets None. It goes through `send_settings_notice` with `settings_notice_markers("Pairings")`, which carries both the actor and no-actor forms, so the next pairing notice retires the last one whoever wrote it and the thread never stacks two.

## The manual vote (`/pod-team`)

A proposal, not a commitment, for the pods the size rule leaves alone — 4, 8, 10, or a 6-player pod whose Pairings someone already set by hand.

- The offer is **its own embed card** in the thread, shaped like the `/pod-table` card: a green embed, the prompt as the title, two side-by-side columns of voters, one button per side (`🤝 Team Draft` / `⏳ Wait`).
- **The vote is public**: the columns list who voted, so players see the push building.
- Locks at a **majority of the pod** — `pod_size // 2 + 1`. The size is fixed when the offer is posted, so a mid-vote arrival can't move the target.
- **The card message is the tally.** Each voter is stored in their column as a mention, which Discord renders as a name and keeps machine-readable, so a click reads the columns straight off the message and the vote survives a restart.
- **On lock**: `set_event_pairing_mode(event_id, "team")` and the card edits in place — title flips to `🤝 Team Draft is on!`, the instruction line drops, the buttons go. The card stays as the record. Locking also ends the size rule for that pod, since it went through `set_event_pairing_mode`.
- Re-running with a vote already up deletes that card and re-posts it at the bottom of the thread, carrying its votes over.
- The offer is deleted at draft start, and when the lobby outgrows the size it was posted for.

## Integration points

| Concern | Location |
|---|---|
| Size rule | `_sync_auto_pairing` / `_auto_pairing_size` / `_move_pairing` (`bot/services/pod_draft_manager.py`) |
| Ready-check backstop | `initiate_ready_check` (`bot/services/pod_draft_manager.py`) |
| Human override | `set_event_pairing_mode` sets `pairing_set_by_user` (`bot/services/pod_draft_manager.py`) |
| Notice copy | `pairing_change_message` (`bot/services/pod_pairing_select.py`), `settings_change_message` (`bot/services/pod_format.py`) |
| Manual vote command | `/pod-team` → `offer_team_vote_manual` (`bot/commands/pod_draft.py`) |
| Vote card + copy + button | `bot/services/pod_team_vote.py`; `TeamVoteButton` registered in `bot/main.py` |
| Vote lock | `handle_team_vote_click` (`bot/services/pod_draft_manager.py`) |

## Preview

`!test teamvote` posts the offer card with a **working** 🤝 button and three votes prefilled, so the previewer's own click is the fourth and locks it. Self-contained, no live pod. The shared builders back it so it can't drift from the live card.
