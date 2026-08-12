# Pod Poll — Onboarding Tip + Configurable Slots

Status: Feature 3 and the Feature 4 role changes are built (staged with the poll/queue work). Data-driven slot config is deferred — the queue already covers the dynamic case; revisit if slot times ever need tuning.

---

## Feature 3 — First-contact pod tip

The pod guide is the reference doc, but a first-time signer-up on a poll or queue gets no inline sense of what happens next. The JDG server leans on veterans telling newcomers "just react and show up." A one-time inline nudge covers that without a wall of text.

Behavior:
- The first time a Discord user ever appears in a pod signal, their button click also sends a short **ephemeral** tip. Every later signup is the normal silent toggle.
- "First contact" = that discord id has no prior `pod_signal_member` row and no prior `pod_draft_participants` row. One-time, self-clearing, no new table.
- Ephemeral, so it never clutters the channel and never pings anyone.

Tip copy (plain, functional): what a pod is, that a slot is a set time so they don't need to be free right now (poll) or that a queue fires as soon as it fills (queue), where the lobby shows up (the thread plus the Draftmancer link), and a link to the pod guide.

Cost: one `has_drafted_before(discord_id)` helper plus one ephemeral follow-up in each view handler. Value: fewer "what do I do now" questions, smoother first pod.

---

## Feature 4 — Configurable slots + per-slot ping role

Today `POLL_BUCKETS` is a hardcoded tuple (EU 15:00, NA 20:00) and the slot roles are constants. Make a slot data-driven so times, count, days, and ping role are tunable without a code edit.

One entry per slot:

```
key         'EARLY' | 'LATE' | …
label       '2PM ET'
emoji       '☀️'
start       time(14, 0)          # ET
ping_role   'Early Pod'          # resolved by name via find_role
weekdays    (MON, TUE, FRI, SUN) # which days this slot is offered
```

Source: a single constants block to start (simplest), promotable to env/JSON if per-deployment tuning is ever needed. Roles are resolved by name (a mod creates the role, no id in config), matching the existing `find_role` pattern.

### Ping roles

Five roles, named by their time slot. Geography would mislead: a European drafting the 8PM ET slot at 1AM makes "Americas" wrong. The slot roles use the short `X Pod` pattern — repeating "Drafters" four times made the `/roles` menu a wall; the umbrella keeps the established `Pod Drafters` name and the queue names its mechanism.

| Role | For |
|---|---|
| `Pod Drafters` (umbrella) | whole-server announces, not per-event |
| `Early Pod` | 2PM ET slot, scheduled or off-day (renames `Euro Pod Drafters`) |
| `Late Pod` | 8PM ET slot, scheduled or off-day (splits off the umbrella) |
| `Weekend Pod` | weekend pods (renames `Weekend Pod Drafters`) |
| `Pod Draft Queue` | spontaneous `/draft`, pinged aggressively |

Time roles are preferences ("I like the 2PM slot"), so they apply on any day and the off-day poll needs no separate role. No `Bonus` / `Off-Day` / `On-Call`.

Ping policy:
- **Poll announce** pings `Pod Draft Queue` via a content line that also plugs `/draft`; the Early/Late roles are granted on slot click instead of pinged.
- **Queue open** pings `Pod Draft Queue` (wired in `pod_queue.py`; the startup reconcile creates the role).
- Renaming `Euro` to `Early` keeps every current member (Discord changes only the display name). Splitting `Late` out of the umbrella moves the existing Wed 20:00 weekly slot's mention off `Pod Drafters`, so it touches `pod_schedule.py` (`CREATE_MENTIONS`).

### Role reconcile + one-time Late migration

Role changes ride the existing `ping_roles.PING_ROLES` reconcile (creates missing, renames in place via `aliases`, recolors), so no manual server edits:
- Rename: `Early Pod` with aliases `Early Pod Drafters` / `Euro Pod Drafters`; `Weekend Pod` likewise.
- Add: `Late Pod`, `Pod Draft Queue` as new `PingRole` entries (appear in `/roles`).
- Untangle: `Pod Drafters` becomes a pure umbrella, so the Wed 20:00 slot's ping moves to `Late Pod`.

Plus `!grant-late`, a one-time owner command that grants `Late Pod` to every current `Pod Drafters` member (idempotent via `grant_role`), so the new role starts populated instead of empty.

---

## Open questions

- Slot config, if ever built: constants block (simplest) or env/JSON (per-deploy tunable)? Leaning constants.
