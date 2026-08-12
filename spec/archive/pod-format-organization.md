# Pod Format Organization

Turns the loose "let players choose formats and flashbacks" idea into three concrete, additive surfaces. Every decision here is reversible: additive DB columns with real `downgrade()`, new modules that no existing flow depends on, and conservative defaults so a pod with no format signal behaves exactly as it does today.

## The problem, stated precisely

Format and attendance are coupled decisions resolved at different times. You cannot pick the right format until you know who shows, and players will not commit to showing until they know the format. On-demand pods default to the latest set (`active_set_code()`), so the only way flashback demand ever gets served today is a moderator pre-scheduling a specific-set pod two days out. Flashback demand is real (a Jul 17-19 sample showed flashback-only players as the single largest cohort, and five different flashback sets drafted in three days) but invisible: it leaves no trace in the system until someone guesses it into a scheduled pod. The weekday floor is genuinely the latest set; the contested window is roughly Thursday through Sunday.

The goal is organization tools that make standing intent visible enough that the right-format pod fires on its own, without players restating a preference in chat every session, and without ever forcing a latest-set player into a format they did not want.

## The three surfaces

1. **Draft Interest** — a standing, per-player preference (Latest / Flashback / Cube), multi-select, set once and reused. The quiet always-on signal of what each player wants.
2. **Launcher composition board** — the daily launcher shows, per slot, how tonight's signups break down (Latest / Flashback / Flexible), so latent demand is visible while a pod is still forming. Signups seed their interest from their standing preference, so the board is never a cold start.
3. **Flashback format poll** — an in-thread poll, styled like the Team Draft vote card, that lets the players present pick the concrete format for a pod whose format is not settled, and writes the choice through to the live lobby.

## Core principle: one vocabulary, three moments

All three surfaces speak the same interest vocabulary, defined once in `bot/services/pod_format_interest.py`: `LATEST`, `FLASHBACK`, `CUBE`. "Flexible" is not a stored value; it is the derived state of a player who holds both `LATEST` and `FLASHBACK`. Cube is a first-class vocabulary member so the same machinery extends to cube-first players later, but this version ships no cube-specific flow — cube stays a manually scheduled format.

The standing preference is "what I would want." The launcher board is "who is around tonight and up for what." The poll is "let us decide this pod." The board opens seeded from standing preferences; the poll can open seeded from the board. Same data, captured at three points in time.

## Decisions (all reversible)

### Storage

- `Player.format_interests` — `ARRAY(String)`, `server_default='{}'`, not null. Empty means unstated. Mirrors the existing `arena_aliases` array column. A player's durable preference.
- `PodSignalMember.format_interest` — `ARRAY(String)`, `server_default='{}'`, not null. The interest that member brings to this specific signup, seeded from their standing preference on join and overridable on the launcher.
- Both are additive columns with a plain `drop_column` downgrade, copied from the `players.dm_draft_link` migration style. No data migration, no backfill; existing rows read as empty and behave as today.

### Multiple choice everywhere

The standing preference, the launcher toggle, and the in-lobby poll are all **multiple choice** — a player genuinely straddles ("I am up for Latest or Flashback", "I would play NEO or IKO"), and Flexible is the whole point of the market-maker model below. On the poll a click toggles the clicker's vote for that one option, leaving their other votes intact, so a player can back several formats. The bar on each option is its share of the votes cast (a lone first vote reads 100%, like the Sesh poll), and an option locks the lobby when it reaches a majority of the players present and leads outright. The tension this introduces — a "safe" latest-set option that everyone piles onto alongside their real pick — is left as a knob to tune, not a solved problem: the lock target is the majority-of-present count, and it can be raised or the latest option demoted later.

### "Flexible" is the liquidity, not a third silo

A player up for both formats is counted toward whichever format needs bodies to reach quorum. This is the reason surfacing the data pays off: dedicated Latest and dedicated Flashback crowds that each fall short of a table can still both fire when Flexible players fill the gaps. The board must render Flexible as available capacity for both, never as a separate dead bucket, so a minority format never looks doomed when the liquidity to save it is present.

### Conservative firing, decision deferred to the poll

This version does **not** change how or when a slot fires. A slot still fires at the global `pod_signal_fire_threshold` and a fired pod still defaults to the latest set. Format is not auto-switched at fire time, because auto-switching risks stranding latest-only players and cannot be verified without a live draft. Instead the concrete format is resolved **after** the pod opens, among the players who actually showed, by the flashback format poll. `format_at_fire()` exists as a pure seam returning the latest set today, so a future version can make firing format-aware in one function without touching the fire path.

The poll is attached to a freshly opened pod only when the fired roster shows real flashback interest (a threshold on flashback-leaning signups); an all-latest weekday pod never sees a poll. It can also be posted manually. This keeps latest-set players undisturbed and confines the new surface to the contested window where it earns its place.

### Format poll resolution

- Options: the latest set (labelled, so "stay on the latest set" is always a choice), the most recent flashback sets from `recent_released_sets()`, and any player write-ins. Each option button is icon only when the set has an app emoji, the code as a label otherwise.
- Multiple choice: a click toggles the clicker's vote for that option.
- Write-ins are real, votable options, not advisory. The ➕ button opens a modal, the typed set code is added to the poll and the submitter votes for it in one step, and it renders with its set emoji when one exists. Any two-to-six-character alphanumeric code is accepted, since Draftmancer drafts by the lowercased code; the poll caps at `MAX_POLL_OPTIONS` buttons.
- Locks when an option reaches a majority of the present players (`present // 2 + 1`), mirroring the Team Draft vote's `needed`. On lock, the choice writes through `set_event_format(bot, event_id, code)` — the same setter `/pod-settings` uses, which renames the thread, re-emits the Draftmancer set restriction, and refreshes the lobby card — and the poll card edits to a locked record with the buttons removed. A write-in that wins applies the same way; an unregistered code resolves to a nullable `set_id` and drafts by its code.
- Ties do not lock; the pod keeps its current format until an option breaks ahead.
- The card message is the source of truth for the tally, read back off the embed by the bracketed set code and voter mentions, exactly like the Team Draft card, so the poll survives a restart and needs no vote table.

## Reuse, do not reinvent

- The poll card, button, and read-back copy the `bot/services/pod_team_vote.py` pattern verbatim in shape: a `DynamicItem` button keyed on `formatpoll:{code}:{event_id}`, a module-level click-handler registered by the manager at import (no circular import), one `bot.add_dynamic_items(FormatPollButton)` registration in `bot/main.py`, and a `!test formatpoll` preview backed by the same builders so the live card and preview cannot drift.
- The launcher board extends `LauncherSlot` and `launcher_snapshot_sync` with a composition breakdown and adds one persistent multi-select to `PodPollView` for interest, following the static-custom_id persistence the launcher already uses.
- Format resolution reuses `active_set_code()`, `recent_released_sets()`, and `set_event_format` / `update_event_format`. No new format registry.

## Copy

All user-facing strings follow the plain declarative microcopy rule: name the real thing and the real action, literal verbs, no marketing register, no em dashes, no phrasal verbs. Poll-specific copy lives beside the poll builders in `pod_format_poll.py` (as team-vote copy lives in its own module), not in `messages.py`, unless a second caller needs it.

## Tests

Logic only, per repo convention. Unit-test the pure core: interest-set parsing and labelling, the composition tally, `format_at_fire()`, the poll's leader/majority resolution, and the embed tally read-back. No tests asserting exact copy or exercising Discord interaction plumbing; those are verified visually through the `!test` previews.

## Out of scope for this version

- Format-aware firing (a slot firing directly into a flashback pod). The `format_at_fire()` seam is in place for it.
- Cube-specific flows beyond the vocabulary slot.
- A second concurrent table split by format at one slot time (the launcher already supports overflow tables; splitting them by format is a later step).
