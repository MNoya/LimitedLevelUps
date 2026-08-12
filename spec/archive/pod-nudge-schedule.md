# Pod nudge & reminder schedule

How the bot tells players a pod still needs people. This is the design intent behind the recruiting nudges; the copy itself lives in code (`bot/services/pod_schedule.py`, `bot/tasks/pod_daily_poll.py`, `bot/tasks/pod_underfill.py`, `bot/commands/pod_queue.py`, `bot/commands/messages.py`) and follows the plain-declarative rule. Nothing here is a string.

## Pod types

The three types differ under the hood but stay mostly transparent to players.

- **Scheduled** — created in advance: a sesh event, a weekly RSVP card from the Monday schedule poster (`bot/tasks/pod_schedule_post.py`), or a `/draft` scheduled for later. Born as an RSVP card with a fixed start time. The weekly "Week N" schedule message still auto-posts every week; the `/pod-schedule` preview command has been removed.
- **Launcher** — a same-day daily-launcher slot. A lazy slot that *fires* into a Scheduled card once it reaches the floor. For recruiting it behaves exactly like a Scheduled pod; the only difference is that it starts life as a slot and creates its card on the fly.
- **Queue** — an on-demand `/draft` queue with no scheduled time. Handled the DraftBot way and out of scope for the time-anchored rules below.

## Two numbers

- **Floor = 6** (`pod_signal_fire_threshold`) — the minimum to actually run a draft (a team draft). A Launcher slot fires (creates its card, opens the lobby path) the instant it reaches the floor. A Scheduled pod runs at its start time with the floor or more; below the floor at start time the players decide whether to cancel (the bot always opens the lobby because the thread exists).
- **Aim = 8** (`pod_draft_target_players`), soft-capped by the lobby Max Players control (8 or 10). This is the recruiting aim, not a go/no-go and not a hard ceiling.

## What "aims for N" means

Aiming governs recruiting and framing only:

1. The count in the copy — "looking for X more" where X = N − current.
2. When the pod stops asking — reaching N flips it to **ready** and it goes quiet.

Aiming does **not** decide whether the draft happens (the floor does), and **ready is not full**: the pod stays open past the aim up to the Max Players cap, and further joins spill to a second table. A ninth player is never turned away. Past the aim the message says so, because a pod sitting on exactly 8 is one drop away from 7 and the organizer should not have to talk it back open by hand.

One number is asked for at a time. Under the floor the only decision a reader makes is whether to make the draft happen, so the aim is not mentioned and would only compete with the ask; past the floor the aim is the ask. A pod at the aim has nothing left to ask for and shows its Yes and Maybe counts instead, which is also how a second table's worth announces itself. Scheduled and Launcher pods read identically — the launcher slot is not a different thing to a player, so it does not get different copy.

## The rally model — shared by Scheduled and Launcher

Every recruiting notification is anchored to the draft time and is never fired far from it. Two escalating steps:

1. **T-3h — silent reminder.** A message in the pod chat, **no ping**, saying the session is looking for players. Sent for any short pod, however far from the aim, because it costs nothing. If T-3h was skipped — the bot was down, or the pod did not exist yet at T-3h (a short-notice Scheduled pod, or a Launcher slot that only reached the floor later) — a **T-2h catch-up** covers it. If the pod is created inside T-2h there is simply no silent step; it goes straight to the T-1h behaviour.
2. **T-1h — @slot ping.** Fires only when the pod is **close**: it needs 1 or 2 to reach the number it is currently chasing, the floor while the draft is not yet on and the aim once it is. A pod still far from that number at T-1h gets no ping, only the standing silent message.

This encodes the organizer instinct: first a low-key "we need a few more in a couple hours" in chat, then lean on the @slot an hour out only if the soft nudge did not move it.

### One living message, from the first signup to the lobby

- It is **deleted only when the pod actually starts** (the lobby opens / the event leaves `pending`) or its recruiting window closes. Never deleted on a player count. So an 8 → 7 drop (someone leaves) flips the text back to asking for one more instead of the message vanishing.
- **Firing does not end it either.** A slot that reaches the floor hands its message to the pod it just made, rewritten against the new card. Deleting it there was the worst possible moment: the draft has just become real and is still short of a full table, and the surface saying so disappeared until the card's own T-3h beat hours later.
- To survive chat burial it **resends** — delete then repost at the channel bottom — at the T-3h and T-1h beats. Live RSVP changes between those beats edit it in place, silently.
- Reaching the aim keeps the message and the signup link, silently.

### Not built: promoting a short pod outside pod chat

Attendance is advertised in the pod channels only, so a quiet day is invisible to anyone not already watching them. The planned answer is a **short pointer** — pod name, start time, current count, what is still needed, link to the launcher — posted in one other channel, at most once per pod, edited if the count moves, removed when the pod starts.

Open, and the reason this is not built yet: **which channel, and when.** The channel is per pod, not global (a flashback or cube pod belongs in the flashback channel, a latest-set pod does not), so it needs a format-to-channel map that does not exist. The timing leans late — around T-10min and only below the aim — rather than the T-3h recruiting beat, which the pod-chat message already covers.

## Launcher fire and the creation announcement

A Launcher slot fires the moment it reaches the floor, at any hour. Firing creates the Scheduled card and opens the lobby path. Firing early and nudging early are different things: a pod coming together hours ahead is fine, only the *recruiting notification* is held to the near-time window. So the card post is gated by proximity:

- **Fires within 3h of the draft time** — post the card with a **creation announcement** that tags the @slot role. The announcement carries **no count** (it states the pod is on for its time), so it never goes stale as players join; the card's own visible roster does the "come be one of the last in" selling. The announcement names the pod via its event name and keeps the @slot tag distinct, so the role mention and the pod name do not read as a doubled label (same fix as the nudge copy).
- **Fires earlier than 3h out** — post the card **silently**, no ping. The T-3h / T-1h rally then recruits the last seats near game time.

## Ping inventory

So we never double-notify, every push is accounted for:

- **Recruiting pings** (@slot, to the whole role): the T-1h rally, and the within-3h creation announcement. Both obey "never ping far from the draft time."
- **Lobby ping** (to the confirmed Yes + Maybe roster, inside the thread) at **T-10min**: Draftmancer is opening, get in. This is not a recruiting ping and is unaffected by the rally rules.
- **No ping** on reaching ready.
- **Queue**: a single count-based "one short of firing" ping, once, after a quiet window, and silent if the queue fills fast (DraftBot-style). Queue has no schedule, so no hour-based reminders.

## Get-ready reminders (once a pod is happening)

These are the "it's on, get ready" reminders, distinct from the recruiting nudges above and largely unchanged by this redesign. They target the pod's confirmed roster, not the slot role. They live in `bot/tasks/pod_draft_reminder.py`.

- **T-60min — roster reminder.** A silent "🔔 Pod Draft starting soon" embed in the pod's own thread, listing the Yes and Maybe rosters. No ping — a courtesy heads-up for those already in.
- **T-10min — lobby reminder.** Posts the Draftmancer link in the thread and pings the attendees individually (the confirmed users, not the @slot role). This is the "get in the lobby" ping.
- **Opt-in DM.** Each player on the default-on preference is DM'd the lobby-open link at open time; opt out via `/roles` (`bot/services/pod_link_dm.py`, spec [[pod-dm-notifications]]). Shipped.

Note the **T-60 coincidence**: the T-1h recruiting @slot ping and the T-60 roster reminder both fire an hour out, but they differ in place and audience — the recruiting ping is public to the whole slot role and only when short, the roster reminder is in-thread and silent for those already in. No conflict, but they land together.

## No-shows

A ✅ Yes is taken at face value as coming. The bot does not react to Yes players who never appear in Draftmancer at lobby time; the players present sort it out live. (Closed decision.)

## Scheduling onto an occupied slot

A `/draft` schedule whose time collides with an existing pod, or with an open launcher slot that already has sign-ups, is **blocked for non-admins**, with a pointer to the existing pod. An **admin can override**. The occupancy check must look at open launcher signals, not only created events, so a user scheduling straight onto a slot that already has poll sign-ups is caught rather than spawning a parallel pod that strands those sign-ups.

## Deltas from current behaviour

- Scheduled nudge first appears at **T-3h**, not T-24h. The T-24h silent post is dropped.
- The nudge is **never deleted on reaching the aim**; it lingers as "ready" and only clears when the pod starts. Fixes the churn case where an 8 → 7 drop made the message disappear.
- The T-1h ping fires for **any close pod** (needs 1 or 2), not only the exact one-short case; and it is **gated to close pods**, so a pod stuck far from the aim no longer pings.
- The Launcher slot stops nudging on the **count trigger** (the current "5th player joined, whenever that is"). Recruiting moves to the shared T-3h / T-1h schedule, so no more "in 9 hours" pings at noon.
- The Launcher **creation announcement** is numberless and **gated to within 3h**; earlier fires post the card silently.
- Copy cleanup still pending for the **queue nudge** and the **second-table offer**, which keep old hype copy.

## Open / tentative

- The "aims" definition above is marked almost-locked pending your review of this section.
- "Close" for the T-1h ping is set at needs ≤ 2.
