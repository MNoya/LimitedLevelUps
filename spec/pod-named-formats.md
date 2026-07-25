# Named formats on the daily launcher

Design intent for the launcher offering more than one format a day, where every pod's format is known before signups open. Written as the handoff into the remaining implementation. `spec/pod-workflow.md` stays the engineering map for pod code generally; this covers only the named-format model and what it replaces.

## Startup prompt

Paste this to open the session that finishes the work:

> Read `spec/pod-named-formats.md` end to end before touching anything, then implement the six items under Remaining work, in that order. The model, the lifecycle and the allocation rule in that doc are settled decisions reached over a long design session — do not re-litigate them, and in particular do not reintroduce inferring a pod's format from a stored player preference, which is what the whole change exists to remove.
>
> Everything under Already built is committed on `master` and working. Read the current `bot/tasks/pod_daily_poll.py`, `bot/services/pod_launch.py`, `bot/services/pod_signals.py` and `bot/services/pod_format_schedule.py` before editing, since the render and the composite-key helpers are already in place and the remaining work builds on them rather than replacing them.
>
> Verify by rendering, not only by tests: the launcher embed and column code have no test coverage, and a missing argument there once passed the full suite. `!test named`, `!test lifecycle`, `!test poll <CODE>` and `!test launcher <CODE>` drive every case. Prime the emoji cache when checking a render outside the bot, or set symbols come back as `None` and hide real bugs. Run `.venv/bin/pytest bot/tests/` before finishing.
>
> Leave the commit to me and never push.

## The problem this replaces

The launcher used to offer one undifferentiated slot per time and infer what each signup wanted from a stored per-player preference (`Player.format_interests`, plus a flashback ranking and cube choices). A slot then decided its own format after the fact. Every failure came out of that inference:

- A slot could only fire into the latest set, so a group that wanted a past set never graduated no matter how many joined.
- The surplus rule in `fills_latest` routed a player who had marked "Any Format" onto the table they had not asked for, invisibly, and against pod formation.
- Nothing re-evaluated firing when a preference changed, so telling players "update your preference and it will start" was a false promise.
- Resolving the concrete set after signups meant nobody knew what they had signed up for. Players rejected this directly: they wanted the set named up front, and a same-day vote among six people reached no consensus.

The fix is to make format a property of the **pod**, not of the **player**. Once each pod carries its own format, there is nothing to infer, and the whole inference layer stops being consulted.

## Model

**A day offers a set of formats.** The latest set, plus an optional second format that is a past set or a registered cube. The formats for a day are written down ahead of time in `bot/services/pod_format_schedule.py` — a hardcoded table, keyed by date for a whole day or by `(date, lane)` to override one slot. No poll, no derivation, nothing decided while players are signing up. A date with no entry offers only the latest set, which is also the state a fresh set cycle starts in: flashback returns when dates are added, never automatically.

**Each pod on offer is its own thing.** Its own signal, its own roster, its own quorum, its own lifecycle. A time slot holding two formats holds two pods.

**Each pod gets its own button**, labelled with the format it joins (`Early MSH`, `Early PEASANT`). Pressing joins, pressing again leaves. That is the whole interaction. Nothing consults a stored preference.

**A player may join several pods**, including both formats at one time, which means "I will play either".

## Lifecycle

Four states. The launcher's job is signups, so it renders a pod fully until the pod stops taking them.

| state | meaning | render |
|---|---|---|
| gathering | below quorum, no thread | full roster block |
| gathering with a thread | reached quorum, thread and scheduled card exist, **still taking signups** | full roster block, with the pod's thread link directly above its own format's block |
| drafting | the draft has actually started | one compact line with the playing mark |
| played | `finalized_at` set | one compact line with the trophy and the winner |

Reaching quorum does **not** close a pod. `toggle_member` accepts joins on a fired signal on purpose, and the Draftmancer lobby only opens ten minutes before the start time, so a pod is joinable from the moment it forms until the draft begins.

The lock point is **draft start**, not lobby open. This is the one thing the current code gets wrong: `LauncherSlot.locked_formats` is populated from `socket_status != "pending"`, which flips at lobby open and locks a pod about ten minutes early. Nothing persists "the draft started" — `socket_status` goes `pending` → `connected` at lobby open → `draft_done` after the draft, so `connected` covers both waiting and drafting. The truth is `PodDraftManager.drafting`, in memory. Read it through `ACTIVE_POD_MANAGERS` when a manager is live, and fall back to `draft_done` for restart safety.

A slot collapses to a single line only when **every** format it offers is locked. One format drafting leaves the other a full joinable block, which is why `locked_formats` is a set rather than a flag.

## Allocation when a pod fires

A pod fires at `pod_signal_fire_threshold` members. On firing it keeps its dedicated members and takes **only as many shared members as it needs** to reach a full pod, releasing the rest to the other pods at that time.

The naive rule — first pod to quorum takes everyone in it — strands people. With 5 signed up for the latest set only, 5 for the second format only, and 2 who joined both, both pods read 7; whichever crossed quorum first takes both shared players and the other drops to 5 and never fires. One pod of 7, five people left out. Needs-based allocation gives two pods of six and makes click order irrelevant.

Players are told one sentence, which lives in `pod_launcher_copy.POLL_INTRO`.

## What suppresses signups

Only the Set Championship. A championship slot renders read-only with a thread link and no join toggle; signup happens in its thread.

A locked pod at a slot must **not** suppress the other formats there. This is a behavior change: today `_lane_snapshot` finds any event at a slot time and `continue`s, skipping the gathering signal entirely, so a `/draft` pod occupying a slot hides every other format at that time.

## Already built

- **The schedule** (`pod_format_schedule.py`), read per slot-day inside `_lane_snapshot`, so a lane rolled to tomorrow shows tomorrow's format. Guarded by a test that fails on a code resolving to neither a known set nor a registered cube.
- **The render**: per-format roster blocks under one slot header and timestamp; a format nobody joined yet keeps its header over a dash so the offer stays visible; the pod's thread link sits above the format it plays; cubes ping `@Cube` and past sets `@Flashback` (`fi.CUBE_ROLE_NAME`, created by `reconcile_ping_roles`); the formats-on-offer heading block appears only when a second format exists.
- **Composite bucket keys** (`pod_signals.named_bucket_key` / `time_key_of` / `format_of`). `bucket_by_key` resolves the time half, so lanes, ping roles and slot times all behave as before and no migration is needed — `PodSignal.bucket` is already the identity and composite keys keep `(message_id, bucket, signal_date)` unique.
- **Buttons** emit composite custom_ids on a two-format day and plain keys on a latest-only day, so such a day is byte-identical to the launcher before any of this.
- **Format Preference removed** from the launcher and the join and grant cards. `InterestPromptView`, the ranking modal, `interest_button()` and all four DB columns are intact and dormant, kept for a future season-planning surface. The welcome card still carries the button, since it is onboarding rather than signup and is currently the only way ranking data arrives.
- **`fills_latest` no longer counts no-preference riders** as a format's own crowd, which is what routed a flexible player onto the wrong table.

Preview commands: `!test named` for the render across day shapes, `!test lifecycle` for the four states, and a set or cube code as an order-free arg to `!test poll` / `!test launcher` to drive any format live without waiting for its date.

## Remaining work

1. **Per-format signals.** `create_poll_signals` creates one signal per (slot, format) from the schedule, keyed with `named_bucket_key`, with `set_code` populated. Quorum becomes a member count on that signal. `_launch_slot` reads the signal's own `set_code` instead of `active_set_code()`. Expiry and underfill beats arm per signal, so a two-format day arms twice as many.
2. **Formats as a list.** `LauncherSlot.other_format: str | None` cannot express a day that drops the latest set. Generalise to a list of formats per slot so `[MSH]`, `[MSH, PEASANT]`, `[PEASANT]` and three-format days are all the same shape. This also removes the last dependence on `fi.format_teams`, which returns exactly two teams and is the only reason a third format looks hard. Touches the roster render, `_slot_button_keys`, the formats heading, and the Main/Second framing.
3. **Restart safety.** Slot buttons become a `DynamicItem` with a regex custom_id, the way `pod_join_button.JoinDraftButton` already does it. Today `PodPollView(None)` pre-registers plain keys only, so after a restart a live board's composite-key buttons would silently do nothing. A dynamic item also removes that pre-registration loop.
4. **Coexistence.** `_lane_snapshot` stops skipping the gathering signal when an event exists at that slot time, so a locked pod and a gathering pod share a lane.
5. **Needs-based allocation** at fire, per the rule above.
6. **The lock point** moved to draft start, per the lifecycle section.

## Deliberately not doing

- **No stored format preference in the signup path.** It is what produced every failure above.
- **No format vote after signup.** Rejected by players outright.
- **No deferred settle.** Firing at quorum stays, so a pod forms as soon as it can and keeps gathering.
- **No post-fire format replacement.** `/draft` retargeting an unfired slot is a `set_code` and label rewrite on that signal, keeping its members; a pod that already exists changes format through the lobby's Settings panel, which already works.

## Known gaps

- **The link hold has no release.** `pod_join_button.hold_link_for_roster` reserves the lobby link for the roster for two minutes, but nothing edits the post afterwards, so the message keeps a release time that has passed and the session URL never returns. Needs the message captured at post time and one scheduled edit.
- **Early release only counts button presses.** The lobby DM's link button fires no interaction, so a roster that opens the DM never records a claim and the hold runs its full timer.
- **Nothing checks seats remain.** After the hold lifts, the button hands out a link even if the roster already filled the pod.
- **Roster-versus-roster contention is unsolved.** More signups than seats is first-come among people who committed, which is acceptable; fixing it properly needs a ready check that holds seats.
- **Rendering has no test coverage.** The launcher embed and column code are exercised only by the `!test` previews. A missing argument in the formats heading passed the full suite and would have reached production.
- **Disposables still in the tree**: `!test signup` (a rejected modal shape) and `!test modalprobe` (settles whether Discord accepts buttons in a modal — it does not; `PartialEmoji.from_str` does not parse `<:name:id>`, so a modal button payload is refused).
