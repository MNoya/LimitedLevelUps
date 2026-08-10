# Pod Draft — Team Draft mode (handoff)

Status: **graduation implemented** — the board, startDraft assignment/reveal, team threads, and all-in finalize live in `bot/services/pod_team_board.py` / `bot/services/pod_team_flow.py`, with thin delegation hooks in `pod_tournament.py` and `pod_draft_manager.py`. Kept for design rationale. This doc supersedes the earlier stale spec (which predated every UI decision — ignore any memory of A/B teams, round-gated flow, or a single champion).

Continues a long design session. The design is settled; the remaining work is a sizable implementation ("graduation") described at the end.

---

## Your task (start here)

You are picking up a team-draft feature whose **design is fully locked** and **partially built** on branch `pod-draft-team-mode` (already checked out; all work is uncommitted in the working tree). Read this entire document first — it is the single source of truth; the design was iterated over a long session and the decisions here are deliberate, so implement them as written rather than re-litigating them.

Your job is the **graduation**: turn the locked design into the live pod-draft flow. Do it in this order:

1. **Extract team logic into its own module(s) first.** `pod_tournament.py` is 4263 lines and must not grow a bigger team footprint. Create `bot/services/pod_team_board.py` (the Components V2 board — render + button/select interaction, graduating the `!test teams` prototype) and `bot/services/pod_team_flow.py` (assign teams on `startDraft`, post the reveal, post the board at `endDraft`, open+link the private team threads, finalize + announce the winning team). Leave only thin `if pairing_mode == "team": delegate(...)` hooks in `pod_tournament.py`, and move the reusable team helpers out of it.
2. Then wire the flow: assign teams on `startDraft` from the locked seating (Phase 2 reveal), post the board at `endDraft` (Phase 3), bind the board's report buttons to the real `_handle_result_submission` path under the existing `_advance_lock`, open the threads linking to the board, and finalize on all-matches-in (per-player records → existing pod-point path; announce the winning team; suppress the single-champion/trophy-hype post for team mode).

**Critical trap:** the team code currently sitting in `pod_tournament.py` is an **earlier, superseded** approach (round-gated per-round embeds) that predates the board decision. Do **not** build on it — rework/replace it. See "Built but SUPERSEDED" below for the exact functions; some helpers are reusable (pairing dispatch, team scoring, thread creation, `team_label`/`team_emoji`), the round-gated *rendering* is not.

Verify with the `!test` commands and `pytest` as you go (see Testing). Follow repo conventions (below). Branch is `master`; **never push**, and **do not commit until the user asks** — leave everything in the working tree.

---

## What this is

A **team draft** pairing mode for the existing pod-draft feature: a fourth value of `pod_draft_events.pairing_mode` (`swiss` / `bracket` / `random` / **`team`**), selectable in the lobby Settings panel. Same lobby, ready check, and Draftmancer socket lifecycle as a normal pod — different seating, pairing, results surface, and finalize. Targeted at **3v3**; 4v4 / 5v5 stay allowed (even rosters only) but 3v3 is the design center.

Reference implementation for the whole feature family is Amelas/DraftBot (`/home/mnoya/Projects/Personal/DraftBot`) — read it before reinventing socket/pairing/copy details. Draftmancer source is at `/home/mnoya/Projects/Personal/Draftmancer`.

## Core mechanics (settled)

- **Teams = draft-seat parity.** Draftmancer's `teamDraft` session setting makes alternating seats the two teams and color-codes them in-client. We push the seating, so seat 0/2/4… = Green Team, 1/3/5… = Blue Team. `teamDraft` is "mostly visual + forces bots=0 + drives its built-in bracket" per Draftmancer's own tooltip; it does **not** change pack-passing. We don't use Draftmancer's bracket — we run our own pairings and results in Discord (exactly like DraftBot).
- **Teams follow the seat order, which follows the existing `seating_mode` — all three modes are in scope for team draft.** Teams are pure seat parity, so the current Seats options map directly: **Random** → random teams; **Manual** → organizer-arranged teams (this is exactly how an organizer puts two people together — reorder the seats via `pod_seating_select` / `SeatOrderModal` and parity decides the sides); **Leaderboard** → rank-balanced (alternating strong/weak). No new team-arrangement UI needed for v1 — Manual already is it. (A nicety for later: surface the 🟢/🔵 parity in the manual seat UI so the organizer sees which side each seat is.)
  - **One caveat for Seats: Random under team mode** — the bot must **shuffle and push** the order via `setSeating` (`setRandomizeSeatingOrder(False)`), *not* emit Draftmancer's `setRandomizeSeatingOrder(True)`. Draftmancer's own start-time shuffle hides the final order until a post-start broadcast/log read, but team mode needs the order known at `startDraft` for the reveal + assignment. Manual and Leaderboard already push a known order via `setSeating`, so only the Random path changes for team mode.
  - Whatever the mode: decide the order **once** (`manager.desired_seating`), re-assert it before `startDraft`, assign teams from it — never leave teams to raw lobby-join order.
- **Team assignment happens at `startDraft`**, from that locked seating — not post-draft from the log. Once `startDraft` fires, Draftmancer locks the table (no joins/leaves), so the seat order is final and there's no staleness window. The draft log later only *confirms* `seat_index`. (The currently-built code assigns post-draft — see "superseded" below; graduation moves it to `startDraft`.)
- **Pairing is a fixed cross-team rotation, results-independent.** Round r pairs `Green[i]` vs `Blue[(i+r-1) % n]`. All 3 rounds (9 matches for 3v3) are known up front. 3v3 = each player faces all 3 opponents; **9 matches is odd so a 3v3 can never tie** (no tiebreaker round needed). 4v4 = 12 matches, can tie 6-6 (a tiebreaker round would be needed — out of scope for now). Even sizes can tie, odd sizes can't.
- **Ungated, but presented as rounds.** Because pairings don't depend on results, all matches are shown at once and every report button is live from the start — a player who finishes early can play their next opponent without waiting on a slow match. We do **not** tell players to "play in any order" (that invites coordination chaos and fights how team drafts actually run); we present rounds as the cadence and let ungating be an implicit convenience.
- **Scoring: per-player reuse.** Each player plays 3 matches, so their individual record (3-0 → trophy pod points, 2-1 → 2) flows through the existing finalize path with **zero formula change**, bot or frontend. The team result is a display/headline concept, not a new scoring term. No single "champion" — the finalize announces the winning *team*.

## The communication flow (locked)

- **Phase 0 — Lobby** *(unchanged)*: organizer sets Pairings = Team Draft.
- **Phase 1 — Draft start**: ready check completes, seating pushed + re-asserted, `startDraft` fires. `teamDraft` emitted on. Pure setup.
- **Phase 2 — Draft underway**: seats are locked. In `_start_draft` (right after `_seed_participants_at_draft_start`, `pod_draft_manager.py` ~L1208), assign+persist teams from the locked seating and **post the team reveal**. For team mode this reveal embed (title `🎉 Team Draft started`) **replaces** the generic `**🎉 Draft started!**` banner (`pod_draft_manager.py:1213`) — do not post both; the reveal *is* the start announcement. Draftmancer also colors teams in-client. This is the *only* reveal — no provisional/confirmed ceremony (DraftBot has none either; it forms teams once).
- **Phase 3 — Draft ends** (`endDraft`): **post the board** (the match surface) in the main thread. Open the two **private team threads**, each with a **one-line intro linking to the board** and the team's **own voice room**, then silent.
- **Phase 4 — Match play** on the board.
- **Phase 5 — Finalize** (all matches in): announce the winning team; board shows final Wins; per-player records feed leaderboard pod points.
- **Phase 6** — team threads auto-archive.

## The board (locked — currently prototype-only in testlobby)

A single **Components V2** `LayoutView` message (discord.py 2.7.1 has full V2), posted once at Phase 3, holding everything. Reference prototype: `!test teams` in `bot/commands/testlobby.py` (`_TeamV2Board` / `_TeamV2View` / `_TeamV2Button` / `_TeamV2ReportSelect`).

Structure inside one `Container(accent_colour=green)`:
- **Team block, Green** — `TextDisplay`: header `🟢 **Green Team**`, with ` - Wins: N` folded in **only once that team has a win**; then one line per player `DisplayName  \`arena#1234\``.
- **`Separator(visible=False, spacing=small)`** — a minor gap, no divider line.
- **Team block, Blue** — same shape, `🔵 **Blue Team**`.
- Then per round: `Separator()` (visible) + `TextDisplay("### Round N")` + one **`Section` per match** = pairing text + a report **Button** accessory (V2 accessories can be a button, not a select).
  - Match line uses **Discord display names only** (`⚔️ A vs B`, or `▫️ Winner wins 2-1 vs Loser` once reported). Arena handles are **not** repeated per round — they live once in the team blocks up top.
  - Button: grey `Report` when pending; **green** (Green won) / **blurple** (Blue won) with the **score** as its label once reported. Clicking opens an ephemeral result select (`A wins 2-0/2-1`, `B wins 2-1/2-0`, `Not played`). Color carries the result; the button never shows names.

Deliberately **not** on the board: no "Team Draft" title (DraftBot has no persistent board title — `### Round N` are the section headers, like its "Round N Pairings"); no "Arena handles" section title; no progress counter (`X/9 reported` — DraftBot has none); no "Report each match" instruction (the Report buttons are self-evident); no "play in any order" line.

### Naming & copy decisions
- **Green Team / Blue Team** (not "Team Green", not A/B, not Red — red reads as loss/danger; green+blurple are the two available positive Discord button styles: `success` + `primary`, with `secondary` grey for pending).
- Team reveal (Phase 2) is a **classic embed** with two side-by-side inline fields `🟢 Green Team` | `🔵 Blue Team` (classic embeds can column; V2 cannot). Prototype: `!test teamreveal` (`_team_reveal_embed`).
- Team thread intro: one line, e.g. `🟢 **Green Team** private room. Talk strategy here. Report matches on the board in the main thread.` — plus a **link to the board** — then the bot never posts there again (DraftBot's team channels are entirely bot-free; we add a single orienting line because private threads otherwise open empty).
- No em-dashes, no interpuncts, no "good luck"/filler in copy.

## Discord/V2 facts learned (so the next session doesn't re-derive them)
- V2 components available: `Container, Section, TextDisplay, Separator, MediaGallery, Thumbnail, ActionRow, File, Label`, selects, buttons. **No column/grid/inline-field primitive** — the only native side-by-side is `Section` (text + one accessory) and `ActionRow` (≤5 buttons). Real columns need a **classic embed** (inline fields) or a **monospace code block** (manual padding).
- V2 replaces the classic embed on a message (no `embed=`/`content=` alongside). We already ship V2 (the trophy-hype card).
- No text alignment anywhere in Discord (no centering). Headings/bold/separators are the only emphasis.
- `Separator(visible=False, spacing=SeparatorSpacing.small)` = gap without a line.

## Race conditions (already handled in the live report path)
Python async is single-threaded (reports interleave, not parallel). `_commit_result` is an atomic per-match transaction. Different matches → independent. Round advancement/finalize is serialized by `manager._advance_lock` so two results can't double-post the next round or double-finalize. Same-match double-report is last-write-wins (benign, editable). Board re-render rebuilds from committed state (self-heals). No `with_for_update` needed.

---

## Inventory: built / prototype / superseded / remaining

### Built (working tree, uncommitted, tests green — 756 pass)
- `bot/models.py`: `PodDraftParticipant.team`, `PodDraftEvent.team_a_thread_id` / `team_b_thread_id` (all nullable).
- Migration `alembic/versions/h9i0j1k2l3m4_pod_team_draft_mode.py` — additive, **applied to the local dev DB**; `alembic check` clean.
- `bot/services/pod_team.py` — **pure** pairing module: `TEAM_A`/`TEAM_B`, `assign_teams` (seat parity), `team_rosters`, `pair_round` (rotation), `team_match_wins`, `team_winner`. Tested by `bot/tests/test_pod_team.py` (9 tests).
- `bot/services/pod_pairing_select.py`: `"team"` in `PAIRING_MODES`.
- `bot/services/pod_draft_manager.py`: emits `teamDraft` in `_emit_session_settings` (gated on `pairing_mode == "team"`); validator accepts `"team"`; manager attrs `team_map`, `team_victory_announced`.
- Round-embed notices (general pod polish, not team-specific): `REPORT_NOTICE` / `DECK_IMAGE_NOTICE` + `_round_notice_lines` — report prompt on **every** round while a match is unreported, deck-image/P1P1 warning round 1 only, both drop once the round completes; **no** Fast Bracket "waiting" footer (the per-slot "waiting on Round N" says enough). Tests updated in `test_pod_round_embed.py`.

### Prototype only — the intended FINAL UI, lives in `bot/commands/testlobby.py`
- `!test teams` → the V2 board (`_TeamV2Board`, `_TeamV2View`, `_TeamV2Button`, `_TeamV2ReportSelectView`, `_TeamV2ReportSelect`), plus helpers `_TEAM1`/`_TEAM2`/`_TEAM_ARENA` (fictional long-name roster to stress-test), `_TEAM_ROUNDS` (the rotation), `_TEAM_REPORT_OPTIONS`, `_team_block`, `_preview_match_line`.
- `!test teamreveal` → `_team_reveal_embed` (the Phase 2 reveal).
- These are in-memory, no DB, no scoring — pure visual/interaction prototypes.

### ⚠️ Built but SUPERSEDED (must be reworked during graduation)
When team mode was first wired into `pod_tournament.py`, it rode the **existing round-gated Swiss flow** (posts round embeds one at a time via `advance_to_round`, gated by the grace window). That predates the single-board decision and is **not** the final design. The team code currently in `pod_tournament.py` (≈lines noted below) implements that gated approach and should be **replaced** by the board model, not kept:
- `_setup_teams` (post-draft assignment — move to `startDraft`), `_persist_teams_sync`, `_load_teams_sync`, `_load_team_discord_ids_sync`, `_persist_team_thread_ids_sync`, `_create_team_threads`, `team_label`, `team_emoji`, `_team_pairings`, `_attach_team_flags`, `_team_round_embed`, `_team_scores`, `build_team_final_embed`, `_announce_team_victory`, `TEAM_GROUP`, plus team branches in `advance_to_round`, `round_embed`, `round_groups`, `_load_round_states`, `render_round_states`, `_advance_locked`, `_post_or_update_live_standings`, `_grace_expire`, `_regenerate_next_round`.

Some of this (pairing dispatch, team scoring, thread creation, victory announce, `team_label`/`team_emoji`) is reusable; the round-gated *rendering* (`_team_round_embed`, the per-round posting) is what the board replaces.

### Remaining — the graduation
1. **Extract team logic into its own module(s).** `pod_tournament.py` is 4263 lines; do not grow the team footprint inside it. Create e.g. `bot/services/pod_team_board.py` (the V2 board render + button/select interaction, graduating the testlobby prototype) and `bot/services/pod_team_flow.py` (assign teams on `startDraft`, post reveal, post board at `endDraft`, open+link threads, finalize/announce winner). `pod_tournament.py` keeps only thin dispatch hooks (`if pairing_mode == "team": delegate`). Move the reusable team helpers out of `pod_tournament.py` into these modules.
2. **Honor `seating_mode` for team mode** (Random / Manual / Leaderboard — all in scope; teams = seat parity of the resulting order). Manual and Leaderboard already push a known order via `setSeating`; the one change is **Seats: Random under team mode** — have the bot shuffle and push the order via `set_seating_order` (`setRandomizeSeatingOrder(False)` + `setSeating`) instead of `apply_seating_mode`'s current `setRandomizeSeatingOrder(True)`, so the order is known at start. Decide the order **once** (`manager.desired_seating`), let `_reapply_seating_if_set` re-assert it before `startDraft`. Then **assign teams on `startDraft`** (from that locked seating, in `_start_draft` after `_seed_participants_at_draft_start`), persist `participant.team`, and **post the reveal** (Phase 2). For team mode the reveal (title `🎉 Team Draft started`) **replaces** the generic `**🎉 Draft started!**` banner at `pod_draft_manager.py:1213` — post the reveal instead, not both. Remove the post-draft `_setup_teams` assignment.
3. **Post the board at `endDraft`** (Phase 3) as the team match surface, replacing the gated per-round embeds for team mode. Bind the `Section` report buttons to the real `_handle_result_submission` path (commit → recolor board → propagate), keeping the `_advance_lock` protection.
4. **Open the two private team threads** at Phase 3, add each side's linked Discord members, post the one-line intro **with a link to the board message** and the team's voice room invite, then silent. Persist thread ids.
5. **Finalize on all matches reported** (not round-3-grace): write per-player records (existing `finalize_champion` path → pod points), announce the winning team, show final Wins on the board. Suppress the single-champion / trophy-hype announcement for `pairing_mode == "team"`.
6. **Register the board view persistently** so buttons survive restart, and handle rehydration (`rehydrate_active_lobbies`) loading `team_map`.

### Testing / commands
- `!test teams`, `!test teamreveal` (owner-only prefix commands; local dev DB only for the live ones).
- `.venv/bin/pytest bot/tests/` — currently 756 pass. Add graduation tests for: board render states, report → recolor, all-in finalize + winner, team assignment from seating.
- Local DB: `dischord-pg` docker on `:5433`. Migration already applied there.

### Conventions reminder
Test logic not framework; never assert exact user-facing copy (assert branching/data); no first-person in bot copy; long unwrapped lines in specs; commit backend+frontend together only when the user asks (no frontend change needed here — per-player scoring reuses the existing formula). Branch is `master`; never push.
