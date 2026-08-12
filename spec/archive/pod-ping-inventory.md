# Pod ping inventory

Living reference for every notification the pod-draft system sends: what fires it, when, who it reaches, and the knob that tunes it. The goal is one place to see the whole notification surface so we can refine and configure it without spelunking. Copy strings are not reproduced here — this tracks *behaviour and configuration*; the wording lives in the modules named per row and follows the plain-declarative rule.

Status tags: **live** (in production), **built** (launcher-convergence work, in the tree but uncommitted), **changed** (reworked by the nudge redesign, step 1).

## Role vocabulary

The roles that get mentioned, and how they differ (easy to conflate):

- **Slot roles** — `Early Pod`, `Late Pod`, `Weekend Early Pod`, `Weekend Late Pod`. Time-of-day recruiting roles a player opts into to hear about pods at hours that suit them, split so a player never gets pinged for a slot at an hour they don't want (an EU player takes the daytime roles and skips the two 20:00 ET slots). This is who the recruiting pings target. Managed in `/roles`. Auto-granted on RSVP (`auto_grant=True`).
- **Bucket role** — *not a separate role*. The daily launcher's lazy slots are called "buckets" in code (`EARLY`, `LATE`, `MORNING`, `AFTERNOON`, `EVENING` — `bot/services/pod_signals.py`), and each bucket carries a `role_name` that resolves to one of the slot roles above. So "bucket role" is just "the slot role attached to this launcher bucket." The buckets map many-to-one onto the slot roles — see the mapping below.
- **Pod Draft Queue** — a broad "tell me when there's day-of pod activity" role, distinct from the slot roles. Pinged by the daily launcher post and the on-demand queue nudge, never by the time-anchored rally. **Opt-in only** (`auto_grant=False`): joining a `/draft` queue no longer subscribes you — you take it in `/roles`.
- **Pod Drafters** — the umbrella membership role every player who has ever drafted holds. It is not a recruiting ping target; it appears only in the first-pod welcome.

### Bucket → slot-role mapping (`bot/services/pod_signals.py`)

| Bucket | Start (ET) | ~CET | Slot role | Note |
|--------|-----------|------|-----------|------|
| EARLY (weekday) | 14:00 | 20:00 | Early Pod | EU-friendly |
| LATE (weekday) | 20:00 | 02:00 | Late Pod | EU late-night |
| MORNING (weekend) | 10:00 | 16:00 | Weekend Early Pod | |
| AFTERNOON (weekend) | 14:00 | 20:00 | Weekend Early Pod | bucket is *named* "Early Pod" |
| EVENING (Sunday) | 20:00 | 02:00 | Weekend Late Pod | bucket is *named* "Late Pod" |
| SATURDAY_EVENING | 21:00 | 03:00 | Weekend Late Pod | Saturday's late lane runs an hour later |

Weekend now splits daytime (Morning + Afternoon → Weekend Early Pod) from evening (Weekend Late Pod), mirroring the weekday Early/Late split, so a weekend subscriber is no longer force-pinged for the 20:00 ET (~02:00 CET) slot. A dedicated Weekend Morning role was deferred — that 10:00 ET slot has not fired yet, so Morning folds into Weekend Early for now.

`slot_role_name_for_event_time` (`pod_signals.py`, keyed on the buckets above) is the single role resolver: the T-1 rally reads it too, so every real slot — weekly or launcher, weekday or weekend — resolves to its slot role. The old `WEEKLY_SLOTS`-keyed `slot_for_event_time` is deleted.

## The pings

### Recruiting family — "this pod still needs people"

Public, time-anchored where possible, targeted at a slot role. Governed by the "never ping far from the draft time" rule.

| Ping | When | Reaches | Sound | Knobs | Code | Status |
|------|------|---------|-------|-------|------|--------|
| **T-1h rally** | 1h before a scheduled/launcher pod, only when close (needs ≤ `close_gap` to reach the aim: 8 for a card, 6 for an unfired slot) | slot role for the pod's time | ping | `pod_underfill_check_hours` (3,2,1), `pod_underfill_ping_hours` (1), `pod_underfill_ping_close_gap` (2), `pod_draft_target_players` (8) | `bot/tasks/pod_underfill.py` `_nudge_ping_role` | changed |
| **T-3h / T-2h silent nudge** | 3h out (2h catch-up for short-notice pods); posts the living recruiting message with no ping | pod-draft-chat, no mention | silent | same `pod_underfill_check_hours` | `bot/tasks/pod_underfill.py` `fire_underfill` | changed |
| **Launcher slot nudge** | the same T-3/T-2/T-1 beats while a slot is unfired, aiming at the fire floor and linking to the launcher; an empty slot stays silent; cleared when the slot fires or expires | slot role, T-1 only when close | silent, T-1 may ping | `pod_signal_fire_threshold` (6) + the shared underfill knobs | `bot/tasks/pod_underfill.py` `fire_slot_underfill` | built |
| **Launcher creation announcement** | when a launcher slot fires within `max(pod_underfill_check_hours)` of its time; numberless, so it can't go stale; an earlier fire posts the card silently | slot role, as the card's content line | ping | window derived from `pod_underfill_check_hours` | `bot/tasks/pod_daily_poll.py` `_fire_announcement` | built |

Note the T-3/T-2 nudge is not itself a *ping* — it is the silent living message that the T-1 rally later resurfaces and may ping on. It is listed here because it is the same message.

Every T-1 rally ping is claimed on `pod_signals.last_call_pinged_at` (`claim_last_call_ping_sync`), so a pod pings its slot role at most once even across restarts and catch-up beats; the queue's one-short ping claims `one_more_pinged_at` the same way. Sesh-born pods carry no signal and ping unclaimed.

### Broad day-of family — "there's pod activity today"

Targeted at `Pod Draft Queue`, not the slot roles.

| Ping | When | Reaches | Sound | Knobs | Code | Status |
|------|------|---------|-------|-------|------|--------|
| **Daily launcher post** | once per day, 11:00 ET weekdays / 08:00 ET weekends | Pod Draft Queue (opt-in holders) | ping | `WEEKDAY_POST_HOUR_ET` (11), `WEEKEND_POST_HOUR_ET` (8) | `bot/tasks/pod_daily_poll.py` `poll_ping_line` | live |
| **Queue nudge** | once, when an on-demand `/draft` queue is one short of firing, after a quiet window; silent if it fills fast; claimed on `one_more_pinged_at` | Pod Draft Queue (opt-in holders) | ping | `pod_signal_fire_threshold` (6), `QUEUE_NUDGE_QUIET_MINUTES` (30) | `bot/commands/pod_queue.py` `_maybe_nudge` | copy cleanup pending (step-3) |

### Get-ready family — "it's on, get in" (once a pod is happening)

Targeted at the confirmed roster, in the pod's own thread. Untouched by the nudge redesign.

| Ping | When | Reaches | Sound | Knobs | Code | Status |
|------|------|---------|-------|-------|------|--------|
| **T-60 roster reminder** | 60 min before start | in-thread, lists Yes + Maybe | **silent** | `ROSTER_REMINDER_LEAD_MIN` (60) | `bot/tasks/pod_draft_reminder.py` `fire_roster_reminder` | live |
| **T-10 lobby reminder** | 10 min before start (or on early-open) | the Yes + Maybe attendees, mentioned **individually** (not a role) | ping | `REMINDER_LEAD_MIN` (10) | `fire_reminder` / `open_ondemand_lobby` | live |
| **Lobby-open DM** | at lobby open | each attendee on the default-on DM preference | DM | opt out via `/roles` | `bot/services/pod_link_dm.py` | live |

### Membership — "welcome"

| Notice | When | Reaches | Sound | Code | Status |
|--------|------|---------|-------|------|--------|
| **First-pod welcome** | the first time a player ever joins a pod, if their Arena handle is not linked | public post in pod-draft-chat, mentions the newcomer as the subject | ping (the newcomer) | `bot/services/ping_roles.py` `announce_pod_grant` → `post_welcome` | live |
| **Returning slot grant** | a returning drafter freshly picks up a slot role | the joiner only, **ephemeral** — not a ping, no public post | none | `announce_pod_grant` → ephemeral followup | live |

The returning grant is deliberately silent and self-only; only the once-ever first-pod welcome is public. Queue joins fold no role into the welcome any more — with Pod Draft Queue opt-in, a queue first-timer gets the generic welcome that points them at `/roles`.

## Configuration knobs (defaults)

All on `Settings` (`bot/config.py`) unless marked as a module constant.

- `pod_draft_target_players` = 8 — the recruiting aim; drives the "looking for N more" count and the ready flip.
- `pod_signal_fire_threshold` = 6 — the floor a launcher slot / queue must reach to fire.
- `pod_underfill_check_hours` = "3,2,1" — the rally beats (T-3 silent, T-2 catch-up, T-1 resurface + ping).
- `pod_underfill_ping_hours` = "1" — which of those beats may ping the slot role.
- `pod_underfill_ping_close_gap` = 2 — the T-1 rally pings only when the pod needs at most this many more to reach the aim.
- `WEEKDAY_POST_HOUR_ET` = 11, `WEEKEND_POST_HOUR_ET` = 8 (`pod_signals.py`) — daily launcher post time.
- `ROSTER_REMINDER_LEAD_MIN` = 60, `REMINDER_LEAD_MIN` = 10 (`pod_draft_reminder.py`) — get-ready lead times.
- `QUEUE_NUDGE_QUIET_MINUTES` = 30 (`pod_queue.py`) — quiet window before the queue's one-short nudge may fire.

The launcher-slot knobs `pod_nudge_in_chat` and `POLL_NUDGE_QUIET_MINUTES` are gone with the count-triggered slot nudge; slot nudges always land in pod-draft-chat on the shared beats.

## Rollout on deploy (weekend split)

The split is committed. On the deploy that ships it: `reconcile_ping_roles` creates the two fresh roles (`Weekend Early Pod`, `Weekend Late Pod`) on startup, leaving the old `Weekend Pod` role orphaned (no bucket points to it). Then run the owner command `!migrate-weekend-roles`, which splits holders by their weekday preference: a member on both `Weekend Pod` and `Early Pod` gains `Weekend Early Pod`; on `Weekend Pod` and `Late Pod`, `Weekend Late Pod` (both if they hold both). Weekend-only and weekday-only members are left untouched. Idempotent. After it reports clean, delete the dead `Weekend Pod` role by hand.

## Open questions / to refine

- **T-60 coincidence:** the T-1h rally and the T-60 roster reminder both land an hour out. They differ in audience and place (public slot role + only-when-short vs in-thread + silent), so no conflict, but they arrive together.
- **Empty launcher slots stay silent:** the slot beats skip a slot with zero signups — there is no pod-in-waiting to rally around, and a daily "looking for 6 more" per empty slot would be noise. Revisit if empty slots should get one silent T-3 line anyway.
