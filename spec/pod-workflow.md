# Pod-Draft Workflow

How the community forms and fires Magic Arena pod drafts, end to end. This is the operational counterpart to the architecture notes in `CLAUDE.md`: it describes the pod lifecycle as design intent and points at the modules that implement each stage, so the mechanics don't have to be re-inferred from code every time.

Two parts: the **current lifecycle** as it runs today, and the **proposed next state** (the ready-check redesign). Copy lives in code (`bot/commands/messages.py`, `bot/services/pod_reminder_copy.py`), never here — this doc names the real thing and points at the module.

## The community problem

A global Discord community plays MTGA pod drafts together across Europe, the Americas, and Asia, so there is no single good universal start time. Under 100 engaged users today, usually one table, occasionally two or three, and the goal is to scale past that. The system has to turn a loose pool of "I might play" into playable tables of the right size, under real-world friction: uncertain attendance, multiple time zones, several possible tables, an even-count requirement, and declining interest in the current set over its lifespan.

Two table shapes:

- **8 players** → record-based 3-round pod (winners play winners, losers play losers; everyone plays all 3 rounds). Not single-elimination — the `bracket` pairer is a fast-advance variant of Swiss, standings from `pod_swiss.compute_standings`.
- **6 players** → 3v3 Team Draft (a different social contract: you coordinate with teammates).

A signup is **never a binding contract**. People click, then don't show. The system leans on having enough people to fire and on the daily cadence as the safety net — if someone is left out tonight, they try again tomorrow. Design for self-correction, not for forcing anyone to honor a click.

## Entry points

Two ways a pod comes into existence, both feeding the same `PodSignal` → `PodDraftEvent` spine:

- **Daily Pod Launcher** (`bot/tasks/pod_daily_poll.py`, `bot/services/pod_signals.py`, `bot/services/pod_launch.py`) — the recurring "who's playing today" post with fixed slots. The default path.
- **Ad-hoc `/draft`** — a mod schedules a pod at any time with custom signups, independent of the launcher slots. "Right now" opens a live queue; a custom time posts a scheduled RSVP card just like a graduated launcher pod. Either way the mod picked the set.

The old fixed **weekly schedule poster** (`bot/services/pod_schedule.py`, `WEEKLY_SLOTS`, Wed/Thu/Sat, the `/create` template flow) is **deprecated** — not part of the current model and not to be supported or extended.

`/mock-draft` sits outside that spine: no signal, no RSVPs, no rounds. Its channel-level surface is the anchor card (`bot/services/mock_lobby_card.py`), the thread starter, re-rendered in place by the manager through open → drafting → complete → canceled. The card is resolved from the thread id rather than a held message handle (a thread shares its starter's id), so a restart mid-lobby keeps updating it. Preview every state with `!test mockcard [SET]`.

## Core data spine

Interest is gathered on a `PodSignal`; when it fires it produces a `PodDraftEvent` (the pod), and `PodSignalMember` rows are the roster that carries across. All in `bot/models.py`.

- **`PodSignal`** — one interest surface. `kind` is `poll` (a launcher slot), `queue` (a `/draft` "right now" lobby), or `scheduled` (a graduated RSVP card). `status` is `open` → `fired` → `expired`. Carries `bucket`, `signal_date`, `slot_time`, `set_code`, pairing/seating/timer config, `format_locked`, and `event_id` once fired. `format_locked` is true for every pod now: a launcher pod carries the format its own signal opened on, and every `/draft` pod, championship, and mock chose its set up front. The flex path it used to gate (format resolved from the roster) is dormant, see section 4. No SQLAlchemy `Enum` types anywhere in the pod models — status/kind/rsvp are plain strings.
- **`PodSignalMember`** — one roster row per `(signal_id, discord_user_id)`. `rsvp` is `yes` / `maybe` / `no` (default `yes`); `format_interest` is a string array.
- **`PodDraftEvent`** — the pod itself. `socket_status` walks `pending` → `reminded` → `connected` → `draft_done` → `complete`. `kind` is `tournament` (default) or `mock`. Holds `draftmancer_session`, thread ids, pairing/seating mode, bracket/team state, and the draft log. `closed_decklist` gates Closed Decklist mode: the website hides the pod's decklists and pick-by-pick draft log until it finishes (`is_finalized`), toggled from the pod Settings panel and defaulting on for championship pods; gating is visual-only in the frontend (`data/podDecklistAccess.ts`), keyed on the `closed_decklist` column now projected by `public_pod_draft_events`. While closed, an organizer (allowlist in `data/podOrganizers.ts`) sees everything and a signed-in player sees their own seat: their deck plus a scroll-only, seat-pinned draft review (`DraftReviewMOCS` `soloSeat`). Children: `PodDraftParticipant`, `PodDraftMatch`, `PodDraftDmMessage`, `PodDraftReplay`.

Per-player standing preferences live on `Player`: `format_interests` (array), `flashback_ranking` (array, capped at 3), `dm_draft_link` (bool).

## Current lifecycle

### 1. Daily poll (interest collection opens)

Posted by `fire_daily_poll` (`bot/tasks/pod_daily_poll.py`), armed as one APScheduler cron in `init_daily_poll`: every day at 10:00 ET (`POST_HOUR_ET` in `pod_signals.py`, timezone `SCHEDULE_TZ` = America/New_York). It posts into the pod coordination channel (`pod_draft_channel_id`), which must be a Text channel, not Announcement. It no longer skips when a board for today exists: a lane-transition repost may have put one up overnight, and the day's ping belongs on a fresh board at the bottom of the channel, so the standing one is replaced and deleted.

The embed (`build_poll_embed`, "Daily Pod Launcher") carries one **sign up button per pod on offer**, labelled with the format it joins (`Early MSH`, `Early PEASANT`), plus one **Leave** for the whole board (`BoardLeaveButton`), which drops the presser from every pod the board carries. A pod button only ever adds, so a double press cannot undo the first one. Buckets are defined by `PollBucket` in `pod_signals.py`:

- Every day, two buckets: Early Pod 14:00 ET, Late Pod 20:00 ET.

Each bucket maps to a ping role resolved by weekend + time-of-day, weekday (`EARLY_POD_ROLE_NAME` / `LATE_POD_ROLE_NAME`) and weekend (`WEEKEND_EARLY_POD_ROLE_NAME` / `WEEKEND_LATE_POD_ROLE_NAME`) variants in `pod_schedule.py`.

**Post-join notices** (`ping_roles.announce_pod_grant`). A first-ever drafter with no linked Arena handle gets the public welcome in pod-draft-chat; it welcomes them to `@Pod Drafters` and names no slot role. Which slot role a click granted, which pod they joined, when it starts, and the other formats of that slot they are now on all ride on the clicker's **ephemeral** confirmation in the coordination channel, so a join always answers privately even when it also announced publicly. That multi-pod line is the only place the shared-signup model is explained to the person it affects, at the click that made it true. A returning drafter who freshly picks up a slot role gets the grant card instead, which folds that same lead in — the one case the caller skips its own confirmation. No card quotes a saved format preference back: it decides nothing about a signup.

**Named formats.** A day offers a set of formats written down ahead of time in `pod_format_schedule.py` — the latest set plus any past sets or registered cubes, keyed by date or by (date, lane). Format is a property of the **pod**, never of the player: `post_launcher` binds one lazy `PodSignal` (kind `poll`) per (slot, format), each with its own roster, quorum, expiry and underfill beats, keyed `named_bucket_key(time_key, set_code)` so `PodSignal.bucket` stays the identity and no migration was needed. `create_poll_signals` is the **only** reader of the schedule table; after that the signals are the truth for what a slot offers and the render derives its formats from them, which is what makes a moderator retarget survive a repaint. An empty entry (`CLOSED`) shuts a slot instead of naming formats for it: the launcher opens nothing there and no lane rolls into it, which is how the Set Championship holds the Early Pod on its Saturday without a second pod opening alongside. A player may join several pods, including both formats of one time slot, which the roster marks with the flexible glyph. Nothing in the signup path reads a stored preference. Design intent and the failures this replaced: `spec/pod-named-formats.md`.

**Reading the table forward.** `/pod-schedule` (`bot/commands/pod_schedule.py`) renders the same table as a calendar of Monday-start weeks. `LATEST` there resolves per rendered day (`formats_on` → `active_set_code(release_instant(day))`), not at call time, so a day past a rotation names the set it will actually draft; `formats_for` keeps its now-based default, which is what the launcher wants. The grid is a Pillow PNG (`pod_schedule_image.py`) in the site's type, Bebas Neue and Space Grotesk out of `bot/assets/fonts`, with set symbols read from the site's `frontend/public/set-symbols/` so no second copy of those assets lives under `bot/`. Discord displays an embed image at 400px wide, so the logical layout is deliberately narrower than that and drawn at `SCALE`: shrinking the logical grid is the only lever the renderer has to make labels land larger on screen. The surface is Components V2, not an embed: an embed pins its image to the bottom, and the set-release note belongs under the calendar it captions. The container holds a heading, one line naming both slots with their ping role and next start (`next_slot_start`) as a localized timestamp, the calendar, then the release note as `-#` subtext. Both slots quote the weekday role names: a reader wants the role to pick up, and the weekend variants are the launcher's own bookkeeping.

**Rolling columns.** A bucket is one *lane* (`PollBucket.lane`, `LANE_EARLY` / `LANE_LATE`) for life; the weekday and weekend buckets of a time of day are two keys for one lane, so a slot crossing into a weekend keeps its column and picks up the weekend ping role (`bucket_for_lane`). Each lane carries its own day and rolls independently, so a mixed-date board is normal:

- **Flip on completion** — `notify_pod_complete` (`pod_active.py`) fires from the three finalize paths (`finalize_tournament`, `finalize_team_tournament`, `_finalize_mock`) into `roll_lane_after_pod`, which opens the next day's pods for that lane, one per format it offers (`roll_slot_forward_sync`, idempotent per lane+day+format) and re-renders. Completion, not firing, is the trigger: a pod mid-rounds still owns its slot.
- **Flip on expiry** — a slot whose start passes unfired rolls the same way (`fire_slot_expiry` → the roll hook registered by `init_daily_poll`); a restart sweep (`reconcile_rolled_lanes`) catches a lane whose pod finished or slot passed while the bot was down.
- **Rolled slots live on the posted message** — the pre-created next-day signal binds to the launcher already on screen, which is why `pod_signals` is unique on (`message_id`, `bucket`, `signal_date`). A board's own day is the *earliest* day its slots cover; `_signal_by_message_bucket` resolves a click to the soonest still-gathering row of that exact key, so a column stacking two days of one format stays correct.
- **Adopt at 11:00** — `create_poll_signals` adopts today's already-open rows onto the fresh message instead of double-creating, so the new board carries whatever accumulated overnight; the old message then retires to its `On This Day` history (`close_recent_launchers`).
- **Hold and show** — signups on a later day accumulate but cannot fire (`slot_can_fire`). The morning post re-checks thresholds and graduates whatever is already full (`_graduate_held_slots`), fullest pod first with ties to Format 1, so which format runs when two are full comes from demand and not from row order. This is the only place a pod fires above the threshold, which is what makes needs-based allocation load-bearing rather than theoretical.
- **Catch up on restart** — `catch_up_daily_poll` runs in the startup sweep: the 11:00 cron is re-armed for its next future fire on every start, so a bot that was down at the post hour would skip the day's post and leave the pods that filled overnight held until their slot time passed. It posts the missing board, or runs the graduation pass when the board is already up.
- **Play Again** — five minutes after a pod is finalized, `post_play_again_prompt` posts a one-click prompt in that pod's thread; the button writes a member onto the next day's pod of the same slot **and format**, resolved at click time (`open_slot_for_bucket_sync`), so it stays correct after a restart. It is only posted when the next day still carries that format.

The render (`build_poll_embed`) is one inline field per lane. Within a lane, pods are grouped by start time: one slot-name header and timestamp, then one roster block per format, and a pod that has started drafting shrinks to a single line inside its group. A slot collapses to compact lines only once **every** format there is drafting, which is when the column splits into Played and Next sections. A played pod's line links its thread and credits its winner (the champion's `Player.slug` seat on the website, or a team draft's winning side with no seat). Every button is a `DynamicItem` (`SlotJoinButton`, `SlotSignUpButton`, `BoardLeaveButton`, `PlayAgainButton`) registered in `main.py`, since the set of keys is not knowable at startup. Launcher copy lives in `bot/services/pod_launcher_copy.py`.

### 2. Interest → fire (a slot graduates)

The fire threshold is **6** (`pod_signal_fire_threshold`). When a pod's own roster reaches 6, `_apply_slot_join` fires it via `claim_slot_fire_sync`, an atomic `UPDATE ... WHERE status='open'` guarded by a re-read of the count, so exactly one firing happens and a pod stripped by the allocation below can no longer fire short.

**Needs-based allocation.** A firing pod keeps everyone who signed up for it alone, then takes shared members (players who also joined another format at that time) in join order until it seats a full pod. Spare shared members go to another format there, but only as many as bring that pod to a full table: releasing a body into a pod that still cannot fill would strand a player who could have drafted here. Every shared member therefore ends on exactly one roster. `allocate_fire_roster_sync` runs before the roster is copied to the card, and `_launch_ready_siblings` then fires whichever format the release brought up to a full pod, which is what makes click order irrelevant (5 + 5 + 2 shared becomes two pods of six either way).

Firing does **not** open a Draftmancer lobby. It **graduates the pod into a scheduled RSVP card on its own format** (`_launch_slot` → `post_scheduled_card` in `pod_rsvp.py`, `format_locked`), which:

- posts a channel RSVP card with a Discord thread hanging off it,
- creates a new `PodSignal` (kind `scheduled`, born `fired`) and copies the poll signups onto it as Yes,
- creates the native Discord scheduled event,
- inserts the `PodDraftEvent` (kind `tournament`),
- arms the timed jobs (roster reminder, team-vote offers, T-10 lobby open, underfill checks).

**Moving a pod after it fires.** The lobby Settings panel's Reschedule accepts an offset from the pod's current start (`+30m`, `1h30m`) as well as absolute and natural forms (`parse_new_time`). `reschedule_event` re-arms every timed job off the new start, updates the native event, re-renders the card, the live nudge and the roster reminder, notes it in the thread with the roster mentioned, and repaints the launcher. The pod's `PodSignal.slot_time` deliberately stays on the slot it was gathered in: that is the lane it belongs to and the board that carries it, so the column still reflects it and still rolls off it, while the block renders the pod's new start. The other formats at that slot are untouched, since one pod moved and the slot did not. The pod keeps the name it was created with, which carries the original date and slot label — accurate for the ordinary half-hour move, stale only for a move across a slot boundary, and a rename is deliberately avoided against Discord's rate limits.

Ad-hoc `/draft` (`DraftLauncherView` in `bot/commands/pod_queue.py`) covers both shapes: "Right now" fires the lobby **immediately** (`open_now=True`, `launch_from_signal`, kind `queue`); a custom time posts a scheduled RSVP card (`_schedule_pod`) that then follows the same path as a graduated launcher slot. Either way the mod can preset set, pairing, timer, and notify role.

### 3. RSVP

Only scheduled cards use the full Yes / Maybe / No mechanics; poll and queue members are implicit Yes. States are plain strings (`RSVP_YES/MAYBE/NO` in `pod_signals.py`) on `PodSignalMember.rsvp`. `set_rsvp` upserts Yes/Maybe; **No deletes the roster row** (there is no tracked "not coming" list). The card (`PodRsvpView` in `pod_rsvp.py`) re-renders on every change, grants the `Pod Drafters` role, moves thread membership (Yes/Maybe in, No out), syncs the native event tally, and refreshes the underfill nudge. Pod capacity is 8.

### 4. Format preference, now dormant

Every pod is **format-locked**: a launcher pod carries the format its button named, a `/draft` card or queue, championship, or mock carries the set its organizer chose. A locked pod renders a plain Yes / Maybe roster with no Latest/Flashback split and its roster reminder drops the Format Preference button. The lock is read per surface from the signal (`pod_launch.format_locked_for_event_sync`, `pod_draft_reminder.signal_format_locked_sync`), and a startup sweep (`pod_rsvp.heal_format_locked_cards`) re-renders a still-gathering locked card that predates the lock so it drops any stale split.

Because no flex pod is created any more, the whole preference-and-vote layer below is **dormant**: it decides nothing about a signup or a pod's format. It is kept for a future season-planning surface, where standing preferences would inform which formats get scheduled at all. Do not wire it back into the signup path — that inference is exactly what named formats removed (`spec/pod-named-formats.md`).

- Vocabulary in `pod_format_interest.py`: `latest`, `flashback`, `cube`. "Flashback" means any set that is not the active set (`bot/sets.py:active_set_code()`); custom cubes (Peasant, Samp) are separate. "Flexible" is holding both `latest` and `flashback`, never stored (`Player.is_flexible`).
- The **Format Preference** button on the welcome card and the roster reminder opens an ephemeral multi-select (`InterestPromptView`), Save only. It writes `Player.format_interests`; joining any pod copies the standing value onto `PodSignalMember.format_interest`, which nothing reads back.
- **Standing ranking** — `Player.flashback_ranking` (up to 3, e.g. "FIN DSK NEO"), set via the Rank Sets button.
- **Format Vote** (`pod_format_poll.py`) is posted only by `/vote-format`, which runs in any channel: it goes through the pod's live manager when the invoking thread holds a pod that has not drafted yet, so the card closes at draft start, and posts a standalone card keyed `channel-<id>` anywhere else. The tally lives in the card's embed, so the buttons work with no pod behind them. The card decides nothing: nothing reads its tally, and the format-driven second-table split it used to feed is gone. `/pod-table format:` opens a table on a format a mod picks.
- `format_at_fire` (`pod_format_interest.py`) and `fills_latest` / `format_teams` are likewise unused by the launcher; a pod's format comes from its own signal.

### 5. Nudges and reminders

**Underfill recruiting nudge** (`bot/tasks/pod_underfill.py`) — one living message, edited in place as RSVPs change. Check beats from `pod_underfill_check_hours` = "3,2,1":

- T-3h: silent nudge in the pod chat with a signup link.
- T-2h: catch-up beat for pods born after T-3h.
- T-1h: deletes and reposts to resurface, and pings the slot role — but only at this beat (`pod_underfill_ping_hours` = "1") and only when the gap to the aim is small (`pod_underfill_ping_close_gap` = 2). One ping max per signal.

Target headcount is 8 for scheduled cards (`pod_draft_target_players`), 6 for unfired launcher pods (the fire threshold). Every pod nudges for itself, named after its own format (`_load_slot_for_nudge`), since two pods can share one slot time and one launcher link and the name is all that tells their nudges apart. The nudge is deleted on lobby open and flipped to a "started" record at fire.

**Roster reminder** (`bot/tasks/pod_draft_reminder.py`) — at T-60 (`ROSTER_REMINDER_LEAD_MIN`), posts the roster into the thread while the socket is still pending, through the shared `pod_roster_fields.add_roster_fields`, plain now that every pod is format-locked. It carries Sign Up / Can't and Format Preference buttons (`ReminderRsvpButton`, `ReminderFormatPreferenceButton`), all keyed by event id: the RSVP buttons record against the pod's card through `_apply_surface_rsvp`, and the picker is Save-only (no per-slot Confirm), acking fast then re-rendering the launcher, card, and reminder in the background (`refresh_event_rsvp_surfaces`). The view builder is injected from `pod_daily_poll` via `register_reminder_view_builder` to avoid the import cycle.

**Team-vote pre-offer** — also at T-60, `maybe_offer_prelobby_team_vote` offers a Team Draft card when the Yes roster is exactly 6. A second team-vote offer fires at the o'clock start time. There is **no separate T-1h "rally repost"** today beyond the underfill resurface and the roster reminder.

### 6. Launch and firing

The Draftmancer lobby is created **lazily**: at T-10 for scheduled cards (`open_ondemand_lobby`, armed by `_arm_open` at `event_time - 10min`, `REMINDER_LEAD_MIN`), or immediately for `/draft` "right now" queues. Never at interest-gathering time.

Session ids (`pod_drafts.py`): on-demand sessions are `LLU-<Mon>-<Day>-<rand4>` and deliberately omit the set code so a format change doesn't desync the lobby; the random 4-char tail prevents lobby-ownership seizure. The URL is `{draftmancer_web_url}/?session=<id>` (`draftmancer_url_for`). On open, the lobby link is posted, the manager starts, the link is DM'd to Yes+Maybe, and the format poll is offered if flashback demand exists.

**Ready check / start** (`bot/services/pod_draft_manager.py`) — `initiate_ready_check` requires an even count at or above the floor (`pod_draft_min_ready_players` = 6); a full lobby of 8 auto-prompts it. `/pod-start` force-starts; `/pod-ready` lowers the floor for manual restarts. Ready timeout is 90s.

**Second table** (`bot/commands/pod_table.py`) — at draft start, once seats lock, `offer_second_table` pings the leftover Yes/Maybe roster if a full table's worth (`pod_table_open_threshold` = 6) remains; a format-driven hook does the same at the T-5 settle assessment when the live format vote shows a flashback set can seat its own table without starving the main pod. The 6th distinct joiner materializes the table (clones the source pod, new session/thread/lobby). `/pod-table` opens the same flow manually and can preset a different format.

**Table shapes** (`bot/services/pod_tournament.py`, `pod_bracket.py`, team modules) — default pairing is `bracket`, which requires exactly 8; at any other count it falls back to swiss. Bracket is 3 rounds. The 6-player Team Draft is auto-offered only at exactly 6 (`pod_team_vote.py`, majority = size//2+1); `/pod-team` allows any pod ≥ 4. Team pods write no individual placement — trophies are 3-0 records only. Team championship and trophy-hype showcases live in `pod_team_showcase.py`.

### Config and thresholds (`bot/config.py`)

| Setting | Value | Meaning |
| --- | --- | --- |
| `pod_signal_fire_threshold` | 6 | roster count that fires a lazy slot / queue |
| `pod_draft_target_players` | 8 | underfill aim for scheduled cards |
| `pod_draft_min_ready_players` | 6 | ready-check floor (even count required) |
| `pod_draft_max_players` | 8 | lobby capacity |
| `pod_table_open_threshold` | 6 | leftover roster needed to offer a second table |
| `pod_underfill_check_hours` | "3,2,1" | underfill nudge beats before start |
| `pod_underfill_ping_hours` | "1" | which beat may ping the slot role |
| `pod_underfill_ping_close_gap` | 2 | only ping when within this many of the aim |
| `pod_draft_pick_timer` | 60 | default Draftmancer pick timer; older sets and cubes override it in `pod_format.py` |
| `pod_draft_channel_id` | — | coordination channel (must be Text, not Announcement) |

Slot post hours and bucket times live in `pod_signals.py`; lead times (`REMINDER_LEAD_MIN` = 10, `ROSTER_REMINDER_LEAD_MIN` = 60) live beside the tasks that use them.

## Proposed next state — ready-check redesign

**Partly superseded by named formats.** Its format half is settled and shipped, differently: a format is decided before signups open, one pod per format, each firing on its own count, with needs-based allocation splitting the players who joined more than one (section 1). What this section proposed instead — a set-agnostic slot whose format resolves at a T-10 ready check off a flashback vote — was rejected by players, who want to know what they signed up for. Read the rest for the parts named formats did not settle: the ready check as a seat-holding surface, team draft as the conversion of a stalled group, and the no-poaching rule. Ignore its format resolution.

The old flow assumed everyone wants the latest set and treated flashback as a sequential afterthought (fill the latest table first, then offer a second table). This strands the tail: on a 20-person night the first 16 seat cleanly into 8 latest + 8 flashback, and the last 4 fall through with nowhere to go. The redesign reframes the firing moment as **continuous matchmaking over ready players**, not a fixed table-1 / table-2 assignment.

### Principles

- **Continuous matchmaking, not batch optimization.** A group fires the moment it becomes viable and keeps other groups recruiting independently — not a single global allocation solved at T-10. The objective is to **maximize satisfactory tables, not seated players**: a 6-player Team Draft is a different experience, not a short pod, and only forms from people who actually want it.
- **Self-selection over a scoring solver.** For this scale the bot's job is to surface which groups are viable (live counts against thresholds) and fire them — not to compute an assignment. Humans self-balance better than an opaque weighted objective would, and self-selection makes "maximize satisfactory tables" fall out for free. No scoring optimizer.
- **Collapse flashback to one concrete set before the ready check.** Use the existing ranked flashback vote to resolve "which flashback" up front, so the ready check shows a small fixed set of buttons, never a menu of five sets at T-10.
- **Lazy per-group links, clean rosters.** Each group that fires gets its own bot-created Draftmancer session at fire time; the button clicks give the bot an unambiguous roster per session. Builds directly on today's lazy-link behavior and the `format_at_fire` seam.
- **No poaching.** "Any format" / "any draft type" players are offered as backfill to the group closest to firing; nobody is auto-moved out of a group they chose. Don't complete a 6-player team draft by yanking the would-be 8th from a pod that is waiting for them.

### Temporal layers

1. **Standing preferences (during the day)** — format interest, flashback ranking, and (optionally) draft-type lean. Signals for building candidate tables, all changeable, none binding.
2. **T-1h rally** — repost the roster with current tallies (how many lean latest vs flashback, the leading flashback set) so people can see the event is close to firing and update their real intent. Today only the underfill resurface and roster reminder exist here; the rally makes the tallies visible.
3. **T-10 ready check** — a "Ready Check" post with a small number of concrete **Join** buttons computed from confirmed preferences. The slot itself is **set-agnostic** ("Jul 22 Late Pod"); the format is resolved here, not at slot creation.

### The ready check

The post shows at most a couple of concrete buttons, each representing an independent group with a fire threshold:

- **Join — <latest set>** (fires at 8; falls back to swiss / team-draft conversion off the happy path).
- **Join — <winning flashback set>** (shown only when enough ready players are in reach of a table; hidden early in a set when nobody wants flashback).

Each button is its own lobby. When a button's ready count clears its threshold, that group fires: the bot creates the Draftmancer session then, spins the thread, and drops the clickers in. Other groups keep recruiting. A group stuck below 8 but at or above 6 past a short grace point can convert to a 6-player Team Draft if its members opt in — team draft is a **conversion of a stalled group**, not a permanent global preference.

This is the same button-hands-out-a-link idea from the original sketch, generalized: two live links only appear when the population actually supports two tables; otherwise it is one ready-check button and the second table is the existing overflow mechanic.

### Honest limits

The model **minimizes** stranding; it does not eliminate it. If four ready players each want four incompatible things, no algorithm seats them — and that is fine, because the daily cadence is the safety net. What it buys over today's rigid table-1 / table-2 assignment is that leftover players stay in the pool and can complete *any* group that needs a body, instead of being stuck behind a fixed assignment. Frame it that way; don't promise full seating.

### Open decisions

1. **Team draft at ready check** — a separate button from the start, or the emergent conversion of a stalled 6-7 group (leaning: conversion)?
2. **Multiple flashback tables** — when population is high, two flashback buttons (top-two voted sets), or always collapse to one winning flashback set and let overflow be a second table of the same set?

### What changes vs today

The `format_at_fire` seam already exists and currently always opens the latest set; the redesign makes it format-aware and lets a graduated slot resolve to a concrete format at the ready check. The set-agnostic session id (`LLU-<Mon>-<Day>-<rand4>`) already omits the set code, so a format decided at ready-check time does not desync the lobby. The second-table offer and the ranked flashback vote are the primitives the ready check composes; the main new piece is the ready-check surface that presents viable groups as buttons and lets each fire independently.
