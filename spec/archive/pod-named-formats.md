# Named formats on the daily launcher

Design intent for the launcher offering more than one format a day, where every pod's format is known before signups open. Shipped. `spec/pod-workflow.md` stays the engineering map for pod code generally; this covers only the named-format model and what it replaces. The one decision to hold on to: a pod's format is never inferred from a stored player preference.

## The problem this replaces

The launcher used to offer one undifferentiated slot per time and infer what each signup wanted from a stored per-player preference (`Player.format_interests`, plus a flashback ranking and cube choices). A slot then decided its own format after the fact. Every failure came out of that inference:

- A slot could only fire into the latest set, so a group that wanted a past set never graduated no matter how many joined.
- The surplus rule in `fills_latest` routed a player who had marked "Any Format" onto the table they had not asked for, invisibly, and against pod formation.
- Nothing re-evaluated firing when a preference changed, so telling players "update your preference and it will start" was a false promise.
- Resolving the concrete set after signups meant nobody knew what they had signed up for. Players rejected this directly: they wanted the set named up front, and a same-day vote among six people reached no consensus.

The fix is to make format a property of the **pod**, not of the **player**. Once each pod carries its own format, there is nothing to infer, and the whole inference layer stops being consulted.

## Model

**A day offers a set of formats.** Any number of them: the latest set, past sets, registered cubes, in any combination, and a day may drop the latest set entirely. The formats for a day are written down ahead of time in `bot/services/pod_format_schedule.py` — a hardcoded table of full format lists, keyed by date for a whole day or by `(date, lane)` to override one slot, with `LATEST` standing for whatever set is current so a table written months ahead survives a rotation. No poll, no derivation, nothing decided while players are signing up. A date with no entry offers only the latest set, which is also the state a fresh set cycle starts in: flashback returns when dates are added, never automatically.

**Each pod on offer is its own thing.** Its own signal, its own roster, its own quorum, its own lifecycle. A time slot holding two formats holds two pods.

**Each pod gets its own button**, labelled with the format it joins (`Early MSH`, `Early PEASANT`). Pressing joins, pressing again leaves. That is the whole interaction. Nothing consults a stored preference.

**A player may join several pods**, including both formats at one time, which means "I will play either". The roster marks those players with the flexible glyph, and the allocation rule below is what splits them when the first of their pods fires.

## Lifecycle

Four states. The launcher's job is signups, so it renders a pod fully until the pod stops taking them.

| state | meaning | render |
|---|---|---|
| gathering | below quorum, no thread | full roster block |
| gathering with a thread | reached quorum, thread and scheduled card exist, **still taking signups** | full roster block, with the pod's thread link directly above its own format's block |
| drafting | the draft has actually started | one compact line with the playing mark |
| played | `finalized_at` set | one compact line with the trophy and the winner |

Reaching quorum does **not** close a pod. `set_membership` accepts joins on a fired signal on purpose, and the Draftmancer lobby only opens ten minutes before the start time, so a pod is joinable from the moment it forms until the draft begins.

The lock point is **draft start**, not lobby open. Nothing persists "the draft started" — `socket_status` goes `pending` → `connected` at lobby open → `draft_done` after the draft, so `connected` covers both waiting and drafting. The truth is `PodDraftManager.drafting`, in memory: `pod_launch._draft_started` reads it through `ACTIVE_POD_MANAGERS` when a manager is live and falls back to `draft_done` for restart safety.

A slot collapses to compact lines only when **every** pod there is drafting. One format drafting leaves the other a full joinable block, which is why `locked` is per pod.

## Allocation when a pod fires

A pod fires at `pod_signal_fire_threshold` members. On firing it keeps its dedicated members and takes **only as many shared members as it needs** to reach a full pod, releasing the rest to the other pods at that time (`allocate_fire_roster_sync`). Whichever of those the release brings up to a full pod fires right after (`_launch_ready_siblings`), so the slot settles in one pass.

The naive rule — first pod to quorum takes everyone in it — strands people. With 5 signed up for the latest set only, 5 for the second format only, and 2 who joined both, both pods read 7; whichever crossed quorum first takes both shared players and the other drops to 5 and never fires. One pod of 7, five people left out. Needs-based allocation gives two pods of six and makes click order irrelevant.

The standoff is reachable when nothing can fire yet: signups on a slot whose own day has not arrived hold at any count, so an evening of them can leave two pods over quorum, and the morning post graduates them together (fullest first, ties to Format 1). On a live day a pod fires at exactly the threshold, so there is never a spare to release and the same rule instead does the other half of the job, keeping a shared player off every pod but the one they are now in.

One refinement the rule needs: release a spare shared member only when it actually brings the other pod to a full table. Otherwise a pod of 6 dedicated players would hand its 2 flexible signups to a pod holding nobody else, and those two would draft nothing. A shared member always ends on exactly one roster — they cannot draft two pods at one time.

Players are told one sentence, which lives in `pod_launcher_copy`.

## Retargeting a slot

A moderator has to be able to correct a slot's format when it is wrong or when the channel agrees on something else. That is the whole requirement: change the format a gathering slot offers, keep the signups already on it, re-render. No pod is created, nothing moves between slots, and a slot that already fired is not retargeted — its pod changes format in the lobby's Settings panel instead.

Under per-format signals this is a `set_code` and bucket-key rewrite on that one signal. Its members are rows on the signal, so they carry over untouched, and the next render regenerates the buttons with the new key.

The groundwork is in: the schedule is read only when `create_poll_signals` seeds the signals, and the render derives a slot's formats from the signals that exist, so a rewrite is not overwritten on the next repaint. **The command itself is not built.** The plan:

- **Surface: a mod slash command**, not a control on the launcher. `/pod-retarget slot:<Early|Late> format:<autocomplete> day:<today|tomorrow>`, with the format autocomplete reusing `pod_format.format_choices`. A gear on the board would put a mod control on a player surface and would still need an interaction check to refuse everyone else; a slash command stays off the card and lands in the audit log.
- **The write** is one sync helper: resolve the open poll signal by (lane, day, current format), then set `bucket = named_bucket_key(time_key, new_code)` and `set_code = new_code`. Members are rows on the signal, so the roster carries over untouched, and the next render regenerates the block and the button from the new key. The underfill beats are armed per `signal_id`, which does not change, so nothing needs re-arming.
- **Refuse, with the reason, when:** the code resolves to neither a set nor a registered cube (`resolve_format_code`); the signal already fired or expired, where the pod exists and its format changes in the lobby's Settings panel instead; another signal at that slot already offers the target format, which would collide on `(message_id, bucket, signal_date)` and double the offer; or a pod at that slot already covers it.
- **After the write:** clear the slot's standing nudge, since it is located by a name derived from the format and the old one would be orphaned, then `refresh_launcher_for_date` and an audit entry. The roster signed up for a named format, so a retarget also posts a short public note in the coordination channel naming old and new and mentioning the members, the way a reschedule notes itself in the pod thread.
- **Tests:** the rewrite keeps its members, and each refusal branch.

## What suppresses signups

Only the Set Championship. A championship slot renders read-only with a thread link and no join toggle; signup happens in its thread.

A pod that exists at a slot does **not** suppress the other formats there. Both checks that used to hide them are per-format now: `create_poll_signals` skips only the formats a pod already covers, and `_lane_snapshot` matches an event to the signal it fired from or to a signal of its own format, leaving the rest to gather behind their own buttons. `_event_ids_for_slot` returns one pod per format at a slot time (newest per format, plus its extra tables) instead of the single newest event.

## How it is built

- **The schedule** (`pod_format_schedule.py`): a table of full format lists per day or `(day, lane)`, with `LATEST` resolved at read time. Read only by `create_poll_signals`. Guarded by a test that fails on a code resolving to neither a known set nor a registered cube.
- **One signal per (slot, format)**, keyed `named_bucket_key(time_key, set_code)` with `set_code` populated. `bucket_by_key` resolves the time half, so lanes, ping roles and slot times behave as before and no migration was needed — `PodSignal.bucket` was already the identity and composite keys keep `(message_id, bucket, signal_date)` unique. A row keyed on the bare time slot is adopted as the latest set's and rewritten, so signups collected before this shipped survived the first post that bound them. Expiry, underfill beats and the nudge (named after the pod's own format) all arm per signal.
- **Quorum is the signal's own member count** (`should_fire`), claimed through `claim_slot_fire_sync`, which re-reads the count so a pod stripped by an allocation beside it can no longer fire short. `_launch_slot` posts the card on the signal's `set_code`, format-locked.
- **The render** derives a slot's formats from the signals that exist: per-format roster blocks under one slot header and timestamp, a format nobody joined keeping its header over a dash, the pod's thread link above the format it plays, the flexible glyph on a player who joined more than one pod there, and a compact line for a pod that is drafting. Cubes ping `@Cube`, past sets `@Flashback`, the latest set `@Latest Set` (`reconcile_ping_roles` creates them). `LauncherSlot` is one pod, not one slot; a column groups its pods by start time.
- **Buttons are `DynamicItem`s** (`SlotJoinButton`, `SlotSignUpButton`, `BoardLeaveButton`, `PlayAgainButton`) registered in `main.py`, since the keys carry formats and no startup registration could enumerate them. Play Again re-signs for the same slot and format, and is only offered when the next day carries that format.
- **Format Preference removed** from the launcher and the join and grant cards, and Save-only everywhere it remains. `InterestPromptView`, the ranking modal, `interest_button()` and all four DB columns are intact and dormant, kept for a future season-planning surface. The welcome card still carries the button, since it is onboarding rather than signup and is currently the only way ranking data arrives.

Preview commands: `!test named` for the render across day shapes, `!test lifecycle` for the five states, `!test poll split` for the allocation case, and a set or cube code as an order-free arg to `!test poll` / `!test launcher` to drive any format live without waiting for its date.

## Deliberately not doing

- **No stored format preference in the signup path.** It is what produced every failure above.
- **No format vote after signup.** Rejected by players outright.
- **No deferred settle.** Firing at quorum stays, so a pod forms as soon as it can and keeps gathering.
- **No post-fire format replacement.** A pod that already exists changes format through the lobby's Settings panel, which already works.

## Known gaps

- **The link hold has no release.** `pod_join_button.hold_link_for_roster` reserves the lobby link for the roster for two minutes, but nothing edits the post afterwards, so the message keeps a release time that has passed and the session URL never returns. Needs the message captured at post time and one scheduled edit.
- **Early release only counts button presses.** The lobby DM's link button fires no interaction, so a roster that opens the DM never records a claim and the hold runs its full timer.
- **Nothing checks seats remain.** After the hold lifts, the button hands out a link even if the roster already filled the pod.
- **Roster-versus-roster contention is unsolved.** More signups than seats is first-come among people who committed, which is acceptable; fixing it properly needs a ready check that holds seats.
- **Rendering has no test coverage.** The launcher embed and column code are exercised only by the `!test` previews and by an offline harness that primes the emoji cache and prints every day shape. A missing argument in the formats heading once passed the full suite and would have reached production.
