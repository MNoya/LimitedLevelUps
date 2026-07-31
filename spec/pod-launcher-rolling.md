# Pod Launcher — Rolling Signups

Design for turning the Daily Pod Launcher from a board that goes stale every afternoon into an always-living, always-forward-looking surface, without adding a multi-day scheduling machine. The core move is **per-slot rolling**: each slot on the launcher carries its own date and rolls forward to the next day the moment its pod finishes, so the board is never lying about a pod that already happened and there is never a dead window where interest is lost.

Sits on top of `spec/pod-workflow.md` (engineering map) and `spec/pod-coordination.md` (player guide). Copy lives in code (`bot/commands/messages.py`, `bot/services/pod_reminder_copy.py`), never here — the mocks below are illustrative layout, not final strings. Modules referenced: `bot/tasks/pod_daily_poll.py`, `bot/services/pod_launch.py`, `bot/services/pod_signals.py`, `bot/tasks/pod_draft_reminder.py`, and the pod-completion path that posts the standings/championship embed.

## The problem this solves

Today one launcher message is posted once a day at 11:00 ET (`fire_daily_poll` → `post_launcher`) with two slots (Early 14:00 ET, Late 20:00 ET), edited in place all day, and only retired at the *next* morning's post (`close_recent_launchers`). Two things fall out of that:

1. **The board lies once the day is spent.** After both pods play, the launcher keeps showing both slots as live and joinable all evening and overnight. Clicking Early at 21:00 adds you to a slot whose 14:00 start already passed and confirms "added." A fired-and-finished slot also reads the same as an in-progress one — `✅` covers both.
2. **There is no way to say "I'll play tomorrow."** Signups only target today and only exist after 11:00. From the last pod finishing until the next 11:00 post there is a multi-hour void where interest cannot be expressed and is simply lost.

The goal is an **always-living calendar**: at any hour, clicking a slot does something sensible and forward-looking, and expressed intent carries forward instead of resetting to zero every morning.

## Guardrails (what would be over-engineering)

Pod philosophy is non-binding clicks, self-correction, and the daily cadence as the safety net (`project_pods_always_public`, `feedback_robust_over_admin_recovery`, and the "simplify, don't extend" framing in `spec/pod-handoff.md`). The rolling calendar stays inside that:

- **One day of lookahead, not N.** A slot is ever only "its current day" or "the next day." No named-day scheduling, no recurring subscriptions, no week view.
- **Still non-binding.** A tomorrow signup is a click you can drop, same as today.
- **Reuse existing seams.** The lazy-signal / message-binding split, the poll→card roster carry-over, and the `socket_status` lifecycle already exist. Rolling composes them; it does not add a parallel state machine.

## Where signups live

The database is the source of truth. `PodSignal` (the slot / interest surface) and `PodSignalMember` (one row per user per signal, carrying RSVP and format interest) are SQLAlchemy models in `bot/models.py`, stored in Postgres. The launcher embed is rendered from a DB snapshot on every render (`launcher_snapshot_sync`); the Discord message is a view, never the truth. This is what makes pre-created signals and carry-over free: the roster exists in the DB whether or not a message is bound to it, and it never has to be copied between messages. (The one deliberate exception elsewhere in the system is the in-lobby Format Vote, whose tally is stored in its own message embed and read back — not relevant here.)

## The model — per-slot rolling

"Which day" is a property of each **slot**, not of the board. The board still shows exactly two slots (Early, Late), but each column shows its own date and walks its own lifecycle independently:

```
Early column:  Day-N open → fired → pod plays → pod finishes ──flip──► Day-(N+1) open → …
Late  column:  Day-N open → fired → pod plays → pod finishes ──flip──► Day-(N+1) open → …   (independent)
```

So a mixed-date board is normal and expected: Early can already be collecting for tomorrow while Late is still playing today. This keeps the always-forward-looking property of a dual-day board while showing only one date per column, so the surface never grows past two slots.

### Flip triggers

A column rolls to the next day when its current-day pod reaches a terminal state:

- **Finished pod (the normal case).** When the pod completes and its standings/championship embed is posted in the channel, flip the column **immediately** to the next day. The finished pod is already documented by its own standings post and thread in the channel, so the flipped column does not need to carry a "completed" link — it flips cleanly to the next day's empty (or pre-seeded) roster.
- **Expired slot with no thread (the never-fired case).** If a slot's start time passes and it never fired (no pod, no thread), roll it to the next day too, rather than showing a closed/expired slot. Presence of a thread/pod link is what distinguishes "fired" from "never fired" (see the note below).

### The "play again" thread CTA

~5 minutes after the standings/championship post lands (enough that it is not on top of the final game), post a one-click CTA into the finished pod's thread that signs the clicker up for **the same slot on the next day**. This hits exactly the players who just finished, at the moment they would decide to come back. It writes a `PodSignalMember` onto the next day's pre-created signal — the same primitive a launcher tomorrow-click uses — so it is nearly free. The launcher column has already flipped to the next day by this point, so a click here shows up there.

### Carry-over by adoption (pre-created signals)

The click made "for tomorrow" has to survive until tomorrow's board exists. It does, because signal and message are decoupled:

- On flip, **pre-create the next day's signal** for that slot. Launcher tomorrow-clicks and the thread CTA attach members to it right away.
- The 11:00 post no longer unconditionally creates fresh signals — it **adopts** the existing next-day signals (binds a new message id) when they are present, and creates them only when absent. `create_poll_signals_sync` becomes idempotent adopt-or-create per (slot, date).

Because the fresh morning post binds to the same DB signals the flipped columns were already writing to, the carry-over is automatic: nothing is copied, the rosters never move, and the count on the fresh board is whatever accumulated overnight — not zero.

### Firing gate — hold and show

Pre-day signups **must not fire early** just by reaching the threshold the night before. A slot becomes eligible to fire only once its own date is the active board day. Concretely: at the 11:00 relabel/adopt, re-check thresholds and graduate any slot already at or above the fire threshold; before that, overnight signups accumulate and are shown but do not fire. So a popular slot can be confirmed at 11:00 (a few hours before its start) but never at 22:00 the night before.

### The morning post

The morning ET post stays as the daily anchor, and its job in this model is: **repost fresh at the bottom of the channel (resurface), relabel the rolled columns' identity for the new day, retire the prior message, and run the firing-gate re-check.** The retired message is edited to its terminal state with the footer `🔒 Signups Closed` and no buttons (`close_launcher_for_date`), unchanged from today.

### Reposting on a lane transition

The board is posted once and edited in place from then on, so it sinks as the day fills the channel with pod cards, threads, reminders and results, and the freshest thing there is a pod that already played. So the board reposts itself on each lane transition: same primitive, run early, silent, and below everything the pods left behind.

**After the early pods** it resurfaces **the same day**, because the late column is still gathering and the day still needs the board it has. The rows move onto the new message and the old message is deleted. This is the stretch the players who matter are in: the late pod is the one still recruiting, and until now it recruited from a board posted before lunch and buried since.

**After the late pods** it posts **the next day's** board, carrying only that day's rows, and the message it replaces is retired in place as that day's `### On This Day` card.

Strictly on a transition, and once each. An early pod still playing holds neither, and a night whose late slot never fires leaves the morning post to do its normal job. The next day's board existing is the claim on the evening one; for the afternoon one it is the board's own post time, which sits before the early slot until the resurface moves it after.

Two changes fall out of this. The morning post no longer skips when a board for today exists — it reposts and deletes the one it replaces, because the day's ping belongs on a board at the bottom of the channel, not on a line pointing up at one from last night. And neither repost runs a graduation pass: a slot that filled before its day arrived would otherwise post its card hours early.

The rows a repost must carry are not all the day's own. A lane rolls forward the moment its pod finishes, so by the afternoon transition the early column is already gathering for tomorrow on a row dated tomorrow. `create_poll_signals` adopts by day and would miss it, so a same-day repost rebinds every poll row on the old message to the new one (`rebind_launcher_rows_sync`).

Note on the global community: 11:00 ET is ~1:00 AM next-day in eastern Australia and around midnight in Japan, so the repost lands in the small hours there. This is acceptable and unavoidable for any single global post time, and low-stakes here precisely because the roll is continuous — players in those zones have been accumulating on the rolled columns since their previous evening and do not wait on the 11:00 post to act.

## Launcher render redesign

The current header (`💫 @Early Pod 3:00 PM (16) ✅`) is replaced. The `✅` is dropped entirely — it was a redundant and imprecise second "fired" signal. Each slot column reads:

```
💫 @Early Pod (16)
Friday, July 24, 2026 at 3:00 PM
:msh: @Latest Set (11)
🔗 <pod link>            ← present only once the slot has fired; sits under the playing format
› player
› ◈ flexible player
:flashback: @Flashback (5)
› player
```

- **Line 1** — bucket emoji, slot role mention, total count across formats.
- **Line 2** — the full slot date-and-time as a Discord timestamp (`<t:…:F>`), so it renders in each viewer's own timezone.
- **Format sub-groups** — the latest group carries the active set's own symbol emoji (e.g. `:msh:`); flashback carries a generic flashback emoji until a specific set is resolved. Flexible players keep the `FLEXIBLE_MARKER` glyph.
- **Fired signal** — the pod link line. Present ⇒ the slot fired and this is its pod; absent ⇒ still gathering. Replaces `✅`.

### Buttons are timezone-safe by staying plain

A button label is static text — it renders identically for every viewer worldwide, so it can carry no date or relative-day word without being wrong for someone (an Asia player's "Jul 24 3 PM ET" is their Saturday morning). All day/date information lives in the localized timestamp line instead. Per-slot rolling guarantees exactly one Early and one Late slot are live at any moment (a column is either its day or the next, never both), so there are always exactly two join buttons, each spatially paired with one dated column. The buttons therefore stay `Early Pod` / `Late Pod` with no date, and the localized date line disambiguates which instant every viewer is joining. A committed (fired) slot keeps its button: it signs the presser up on the pod's card. Every pod button only adds, and the board carries one Leave that takes the presser off all of them.

### Title date

The launcher title keeps a date, because old launchers are never deleted and need a stable identity in channel history. The rule: **the title date is the day the launcher was posted, fixed for the life of that message; the per-column dates are the live slot instants and may roll forward past it.** So a board posted on Jul 23 stays titled `Daily Pod Launcher — Jul 23` even after its Early column flips to Jul 24, and the fresh Jul 24 board (a new message) carries the Jul 24 title. The title date is static ET text — a label, not a localized time to act on.

## Worked timeline (viewer's local time)

```
12:00 PM Jul 23  Launcher — Jul 23 posts; both columns Today (Jul 23).

~5:35 PM         Early pod finishes → standings/championship post lands in channel.
~5:40 PM         "Play again — next day" CTA posts in the Early thread;
                 Early column flips to Jul 24 and starts accumulating.
                 Late column still Jul 23.

~11:40 PM        Late pod finishes → standings post → CTA → Late column flips to Jul 24.
                 Both columns now Jul 24, accumulating overnight (held, not fired).

12:00 PM Jul 24  Fresh Launcher — Jul 24 reposts at the bottom, adopting the pre-created
                 Jul 24 signals (counts carried over from CTAs + launcher clicks, not zero);
                 firing-gate re-check graduates any slot already at threshold;
                 Jul 23 message retired to 🔒 Signups Closed.
```

## Decisions locked

1. **Flip immediately** at pod completion; the thread CTA fires ~5 min after the standings/championship post.
2. **Hold and show** overnight signups — they fire only at the 11:00 relabel, never the night before.
3. **Roll an expired slot** (start passed, never fired, no thread) to the next day rather than showing it closed.
4. **Carry over by adoption** — the fresh 11:00 post binds to the pre-created next-day signals, so launcher and thread-CTA signups both persist with no copying.
5. **Render**: drop `✅`; new column layout with full localized date line; pod link is the fired signal; plain timezone-safe buttons; title date = posting day.
6. **Footer** on a retired launcher stays `🔒 Signups Closed`.

## To validate during build

- **"Thread/pod link ⇒ fired" as the only fired signal.** True in today's flow (fire → graduate → card + thread), but a fire that fails to create its thread would break the equivalence. Confirm the fire path always produces the link before relying on its absence to mean "still gathering," or key the fired state off `PodSignal.status` / `event_id` and use the link only as the visible affordance.
- **Idempotent adopt-or-create** in `create_poll_signals_sync` — the morning post must never double-create a signal that a flip already pre-created, and must still create one for a slot that never rolled (e.g. a day with no pods the day before).
- **Flip hook site.** Identify the exact point in the pod-completion path where the standings/championship embed is posted, and attach the column flip + scheduled CTA there.
- **Expired-with-no-thread detection** vs a slot that fired but whose pod is still mid-rounds — the roll must not fire while a pod is in progress.
- **Weekend/role mapping across a weekday→weekend boundary** — a slot rolled from Friday to Saturday must re-resolve to the weekend ping-role variant at render, since roles resolve by weekday + time-of-day.
