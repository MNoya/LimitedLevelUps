# Capture Arena handle at the Pod Drafters welcome

## Status — BUILT

Shipped as the button-driven Pod Drafters welcome. This is the data-capture half that makes [[pod-personalized-link]] work — auto-fill degrades to the manual "set your name" fallback whenever `players.arena_name` is null, and this drives that null rate down.

## What it does

When a player first becomes a Pod Drafter they get a Components V2 card. The card is one shared builder (`_PodButtonCard` in `bot/services/ping_roles.py`) behind two surfaces:

- **The welcome** (`build_welcome_view`) — public in pod-draft-chat, green accent, pings the newcomer. Fires only for a player with no linked Arena handle. Shows what they're now subscribed to (the granted slot role and its notification, or the Pod Drafters umbrella on the onboarding path) over the button row.
- **The returning grant card** (`build_grant_view`) — the ephemeral notice a drafter gets when they freshly pick up a slot role. No self-mention (the reader is the subject). Linked players see their Arena handle and no Link Arena button; unlinked players see the link call-to-action and the button. Accented with the granted role's color.

Both carry the same button row, each reusing the existing command's code path so they can't drift:

- **Link Arena** — opens a modal that stores the handle through `attach_arena_alias`, the same path `/link-arena` uses; posts the shared public confirmation (`MSG_ARENA_LINKED`). Shown on the welcome always, and on the grant card only when unlinked.
- **Pod Guide** — the same ephemeral guide embed `/pod-guide` posts.
- **Notifications** — the same ephemeral `RolesView` `/roles` opens.

A linked handle gates the welcome out entirely: reaching `/link-arena` (or the modal) means the player already found pods, so they're treated as returning. On an interaction path they fall through to the grant card; on the no-interaction onboarding path they get nothing.

## Onboarding coverage

The welcome originally fired only off `grant_pod_drafters` returning "first pod", which is reached only from interaction paths (RSVP, queue, poll, table, `/roles`). Discord's native Server Onboarding grants Pod Drafters with no interaction, so those joiners never hit that path. Covered with a role-**gain** branch in the `on_member_update` listener (`bot/commands/roles.py`, alongside the existing removal branch) that posts the welcome to the channel via `send_welcome` (`bot/discord_helpers.py`).

Dedup between the two paths avoids a double welcome: bot-mediated umbrella grants (`grant_role` / `toggle_role` in `bot/services/pod_roles.py`) set a one-shot marker before `add_roles`; the listener welcomes only gains with no marker (`consume_bot_umbrella_grant`), which is exactly an onboarding grant. The interaction paths keep posting their own welcome.

A welcomed-once guard (`_first_welcome_for` / `forget_welcome`) stops a re-toggle of the role from re-posting the public welcome. It is **in-memory**, so it re-arms on restart — acceptable because a member only picks the role once in normal use. `!test reset` clears the tester's mark so the flow stays replayable.

## Shared Arena accounts

An Arena account passed between players is a normal thing here, so linking a handle someone else holds is allowed and takes it from them: their row keeps its history, it just stops answering to that name. Only future pods move, since a finished pod already recorded which player sat in the seat. One holder at a time is what keeps a Draftmancer seat a single lookup with a single answer, and it makes the link itself the declaration of who is playing the account now.

## Persistence

`persistent_pod_card_view()` is registered at startup (`bot.add_view` in `bot/main.py`) so the card's buttons keep dispatching after a restart; both surfaces share the same custom_ids. The card view is `timeout=None` and the grant card is ephemeral with no `delete_after`, so it stays until the player dismisses it.

## Testing

`bot/tests/test_ping_roles.py` covers the welcomed-once guard and the bot-grant dedup marker; `bot/tests/test_pod_identity.py` covers `player_arena_handle`. Per convention, not the card copy. End-to-end flows (onboarding welcome, no-double-post, linked-silent, persistence) are exercised by hand through `!test welcome` / `!test rsvp` / a manual role add, with the listener and grant decisions logged.

## Follow-ups (not done)

- **Durable welcomed-once guard.** The in-memory guard re-arms on every deploy. A persistent version would need a "welcomed" marker, and for onboarding-only users (no `players` row yet) that means creating a lightweight row — deferred as not worth blocking on.
- **Pod Guide content.** The guide text (`bot/pod-draft-guide.md`) was not revisited for the button era.
