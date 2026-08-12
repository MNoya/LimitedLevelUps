# Personalized Draftmancer link (auto-fill Arena name)

## Status — SHIPPED

Built as `bot/services/pod_join_button.py` (the in-thread Join Draft button), `draftmancer_url_for(session_id, user_name)` in `bot/services/pod_drafts.py` (the link builder), and `bot/services/pod_active_lobby.py` (hands the live lobby's personalized link back on a fresh `/link-arena`). Shipped alongside [[pod-dm-notifications]] (the DM delivery of the same link) in one deploy rather than as a fast-follow.

As-built beyond the original design: session ids gained a random tail and the lobby-open post is gated on the bot holding the Draftmancer session, so a guessable id can't be entered to seize ownership before the bot connects (`PodDraftManager.await_ownership`, `_session_id_off_base`). Sibling: [[pod-arena-handle-capture]] populates the `arena_name` this relies on.

## Kickoff prompt

> Implement the personalized Draftmancer link for pod drafts, per `spec/pod-personalized-link.md`. Read that spec and `CLAUDE.md` first. This is the entry point of three coupled join-flow specs — recommended order: this one, then `spec/pod-dm-notifications.md` (reuses this link builder), with `spec/pod-arena-handle-capture.md` landable any time (it feeds the `arena_name` this relies on). Scope for now: the link builder + the in-thread "Join Draft" button only, no DM. Before writing code: confirm the lobby-open flow at the cited files still matches, and resolve the open questions — especially verify Draftmancer honors `?userName=` on our join URL. Surface the still-open decisions to me before building. Conventions: no inline comments, Title Case on Discord menus/options, test logic not framework, leave changes staged and don't commit until I ask.

## Context

Lobby-open posts a single shared Draftmancer session URL and asks every player to manually set their Arena name in Draftmancer so pairings resolve. The current copy literally says to set `ArenaID#12345` as your Draftmancer name. Amelas DraftBot instead bakes the name into a per-user link (`?userName=`), so the field is pre-filled and the manual step disappears.

We store each player's Arena tag (`players.arena_name`, nullable, `bot/models.py:50`, plus `arena_aliases` at line 51), so we can pre-fill the *correct pairing name* — one better than DraftBot, which fills the Discord display name because that's all it has.

Goal: make it faster and clearer to join and load a pod, by removing the manual rename.

## Mechanism

Append `?userName=<url-encoded arena tag>` to the session URL (`&` separator if the URL already carries a query), matching DraftBot's `models/draft_session.py:171-189` in the local clone. Draftmancer reads `userName` and pre-fills the lobby name field. Our pairing logic matches Draftmancer session user names back to `arena_name`, so a pre-filled name makes pairing resolve with no player action.

Fallback when `arena_name` is null (unlinked or lightweight pod-only player): keep the current shared link and the existing "set your name" copy. The prompt to fix that null is [[pod-arena-handle-capture]].

## Delivery

Pre-filling makes the link per-user, so it can no longer be one shared thread post. Proposed v1: keep the shared session link in the lobby-open thread post, and add a **Join Draft** button that returns an *ephemeral* personalized link on click. This stays in-channel, is one message, needs no DM, avoids the double-ping problem, and kills the manual rename for everyone present. Opt-in DM delivery of the same link is the separate [[pod-dm-notifications]] spec (the button and the DM share one link builder).

Wrap the URL in `<...>` to suppress the Draftmancer OG unfurl (DraftBot's DM shows the unfurl is noise).

## Surfaces to touch (as mapped this session)

- `MSG_LOBBY_OPEN` (`bot/commands/messages.py:32-37`) and `build_lobby_open_body` (`bot/tasks/pod_draft_reminder.py:404-416`).
- `draftmancer_url_for(session_id)` (in `bot/services/pod_drafts`) — the link builder. Add a `user_name` parameter or a `personalized_draftmancer_url(session_id, arena_name)` wrapper. Consumed at `pod_launch.py:936` and `pod_draft_reminder.py:67`.
- Lobby-open post sites: `fire_reminder` (`pod_draft_reminder.py:80-85`, scheduled T-10) and `open_ondemand_lobby` (`pod_launch.py:944-946`).
- New Join button view: resolve the clicking member → player → `arena_name` → personalized ephemeral link. Null `arena_name` → ephemeral nudge to `/link-arena`.

## Resolved decisions

- Shipped the in-thread button and the opt-in DM together in one deploy, not button-first.
- The button resolves discord id → player row → `arena_name`; a null handle returns the shared link with a Link Arena nudge instead of a personalized one.

## Testing

Link-builder unit tests: arena name url-encoded, correct `?`/`&` separator, null arena_name returns the base URL unchanged. Button resolves the caller's own arena_name. No test that Draftmancer itself pre-fills — that's framework behavior.
