# Scheduled Pod RSVP Cards — Replacing sesh

Status: spec agreed with the owner 2026-07-14, not started. Third act of the on-demand work (`spec/pod-daily-poll.md`): the poll covers off days, `/draft` covers right-now, this covers the fixed weekly slots so sesh can leave the server.

Why: sesh has no free API, so today the bot DMs the owner a `/create` command to paste for every weekly slot (`bot/tasks/pod_schedule_post.py`), then reverse-engineers sesh's embed edits to track RSVPs (`bot/listeners/sesh_listener.py`). Owning the card removes the paste dance, the parser, and the third-party dependency in one move.

---

## What sesh does for us today

Posts the RSVP embed (localized time, duration), tracks Yes / Maybe / No via buttons, edits the card as RSVPs move, creates the event thread, and pings the slot role from the `/create` mention. Everything downstream is already ours, keyed off sesh's message: event registration, T−10 lobby open, underfill nudges, roster reminder, slot-role auto-grants, team-vote offer.

---

## Design

### Signal model — reuse, not invent

A scheduled pod is a `pod_signal` with `kind='scheduled'`, created already in status `'fired'` with `event_id` linked — the thread and `PodDraftEvent` exist from post time, exactly like sesh. That single choice buys the fired-signal semantics for free: RSVPs stay open forever (over-signups welcome), expiry never triggers, and `set_membership` needs no new states.

New migration: `pod_signal_members.rsvp TEXT NOT NULL DEFAULT 'yes'` (`yes` | `maybe` | `no`). Poll and queue members are implicit yes; the scheduled card is the only surface that writes the other two.

RSVP semantics: clicking a state moves the member there; clicking their current state removes the row entirely. Yes grants the slot role + Pod Drafters umbrella with the one-time ephemeral confirmation (same helpers the poll uses); Maybe and No grant nothing.

### The card

One card, two button surfaces over one signal. The channel card: a bare slot-role mention as the pinging content line (embeds never notify), an embed with the localized `<t:…:F>` time, a Google Calendar `[+]` link, and three inline columns (Yes / Maybe / No), plus RSVP buttons on a persistent view with static custom_ids (`pod_rsvp:yes` etc.), resolved per message like the poll. The thread hangs off the card message, sesh-style, so the channel shows one block with the thread preview attached and the thread displays the live card on top as its starter. Discord renders the starter's own components disabled inside the thread, so a near-empty view-only button row posted right under it is the live surface there; its clicks resolve to the same signal and re-render the shared card — the fix sesh couldn't ship. Thread membership follows the RSVP: Yes and Maybe pull the member in, No takes them back out.

The card states concisely that RSVPs past 8 split into multiple pods — attendees regularly blow past 8 and need to know extras still play. The split itself stays manual via `/pod-table`; automating it is out of scope. Copy lives in the card builder, not here.

Every RSVP click gets an ephemeral confirmation of the recorded state, matching sesh's Ephemeral RSVP Confirmations behavior — on the scheduled card only; poll and queue keep their silent toggles. The one-time role-grant ephemerals are separate and unchanged.

Restart survival, DB-enforced button truth, and edit-in-place all follow the poll/queue rules from `spec/pod-daily-poll.md`.

### Native Discord Event

sesh also creates a guild scheduled event, which is where mobile discovery, the Events tab, and Discord's own start-time notifications come from — worth keeping. The poster creates one alongside the card: same name, start at slot time, end at +2 h, description carrying a jump link to the card. It is a discovery mirror, not a second RSVP surface — the card stays canonical and Discord's "Interested" is Discord's own affordance, so the one-canonical-surface rule holds. A postpone updates it; nothing else touches it.

### Postpone

sesh's external settings website is overkill, but its in-place reschedule matters — pods get pushed a few hours routinely. A ⚙️ button on the card opens a mod-gated ephemeral menu, sesh-style; its postpone entry (quick offsets or an exact time via modal) updates `event_time`, re-arms the lobby open + team-vote + underfill + roster jobs, edits the card's timestamp, updates the native Discord event, and drops a note in the thread. No general edit UI beyond time.

### Creation and arming

At post time the poster creates the event + thread through `pod_launch` (standard `SET Pod Draft #N - date` naming), arms the T−10 lobby open via `open_ondemand_lobby`, and arms the at-start team-vote check — all existing machinery. The startup re-arm sweep already covers bot-native pending opens.

### The poster — `pod_schedule_post` rework

`fire_create_command` (DM the owner a `/create` to paste) becomes posting the card directly. Send instants:

- **Wed slot**: Monday noon ET, alongside the weekly overview — unchanged.
- **Thu slot**: slot − 47 h — unchanged.
- **Sat slot**: **Thursday early-slot start + 3 h** (17:00 ET / 18:00 UYT). The old slot−47h instant lands mid-Thursday-pod; this waits until that pod is done.

Release/championship/season pauses via `monday_kind` gate the poster exactly as they gate the DMs today. The Monday overview post itself is unchanged.

### Decoupling from `sesh_message_id`

The RSVP card is ours, so RSVP changes are handled in the button handler directly — no edit-detection. The consumers currently keyed off sesh re-key to the event/signal:

- **Underfill nudges** (`pod_underfill`): yes-count reads from signal members; refresh runs from the RSVP handler instead of the sesh-edit hook.
- **Roster reminder** (`pod_draft_reminder`): yes/maybe lists read from signal members.
- **Lobby open**: `open_ondemand_lobby` (already roster-driven); `fire_reminder` stays sesh-only until the listener is deleted.
- **Slot-role auto-grant**: moves into the Yes handler; the sesh-edit grant path stays for legacy cards until removal.
- **Time edits**: replaced by the card's ⚙️ postpone menu (above); `bot/scripts/reschedule_pod_event.py` stays the emergency hatch.

### Transition

Deploy → the poster starts posting bot cards → the owner stops pasting `/create` → `sesh_listener` sits dormant (it only reacts to sesh messages) → kick sesh from the server whenever → a follow-up change deletes the listener + parser, keeping finalized sesh-born history untouched.

---

## New / changed files

- `bot/tasks/pod_schedule_post.py` — post cards instead of DMing `/create`; Saturday send-time change.
- `bot/commands/pod_rsvp.py` (or grow `pod_queue.py`'s sibling) — card builder + `PodRsvpView`.
- `bot/services/pod_launch.py` — scheduled-kind creation path; RSVP toggle with the `rsvp` column.
- `bot/tasks/pod_underfill.py`, `bot/tasks/pod_draft_reminder.py` — signal-keyed refresh paths.
- Migration: `pod_signal_members.rsvp`.
- `!test rsvp` driver in `testpolls.py`.

## Implementation order

1. Migration + `rsvp` column through `set_membership`.
2. Scheduled creation path in `pod_launch` (event + thread + card + native Discord event at post time, status `'fired'`, arming).
3. Card builder + `PodRsvpView` with the three-state toggle, per-click ephemeral confirmations, and grants.
4. Poster rework with the Saturday instant.
5. Underfill + roster-reminder re-keying.
6. The ⚙️ postpone menu.
7. `!test rsvp`; live-test on the test guild.

## Out of scope

- Automated multi-pod splitting past 8 (stays `/pod-table`).
- Card edits beyond time (name, duration, description are code constants).
- Deleting `sesh_listener` / `sesh_parser` (follow-up once sesh is kicked).
- Website surface.
- Personal DM reminders (wanted, a later phase): sesh DMs each RSVP a confirmation carrying a Reminders picker (on event start / 10 min / 1 hour / 1 day / 1 week before) and an UnRSVP button. Ours would hang off the Yes handler: an opt-in picker on the confirmation ephemeral, per-user DB-backed reminder rows, DM delivery via APScheduler date jobs re-armed by postpone and the startup sweep. The native Discord event's bell covers the basic case today, so this is additive polish.
