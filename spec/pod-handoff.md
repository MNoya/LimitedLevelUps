# Pod Redesign Handoff — 2026-07-24

Point-in-time handoff for the next pod work session. Reconciles the earlier ready-check redesign discussion against what has since shipped on `master`, and frames the two priorities that matter now: the multi-table system and the reminder/recruiting system, both of which have complexity-crept and want simplifying more than extending.

Living docs this sits on top of: `spec/pod-workflow.md` (engineering map) and `spec/pod-coordination.md` (player guide). Both are mostly current; the exception is called out at the end.

## Where things are

`drop-sesh` merged; work is on `master`. Relevant to the redesign, these shipped since the discussion:

- **Uniform daily launcher** (`4c30995f`, `1f32c5de`) — one 11:00 ET post, two slots every day (Early 14:00, Late 20:00). Weekend-specific buckets and advance-posted scheduled cards are gone. This was a real simplification; keep going in this direction.
- **Format-aware firing** (`7ba0ed4e`) — `slot_fires_latest` fires a slot only when the latest-set-seatable count reaches the threshold, so flashback-only clickers no longer force a latest pod nobody there wanted. This already implements a chunk of the "format-aware `format_at_fire`" seam from the discussion.
- **Format-lock** (`c81e5dd4`) — `PodSignal.format_locked` gates the whole Latest/Flashback preference system off for every pod except a graduated launcher slot. `/draft` pods, championships, and mocks pick their set up front. Clean separation; the preference machinery now has exactly one entry point.
- **Set Championship + rebuilt T-60 roster reminder** (`d1f53f1c`, `becbf5e0`) — the reminder now posts a roster grouped by format with Sign Up / Can't / Format Preference buttons and no Maybe at that stage.
- **Closed Decklist mode** (`568e4f32`) and progressive team-draft round posting (`ed9e2634`) — orthogonal to the two priorities below.

## Still relevant from the ready-check discussion

The two open decisions are still open, but the ground shifted:

1. **Team draft at the ready check** — separate button vs conversion of a stalled group. Still undecided. Note the current code already has *five* different team-vote eligibility rules (see Priority 2), so "how team draft gets offered" is itself part of the complexity problem, not just a redesign choice.
2. **Multiple flashback tables** — two buttons vs collapse to one winning set. Still undecided, and this is now entangled with the fact that the automatic format-split path is effectively not wired (see Priority 1).

The core recommendation from the discussion holds and is now more clearly the right lever: **resolve format and table shape at one explicit ready-check moment via self-selection, instead of continuously inferring table compositions.** That is the same move that simplifies both priorities below.

## Priority 1 — Multi-table system

**What actually forms a second table today:**

- The **leftover offer** at real draft-start (`offer_second_table`, `pod_table.py`) — posts only if a full table's worth of Yes/Maybe is left unseated.
- **Manual `/pod-table`** — a mod opens table N, optionally format-preset.
- Format-preset handoff keeps a still-gathering format table recruiting past table-1 seating.

**What does not fire on its own:** the intended automatic latest/flashback split. `should_offer_format_poll` (`pod_format_interest.py`) has no production call site — it is defined and unit-tested but dead in the live path. So `assess_format_split` (armed T-5) no-ops unless someone manually posted a Format Vote via `/vote-format`. In practice the "split the room into a latest table and a flashback table automatically" behavior is not happening without a manual trigger. Verify this before acting on it, but it matches the felt problem that multi-table is not great.

**Why it is hard to reason about:** there is no single allocator. The "8 here, 6 there, N leftover" logic is spread across `Composition` properties, `format_teams` + `fills_latest`, `pick_second_table` + `_tally_interests`, and an inline leftover computation in `offer_second_table`. `fills_latest` is a four-way branch (threshold vs both team counts, with a "only if the other team has dedicated members" caveat) that drives the launcher render, the card render, and the split gate all at once. Change it in one place and three surfaces move.

**Simplification direction:** collapse the distributed, continuously-recomputed allocation into one explicit decision at the ready check. Instead of `fills_latest` inferring team assignment on every render and a separate (dead) auto-poll gate, present the viable tables as self-select buttons at T-10 and let people pick. The bot surfaces counts and fires a table when it clears threshold; it does not solve an assignment. This deletes `fills_latest` as a render-time allocator, removes the dead format-poll path, and makes "which flashback set" a vote that resolves once, before the buttons appear.

## Priority 2 — Reminders / recruiting

**The timed surfaces a single pod fires between fire and start:** T-3h / T-2h / T-1h underfill nudge beats, T-60 roster reminder, T-60 prelobby team-vote, T-10 lobby open, T-5 format-split assessment, T-0 at-start team-vote, T-0 second-table offer. That is roughly six independently-scheduled surfaces, several with their own gating.

**Where special cases pile up:**

- `_arm_underfill_beats` — downtime catch-up: `run_at <= now` plus `created_at <= run_at` gating, with the catch-up beat inheriting the missed beat's resurface/ping behavior. Subtlest scheduling code in the subsystem.
- `_nudge_ping_role` / `_claimed_ping_role` — ping fires only on beats in `ping_hours` AND within `ping_close_gap` of the aim AND when the bucket role resolves, layered over an atomic once-per-signal claim, layered over resurface-vs-edit mention re-carrying.
- `_find_nudge` marker disambiguation — launcher slots share one signup URL, so the living-message lookup depends on the bolded pod name rendering identically. Fragile coupling of message-finding to copy formatting.
- Team-vote size fan-out — five eligibility rules for one card: prelobby (==6), auto (==6), armed-at-fill (even and <=6), manual (>=4), and `adopt_existing_team_vote`'s `(needed-1)*2` back-computation.
- `add_roster_fields` / `_add_format_split_fields` — plain-vs-split decision, championship include-No override, per-team Yes/Maybe sub-grouping: three orthogonal special cases in one renderer shared by two surfaces.

**Simplification direction:** cut the number of timed surfaces and the number of eligibility rules. Candidates: fold the T-5 format-split assessment into the ready check (it no-ops today anyway); unify the five team-vote size rules into one; and let the roster renderer stop branching on format once format resolution is a single explicit step rather than a per-render inference. The underfill living-message + ping gating is the one piece carrying real weight and is worth keeping, but its marker-based message lookup is a fragility worth replacing with a stored message id.

## The unifying lever

Both priorities have the same root cause: the system tries to compute exact table compositions and breakdowns implicitly and continuously (a render-time allocator, auto-split gates, per-count team-vote rules, a T-5 settle step). Moving format and table-shape resolution to one explicit ready-check step with self-selection removes the need for most of that machinery. It is not primarily a new feature — it is the simplification that lets a lot of the current special-casing be deleted. Scope the redesign as "delete complexity by making one decision explicit," not "add a ready-check surface on top of what exists."

## Decisions to make before building

1. Team draft: one offer path (which?), replacing the five current eligibility rules.
2. Flashback tables: one winning set with same-set overflow, or top-two sets as parallel tables.
3. Ready check: self-select buttons (recommended) as the single format/shape decision point, replacing the render-time allocator and the dead auto-split path.

## Doc maintenance note

`spec/pod-workflow.md` is accurate on current lifecycle but its "proposed next state" section predates the shipped work above (it still frames `format_at_fire` as an untouched seam and does not mention `slot_fires_latest`, `format_locked`, or the dead `should_offer_format_poll`). Refresh that section when the redesign scope is settled so the map stops proposing things that partly exist.
