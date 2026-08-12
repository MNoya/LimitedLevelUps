# Set Awards

End-of-set awards: an admin-posted ceremony recognizing standout drafters across the set, plus a per-player self-view behind a persistent button. All backend. The `/set-awards` slash command needs `!sync` after schema changes.

## Files

- **`bot/services/set_awards.py`** — compute logic + wording formatters, no Discord/presentation. Per-award ranking, the greedy assignment, and the personal fun-stat computations. Each award's detail wording lives in a formatter function (`first_striker_detail`/`_ceremony`/`_gap`, `seize_detail`/`_ceremony_detail`, `climber_detail`, `specialist_detail`/`_ceremony_detail`, `revel_detail`, `mvp_detail`) so the live command and the `!test` harness share one source and can't drift.
- **`bot/commands/set_awards.py`** — the `AWARD_SPECS` catalog (emoji/name/tagline/display-order + per-award `connector`/`you_verb`/`miss`), the Components V2 builders (`build_set_awards_view`, `build_my_awards_view`), `build_data` (winners/runners → `SetAwardsData`), the cog (`/set-awards` + the "How did I do?" button), and presentation helpers.
- **`bot/commands/testawards.py`** — `!test setawards [gated]` builds sample `AwardCandidate`s through the live `build_data`, so layout, wording, and runner-up logic all exercise the production path. `!test myset [full|off]` previews the personal view. Fictional names.
- **`bot/commands/descriptions.py`** — `SET_AWARDS`.
- **`bot/main.py`** — registers `setup_set_awards` (cog + `bot.add_view(persistent_my_awards_view())`).
- **`bot/scripts/set_awards_results.py`** — dev preview of the DB awards against prod: `DATABASE_URL=$SUPABASE_DB_URL .venv/bin/python -m bot.scripts.set_awards_results`.

## The six awards (ceremony, `/set-awards`)

Reveal/display order = `AWARD_SPECS`. Pre-release events are excluded (anything before the set's release **date** in ET).

1. **⚔️ First Striker** — first trophy of the set (Sealed and Quick queues excluded), anchored to the earliest day-one draft start `t0`. Winner (ceremony): "trophied **{1h 35m}** after set release" (full delta). Runner-up: "earned one **{1h}** later" (coarse, single unit). Personal: "You trophied **{own delta}** after set release".
2. **☀️ Seize the Day** — most trophies in any rolling **24h** window. Winner (ceremony): "claimed **{n} trophies** on {Mon Day}" (the tagline carries "24h", so the line gives the date). Runner-up: "**{n} trophies**, {N days after|before|the same day}". Personal: "claimed **{n} trophies** in 24h on {Mon Day}". **Featured-runners exception** (`ALLOW_FEATURED_RUNNERS`): shows every tied co-runner-up even if they won another award.
3. **📦 Revel in Riches** — most Arena Direct sealed boxes. "won **{boxes}** boxes in {n} events". Higher win-priority than The Climber (see assignment).
4. **🧗 The Climber** — fastest rank ascent to Mythic within a single ranked month. **Qualify**: start tier Gold or lower (a 3+ tier climb); trivial high-start hops are excluded. **Score** = `CLIMB_TIER_WEIGHT × tiers_climbed − days` (higher wins); ties break on fewer days, then lower start tier. Each player is represented by their highest-scoring climb. "climbed from {StartTier} to Mythic in **{n} days**".
5. **🎯 The Specialist** — best win rate vs the community field for an archetype, sample-weighted z-score. Shows the player's **best archetype regardless of whether they beat the field** (the must-beat-field filter was dropped); floors ≥20 player games, ≥40 community games. Ceremony: "**{wr}%** on **{arch}** over {games} games, vs field of {fw}%". Personal: "a **{wr}%** win rate with **{arch}** over {games} games, vs field of {fw}%". A runner-up sharing the winner's archetype drops the field clause (split on `SPECIALIST_FIELD_SEP`).
6. **🚀 Most Valuable Pod-Drafter** — most pod drafts played during the set window. A seat counts once the participant has a record, and the window is matched on the pod's **date**, not its format code, so every pod counts: the active set, flashbacks, cube, Peasant. "played **{n}** pod drafts". Field rule differs from the other five: pods are public, so `load_contexts` keeps **every active player** and only reads 17lands events for opted-in ones. A pod-only or opted-out player can win this award and no other.

### Assignment
Greedy in `CEREMONY_ORDER` (win-priority), one award per player; runner-ups exclude winners (except `ALLOW_FEATURED_RUNNERS`); ties surface co-runner-ups; the **Premier > Trad > Quick** tiebreak decides **winners only**.

`CEREMONY_ORDER` (win-priority) is intentionally **decoupled** from `AWARD_SPECS` (display order): Revel in Riches sits above The Climber in win-priority so it claims a doubly-eligible player first, but the embed still reveals in the original display order. Keep them separate on purpose.

**Names**: a winner/runner is rendered as a mention (`<@id>`) only when the player is a member of the **posting guild**; otherwise their **bold display name** is used (so a cross-guild winner never shows as `@unknown-user`). In a **thread**, names are always bold (never mentions), so a live test pings nobody.

## Personal view ("How did I do?" button)

There is **no `/my-set-awards` command** — the persistent green button (`custom_id="set_awards:my"`) on the final ceremony frame is the only entry, registered via `bot.add_view()` so it survives restarts. The view shows **every** category: earned ones carry a rank badge (🥇/🥈/🥉 or `- #N`) and a "You …" line; categories the player didn't place in show a muted reason ("No Arena Direct boxes this set", etc.). A clicker with **no Player row** gets a `/join` CTA; a **joined** clicker with no events this set gets "on the leaderboard, but no {SET} drafts … contact an admin".

Personal-only fun stats (always shown, earned or not — negative awards use a "Safe!" framing):
- **🔥 Trophy Streak** (≥2): longest consecutive trophy run. "You scored **{n} trophies** in a row {between … and …}".
- **🪙 The Merchant** (≥3): longest consecutive 2-1 run in Trad, "out of {n} events". Under threshold: "Safe! Only {n} 2-1s in a row in Trad, out of {n} events".
- **🥀 Heartbreakers** (≥3): total 6-3 finishes in **Premier** (Premier-only), "out of {n} events". Under: "Safe! Only {n} Premier 6-3 finishes total, out of {n} events".
- **🥶 Cold Run** (≥3): longest consecutive Premier drafts without a 4+ win finish. Under: "Safe! Only {n} Premier drafts in a row without a 4+ win".

Counts are spelled out only when the preceding token is a number (e.g. after "2-1"/"6-3"); fun-stat ranks come from `rank_in` over the payload's `FUN_RANKED_STATS`.

## Mechanics

- **Loading**: every award is computed from the DB on each call, ceremony and button alike. `load_contexts` pulls the set's draft events, stats rows, and pod-draft counts in three queries; there is no payload cache.
- **Avatars**: thumbnails use `avatar_url(discord_id, avatar_hash)`; `avatar_hash` is captured on join/relink/auto-link/pod-link, so it is fresh as of the player's last signup/relink.
- **Reveal**: the drumroll edits a Components V2 message in place. A thread invocation renders bold names (no pings, the live-test path); a real channel mentions members.

## Testing

- `!test setawards` / `gated` — full ceremony / timed reveal, built through the live `build_data`.
- `!test myset` / `full` / `off` — personal view: mixed / all-earned / all-missed.
- Dev preview against prod: `DATABASE_URL=$SUPABASE_DB_URL .venv/bin/python -m bot.scripts.set_awards_results`.

## Conventions to keep
`AWARD_SPECS` is the single source of each award's copy/emoji/display-order; `CEREMONY_ORDER` is the separate win-priority. Per-award detail wording lives in the service formatters — both the live computation and the test fixtures attach to them, never duplicate award copy. Service holds logic, command holds presentation.
