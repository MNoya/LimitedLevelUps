# Pod Draft — Components V2 lobby migration (parked)

Working spec for porting `bot/services/lobby_embed.py` from classic `discord.Embed` to Components V2 (`ui.LayoutView`). **Not started.** Champion announcement migration (already shipped) is the precedent.

## Why migrate

The lobby embed currently uses several alignment hacks that V2 primitives would replace cleanly:

| Current hack (lobby_embed.py) | V2 equivalent |
|---|---|
| `embed.add_field(name="​", value="​", inline=True)` filler fields to break inline 3-column rows | No 3-column inline rule in V2 — components stack as placed, no filler needed |
| `"\n​"` trailing zero-width-space lines for vertical spacing between row groups | `Separator(visible=False, spacing=small\|large)` — proper spacing primitive |
| `_block()` using `> ` blockquote markdown for the vertical-bar effect | `Container` accent bar provides similar visual grouping; or keep blockquote inside TextDisplay |
| Conditional `ready_trailing` newline math to height-match Ready vs Pending columns | Separator components don't need height-matching; layout is purely vertical |

## What V2 won't fix

- True side-by-side "display name | arena name" columns — V2 has no column primitive. We hit the same wall with the champion announcement standings; the fix there was to merge into a single TextDisplay row with `name | arena` inline rather than two parallel fields. Lobby could do the same.
- Per-row icons/thumbnails — Thumbnail is sized for accessory use (~64px) and looks oversized next to short rows. Same finding as the champion-standings experiment.

## Scope of the port

`render()` in `bot/services/lobby_embed.py` (~140 lines) builds embeds for these states:

- `empty` / `partial` / `linked` / `unlinked` — pre-ready
- `ready` / `notready` — ready check in progress / failed
- `drafting` / `complete` / `cancelled` — terminal/post states

Each branch composes different field sets (in-draftmancer, unrecognized, waiting-on, maybe, commands footer). The port replaces every `embed.add_field(...)` with a V2 `Container` + `TextDisplay` / `Separator` / `Section` composition.

## Plan

1. New module `bot/services/lobby_view.py` exposing `render_layout(...)` returning `ui.LayoutView` (parallel to `render()`'s embed for an A/B period if needed). Same input signature so callers don't churn.
2. Port each state branch one at a time, starting from `empty` (simplest) and ending at `ready` (most complex with parallel columns).
3. Wire `LobbyReadyButtonView` into the LayoutView. The persistent `custom_id` dispatch (`READY_CHECK_CUSTOM_ID`) still works in V2 — buttons keep their identity inside `ActionRow` components.
4. Update callers:
   - `bot/services/pod_draft_manager.py` — wherever `lobby_embed.render(...)` is called and the embed posted/edited.
   - `bot/commands/testlobby.py` `_build()` — testlobby renders multiple states for preview.
5. Run `!testlobby` against every state in `_VALID_STATES` to confirm visual parity (or improvement).

## Open questions

- **Keep both renderers in parallel?** Could expose `LOBBY_USE_V2` env flag to A/B between embed and LayoutView during the transition. Probably overkill — port is mechanical enough to do as a single PR.
- **`empty` state in V2** — currently the embed has just a title and minimal fields. V2 with a Container might feel heavier visually for the "empty" case. Maybe collapse to a bare TextDisplay (no Container) for empty.
- **Component budget**: busiest state (`ready` or unrecognized + waiting + maybe) approaches the 40-component cap. Audit before porting.

## Component-budget audit (estimate)

| State | Current fields | V2 components (rough) |
|---|---|---|
| `empty` | 1–2 | 3 (Container, TextDisplay, ActionRow) |
| `partial` | 3–5 | 6 (header, separator, in-draftmancer block, waiting block, maybe block, footer) |
| `unlinked` | 6–8 | 10–12 (additional unrecognized/how-to-fix blocks) |
| `ready` | 5 | 8 (header, separator, Ready section, Pending section, commands footer) |
| `notready` | 5 | 8 (same as ready) |
| `drafting` / `complete` | 3 | 5 |

All states comfortably under the 40-component cap.

## Verification

- `!testlobby` walks through every state — confirm parity with current screenshots
- Persistent `LobbyReadyButtonView` survives bot restart (custom_id dispatch)
- All 221 tests still pass
- Visual smoke on mobile + desktop (Section/Thumbnail layouts wrap differently on narrow widths)

## Files to touch

| File | Action |
|---|---|
| `bot/services/lobby_view.py` (new) | LayoutView builder mirroring `render()` |
| `bot/services/lobby_embed.py` | Eventually deleted; or kept as compatibility shim during transition |
| `bot/services/pod_draft_manager.py` | Swap `embed=...` posts/edits for `view=...` |
| `bot/commands/testlobby.py` | `_build()` switches over for every state |

## Out of scope

- Migrating the round-pairings embed (`_round_embed`) — separate effort, lower payoff
- Migrating the live-thread standings (`build_champion_embed`) — separate effort, lower payoff
- Per-player avatar thumbnails in the lobby (Thumbnail-too-big problem already known)
