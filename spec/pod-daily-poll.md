# Pod Draft On-Demand Scheduling — Daily Poll + Dynamic Queue

Status: built and committed after live iteration on the test guild. Two independent features sharing one bot-native creation path. Both go live with the deploy — feature flags were considered and rejected as overengineering; the launch gate is pushing to master.

Provenance: designed 2026-07-13 with the bot owner. Fills the gap between the fixed weekly slots (`bot/services/pod_schedule.py`) — Wed 20:00, Thu 14:00, Sat 15:00 ET — which leave Mon/Tue/Fri/Sun with no pod.

---

## Scope

Two ways for the community to spin up a pod on a day the weekly schedule doesn't cover:

- **Feature A — Daily poll (fixed slots).** A future-tense signal. Every Mon/Tue/Fri/Sun the bot posts a poll offering two fixed times (14:00 ET early, 20:00 ET late). A slot with 6 committed players fires a pod at that time. "I'll be there at 8" — the clock is the anchor, so nobody has to be online right now.
- **Feature B — Dynamic queue (present-tense).** A `/draft` command opens a live "who's around right now" queue. The instant 6 have joined, the bot creates the thread + Draftmancer lobby immediately. "I'm here now." Ported from Amelas/DraftBot's on-demand queue, minus the manual ready-check gate (our lobby ready-check already covers presence downstream).

Both features **create the thread + Draftmancer lobby** on threshold — they do not start the draft. Whether 6 people are actually seated and ready stays the job of the existing lobby fill + ready-check (`pod_draft_min_ready_players = 6`). A signal that never fills a lobby self-corrects there.

This does **not** cover (yet): a website surface, per-slot custom times, or waitlists.

### Robustness — this may replace sesh

Feature A is being built as a plausible permanent replacement for sesh as the scheduled-pod signup mechanism, so it holds itself to that bar:

- **One canonical RSVP surface, no dead copies.** The single sesh behavior the community disliked was a *forwarded thread embed that looked RSVP-able but wasn't* — a second copy of the signup card with no working controls. The interactive buttons live on exactly one message (the poll). Anywhere the pod is referenced elsewhere (the pod thread starter, an admin ping) uses a plain **jump link** back to that message — never a re-embedded look-alike with inert buttons. Discord's own "forwarded message" is never used for the RSVP card.
- **Restart-survivable.** Signals are DB-backed and views are persistent (static custom_ids); a bot restart re-attaches the buttons and re-arms every pending slot-open, expiry, and queue-teardown from the DB. No in-memory-only signup state.
- **Edit-in-place, idempotent.** Counts update by editing the one poll message. The daily post is idempotent per day; fire is one-way and guarded on `status='open'` so a double-click or a restart mid-fire can't create two pods for one slot.
- **Self-correcting, not admin-recovered.** A slot that never reaches 6 expires quietly; a fired slot whose lobby never fills is caught by the existing ready-check. No manual cleanup step in the happy path.

---

## How it works

Both features gather a **signal** (interested Discord users) on a message with buttons, and when a signal reaches the fire threshold (6) the shared launcher creates a bot-native pod. The only differences are when the signal is posted, what the button reads, and when the lobby opens relative to the fire.

```
                    poll (Feature A)              queue (Feature B)
 posted             11:00 ET cron, poll days      /draft, on demand
 signal semantics   future ("I'll be there")      present ("I'm here")
 buckets            2 (EARLY 14:00, LATE 20:00)    1 (queue)
 fires at           6 in a bucket                  6 in the queue
 lobby opens        slot_time − 10 min             immediately
 staleness          unfired slot expires at slot_time   180-min inactivity teardown
```

---

## Data model

One unified pair of tables. A daily poll is **two** `pod_signal` rows (EARLY, LATE) sharing a `message_id`, so each slot fires and expires independently. A queue is **one** row.

```
pod_signal
  id                UUID PK
  kind              TEXT NOT NULL              -- 'poll' | 'queue'
  bucket            TEXT NOT NULL              -- poll: 'EARLY' | 'LATE'; queue: 'queue'
  guild_id          TEXT NOT NULL
  channel_id        TEXT NOT NULL
  message_id        TEXT NOT NULL              -- the poll/queue message carrying the buttons
  signal_date       DATE NOT NULL
  slot_time         TIMESTAMPTZ NULL           -- fixed slot start (poll); NULL for queue
  status            TEXT NOT NULL              -- 'open' | 'fired' | 'expired'
  opened_by         TEXT NULL                  -- discord id of /draft invoker
  event_id          TEXT NULL FK pod_draft_events.id ON DELETE SET NULL  -- set on fire
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
  last_activity_at  TIMESTAMPTZ NOT NULL DEFAULT now()   -- reset on each join; drives queue teardown
  UNIQUE (message_id, bucket)

pod_signal_member
  id                UUID PK
  signal_id         UUID NOT NULL FK pod_signal.id ON DELETE CASCADE
  discord_user_id   TEXT NOT NULL
  display_name      TEXT NOT NULL              -- snapshot for roster + Draftmancer seeding
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
  UNIQUE (signal_id, discord_user_id)
```

Data model notes:
- A signal fires when its member count reaches the threshold and `status = 'open'`. Fire is one-way; a member leaving a fired signal does not un-fire it. A fired signal keeps accepting joins — over-signups cover unexpected drops and land in the roster the lobby pings; only an expired signal refuses.
- `event_id` links a fired signal to the pod it created, so the bot-native lobby-open reads the roster (with Discord ids for pings) back off the signal.
- Buttons carry static custom_ids (`pod_poll:EARLY`, `pod_poll:LATE`, `pod_queue:join`, `pod_queue:leave`) so persistent views survive a restart; the handler resolves the signal from `interaction.message.id` + bucket.

---

## Bot-native pod creation (shared)

The load-bearing new path. Today every `PodDraftEvent` is born from a detected sesh embed; `record_mock_event` already proves a sesh-less event works. This adds a `tournament`-kind equivalent and a sesh-less lobby-open.

`bot/services/pod_launch.py`
- `launch_from_signal(bot, signal_id, *, set_code, event_time, name, open_now) -> event_id` — names come from `ondemand_event_name_sync`: the standard `SET Pod Draft #N - date`, numbered after the set's highest existing pod (gaps against schedule-reserved numbers are fine).
  1. Create the thread in the pod-draft coordination channel (`pod_draft_channel_id`), where all pods live. An open-now pod gets a bare thread — the lobby-open post inside is the whole announcement; a scheduled pod anchors its thread on a message carrying the start time.
  2. `record_ondemand_event` — a `PodDraftEvent` with `sesh_message_id=NULL`, `kind='tournament'`, `socket_status='pending'`, its own `draftmancer_session`.
  3. Seed one participant per member (`seed_event_participants`) so player linkage/scoring works.
  4. `open_now=True` (queue): open the lobby right away and arm the manager's presence-based Team-Draft offer. Else (poll): arm an APScheduler date job at `event_time − 10 min` plus the at-start Team-Draft offer check, exactly like sesh pods.
- `open_ondemand_lobby(bot, event_id)` — the sesh-less analogue of `fire_reminder`: load roster + Discord ids off the linked signal, post the Draftmancer link and ping the roster, flip `pending → reminded`, call `start_manager(..., rsvps_yes=roster)`.

`fire_reminder` is **not** reused: it does `int(event.sesh_message_id)` and re-parses the sesh embed. `reschedule_pending_events` is guarded to skip `sesh_message_id IS NULL` (also fixes a latent mock-event crash); bot-native pending opens are re-armed by `pod_launch` on startup instead.

---

## Feature A — Daily poll

> Cadence and slot rules below are superseded by the 2026-07-14 consolidation amendment at the end of this doc (daily posting, day-dependent slots, reflected scheduled pods, lazy-slot nudge). The signal model, fire semantics, and bot-native creation path carry over unchanged.

`bot/tasks/pod_daily_poll.py`
- `init_daily_poll(bot)` — a cron job at 11:00 ET, `day_of_week='mon,tue,fri,sun'`, `SCHEDULE_TZ`. Runs through paused (release/championship) weeks by design — the poll is how pods stay alive when the fixed slots are off.
- `fire_daily_poll()` — idempotent per day (skip if a `poll` signal already exists for today). Posts the poll in `pod-draft-chat` and inserts two `pod_signal` rows; arms a per-slot expiry job at each `slot_time`.

The poll renders as two inline-field columns, one per slot, each headed by the slot role mention + localized time with signups blockquoted beneath; the pinging role mention rides as message content, since embeds never notify. Copy and layout live in `pod_daily_poll.build_poll_embed`.

Slot times: `slot_time = signal_date @ 14:00 ET (early)` / `@ 20:00 ET (late)`.

`PodPollView` (persistent): each pod button adds the clicker to that bucket and answers them straight off the write, with the embed re-render, the slot role grant and the Pod Drafters umbrella settled in a background task after; the board's own Leave button takes them off every pod on it. When a bucket hits threshold and is still open → launch with `open_now=False`, mark that row `fired` (rendered as a ✅ on the count; the slot keeps taking over-signups). At `slot_time`, an unfired slot flips to `expired` — enforced in the DB, so its button goes inert on click.

Slots fire **independently**: a hot day can produce both an Early pod and a Late pod.

---

## Feature B — Dynamic queue

`bot/commands/pod_queue.py`
- `/draft` (anyone) — posts the queue card in the invoking channel, auto-joins the caller, inserts one `pod_signal` row (`kind='queue'`), arms a teardown job at `now + 180 min`.

The queue message is a single Components V2 card (`PodQueueView` builds the open / fired / closed states): V2 text mentions notify, so the pinging `Pod Draft Queue` mention lives inside the card as its title instead of a bare content line above it.

`PodQueueView` (persistent):
- Join → add member, `last_activity_at = now`, reschedule teardown, grant the queue role + umbrella, re-render. At threshold → launch with `open_now=True`, mark `fired`; the card is left untouched until the thread exists, then a single edit keeps the roster and adds the native thread mention, buttons gone.
- Leave → remove member, re-render. The queue role stays — leaving one queue is not an unsubscribe.
- Teardown (`now + inactivity` with no new join) → mark `expired`, swap in the closed card.

Staleness follows DraftBot: no per-entry expiry, a single inactivity window (`pod_queue_inactivity_minutes = 180`) that resets on each join. **Always allowed** — no coexistence check against fixed slots or scheduled pods.

Almost-full nudge, also from DraftBot: when a join brings the queue to threshold − 1, the channel gets one `Pod Draft Queue` ping. Guarded by a 30-minute quiet window from queue open (a fast-filling queue never pings) and claimed atomically via `pod_signals.nudged_at`, so each queue nudges at most once.

---

## Pure logic — `bot/services/pod_signals.py`

Discord/DB-free, unit-tested:
- `POLL_WEEKDAYS = (MON, TUE, FRI, SUN)`; `is_poll_day(d)`.
- `slot_event_time(signal_date, bucket) -> datetime` — 14:00/20:00 ET.
- `should_fire(member_count, threshold) -> bool`.
- `teardown_at(last_activity, minutes) -> datetime`.
- `POLL_BUCKETS`, bucket labels/emoji/times.

---

## New files

```
bot/
├── services/
│   ├── pod_signals.py      -- NEW: pure slot/day/threshold logic
│   └── pod_launch.py       -- NEW: bot-native create + sesh-less lobby-open
├── tasks/
│   └── pod_daily_poll.py   -- NEW: 11AM cron + PodPollView
├── commands/
│   ├── pod_queue.py        -- NEW: /draft + PodQueueView
│   └── testpolls.py        -- NEW: owner `!test poll` / `!test draft` / `!test tip` drivers
└── models.py               -- add PodSignal, PodSignalMember
```

Changed: `bot/config.py` (threshold + inactivity knobs), `bot/main.py` (init + persistent views + startup re-arm), `bot/services/pod_drafts.py` (`record_ondemand_event`), `bot/commands/descriptions.py` (`POD_QUEUE`), `bot/listeners/sesh_listener.py` (guard `reschedule_pending_events`).

New migration: `pod_signal`, `pod_signal_member`.

---

## New config

```
POD_SIGNAL_FIRE_THRESHOLD=6
POD_QUEUE_INACTIVITY_MINUTES=180
```

Poll times (14:00/20:00 ET), post hour (11:00 ET), and poll weekdays are module constants, not env. They mirror the existing `pod_schedule.py` slot convention.

---

## Implementation order

1. Migration + `PodSignal`/`PodSignalMember` models; `alembic check` clean.
2. `pod_signals.py` pure logic + tests.
3. `record_ondemand_event` + `pod_launch.py` (create + sesh-less open); guard `reschedule_pending_events`.
4. Feature A: `pod_daily_poll.py` + `PodPollView`.
5. Feature B: `pod_queue.py` + `PodQueueView`.
6. Wire `main.py` (init, `add_view`, startup re-arm).
7. `!test poll` / `!test draft` (owner-only, in `testpolls.py`) post the live surfaces in the current channel, reusing the production builders and views so clicking drives the real add/remove/fire path.

Exercising over automated tests: the two `!test` commands drive every user-facing surface (poll look, slot buttons, counts, fire, queue join/leave, teardown copy). Set `POD_SIGNAL_FIRE_THRESHOLD=1` to reach a fire solo. No pytest suite — the design is expected to move after review, and pinned tests would fight that.

---

## Out of scope

- Website surface for polls/queues.
- Custom or per-signal times. (Fixed two-slot rule relaxed by the 2026-07-14 amendment: weekends carry three slots.)
- Waitlist / auto-second-pod split (Phase 2's deferred idea).
- Coexistence suppression between the queue and scheduled pods. (The poll↔scheduled-pod relationship is now in scope as *reflection* — see the 2026-07-14 amendment — but the queue stays independent.)

---

## Amendment 2026-07-14 — Daily launcher + reflected scheduled pods

Status: agreed with the owner 2026-07-14, not started. Supersedes Feature A's cadence and slot rules above; leaves Feature B (queue) and `spec/pod-scheduled-rsvp.md` structurally intact.

Why: the poll, the scheduled RSVP cards, and the queue are the same `pod_signal` + card tail at three commitment levels, but players met two different UIs depending on the day. This promotes the poll to the single day-of surface and folds the locked pods into it, so a scheduled pod and its day's poll slot are two live windows on one roster.

### Three tiers

- **Scheduled cards (Wed/Thu/Sat)** — locked, sent >48h out, on people's calendars. `spec/pod-scheduled-rsvp.md`, unchanged.
- **Daily Pod Launcher** — on-demand, the day-of "who's playing today" heartbeat. Posts every day.
- **Queue (`/draft`)** — right-now, aggressive ping-hunting. Feature B, unchanged.

### Cadence and slots

The poll cron moves from `mon,tue,fri,sun` to every day. `POLL_WEEKDAYS` / `is_poll_day` retire; the slot set and the post time both become a function of the signal date, resolved in `pod_signals`:

- **Weekday (Mon–Fri):** posts 11:00 ET. Slots Early 14:00, Late 20:00 → Early Pod / Late Pod roles.
- **Weekend (Sat–Sun):** posts 08:00 ET (earlier so the 10:00 slot has runway — an 11:00 post would land after Morning's slot time). Slots Morning 10:00, Afternoon 15:00, Evening 20:00 → Weekend Pod role for all three (role and mention already exist in `pod_schedule.py`).

`POLL_BUCKETS` and `POLL_POST_HOUR_ET` become date-dependent; the bucket→role map gains the weekend buckets pointing at Weekend Pod. Slots still fire independently.

### Reflection of locked pods — the load-bearing behavior

On a day whose slot time matches a locked scheduled pod, the poll slot does not open a fresh signal — it **binds to the existing scheduled `pod_signal`** (already fired, event linked). One roster, two live surfaces; never a duplicate, never an inert lookalike (the one-canonical-surface rule from `spec/pod-scheduled-rsvp.md` holds because both surfaces are live and edit the same signal).

- The poll message records, per slot, the bound `signal_id`: an existing scheduled signal for reflected slots, a freshly created lazy poll signal otherwise.
- Rendering reads the bound signal — live count, thread link, and the pod's **real** start time (a reflected slot shows its actual time, not the bucket default).
- Poll join maps to the scheduled card's Yes (live join). Maybe/No stay on the rich card; the poll is a binary in/out day-of surface.
- Mapping: Wed 20:00 → Late, Thu 14:00 → Early, Sat 15:00 → weekend Afternoon. Saturday stays at 15:00 (no calendar/native-event change) and now coincides with the Afternoon bucket, so the old time-vs-bucket mismatch disappears.
- Binding resolves by looking up a scheduled event at the slot instant at poll-post time; a lazy slot that would otherwise fire also checks for an existing event first, so a late-created scheduled pod can never be doubled.

### Lazy-slot nudge

A poll slot with **no linked event yet** nudges once at threshold−1, pinging its slot role (targeted, not channel-wide), behind a quiet-window guard — mirroring the queue's `_maybe_nudge`. Reflected/locked slots already carry an event, so the scheduled-pod underfill nudge owns those; the poll nudge is gated on "no event" so the two never double-ping.

### Notification polish (2026-07-14 clarity audit)

When the system advances a pod's state, it should carry the already-opted-in players with it:

- Poll slot graduation preseeds and pings its signups; a reschedule pings the Yes roster with the new time.
- A failed slot launch surfaces a notice instead of silently reopening.
- The lobby-open body becomes one shared builder (today duplicated across `pod_draft_reminder` and `pod_launch` with divergent headlines).
- The queue card gains a live "opened `<t:…:R>`" age line (DraftBot parity), sourced from `PodSignal.created_at` via `SignalState`.

### Touched surfaces

`pod_signals` (date→buckets, weekend roles), `pod_daily_poll` (daily cron, reflection binding, lazy nudge), `pod_launch` (`SignalState.created_at`; scheduled-signal lookup by instant), `pod_rsvp` (reschedule ping), `pod_queue` (opened-age line, poll/queue naming), and one shared lobby-open builder. Copy lives in those modules, not here.

### Still out of scope

Website surface, waitlists, auto-split past 8, and any change to the queue's independence.
