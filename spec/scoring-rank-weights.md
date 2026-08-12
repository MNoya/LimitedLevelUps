# Scoring formula v2: rank-weighted Premier trophies, Sealed 10

Covers the scoring change agreed 2026-08-04, revised 2026-08-10 to leave Trad alone, and the analysis behind it. Read this before editing `scoring_buckets.json`, `bot/scoring.py`, `frontend/src/data/scoring.ts`, or `ScoringExplainer.tsx`. Built, with the cube boards the one open item.

## The change

| Group | Points |
|---|---|
| **Premier** | 10 base. **Platinum trophy 11, Diamond trophy 13, Mythic trophy 15.** Gold and below stay at 10 |
| Trad | 8, unchanged |
| **Sealed** | **10** (was 8) |
| Quick | 4, unchanged |
| LCQ Draft 1 / Draft 2 | 30 / 10, unchanged |
| Pod trophy / 2-1 | 5 / 2, unchanged |

Three rules govern the rank weights:

1. **The weighted count feeds the numerator only.** Trophy rate stays on raw trophy counts, so each format's rate is unchanged and only the multiplier moves. Concretely `raw_group = weighted_trophies × points × (trophies / events)`.
2. **The whole Premier group is weighted, aggregated.** `PremierDraft` and `ContenderDraft` are the same queue from the player's point of view. `PremierDraft`, `ContenderDraft`, and `PremierDraftRemixArtifacts` carry rank at 96-99%; `DraftChallenge`, `OpenDraft_D1_Bo1`, and `ArenaDirect_Draft` carry none and fall to a 1.0 multiplier without needing a rule, so no per-format allowlist is required.
3. **Confidence is untouched.** `T/(T+2)` still builds from raw trophy count across groups.

**Applies retroactively to every set.** This reverses an earlier plan to version the formula from HOB onward. There is no ruleset resolution, no set code threaded through `compute_score`, and the site explainer stays a single global formula. Cube boards are the one exception, and they are still an open item below.

The 6-win Arena Direct box factor was modelled and rejected: too little effect for the complexity.

## Why these numbers

Per-event score value works out to `points × trophy_rate²`, because `raw_group = trophies × points × trophy_rate` and `trophies = events × trophy_rate`. Trophy rate therefore enters **quadratically**, which is what makes small rate differences produce large ranking effects. "Parity" below means one drafted event contributes equally whichever queue it was played in — a fairness standard based on time invested, and a choice rather than a law.

Rank weighting is adopted as a **prestige signal**, not a difficulty adjustment. The data does not support a difficulty reading: Premier trophy rate is flat across tiers (Gold 0.198, Platinum 0.196, Diamond 0.200, Mythic 0.219) and Arena deranks monthly, so Mythic share swings from 6.5% to 32.7% depending on where in the month a player drafts while trophy rate and winrate hold constant. The `reference_arena_rank_data` memory has the full measurements. This was a deliberate decision with the evidence on the table.

Trad's distortion is a threshold asymmetry, not a tougher field. `wins` means match wins in Trad (max 3) and game wins in Premier (max 7), the trophy gates are 3-0 in matches versus 7 game wins before 3 losses, and 124 players with 25+ events in both formats convert at the same implied per-game rate (+0.012 mean in Trad's favour, 91 of 124 better in Trad). See the `reference_trad_premier_threshold` memory.

**Trad keeps its 8 and is corrected indirectly.** An earlier draft cut it to 7. It is left alone because the rank weights already do most of the work: Premier's effective points rise about 22%, which pulls Trad from 1.72× down to 1.41× on MSH and 1.82× to 1.50× on SOS without touching the Trad weight at all. Taking Trad down as well would stack two corrections on the same distortion. This also costs Trad players nothing directly, so the gap closes because Premier rises and not because their queue was devalued, and it is the smallest reordering of any option (top-50 mean move 2.46 against 3.36 at Trad 7 and 4.84 at Trad 6). Parity sits between 6 and 5 and is deliberately not the target.

Per-event value relative to Premier, before and after, measured on prod:

| | Trad | Quick | Sealed |
|---|---|---|---|
| MSH before | 1.72× | 0.90× | 0.53× |
| MSH after | 1.41× | 0.74× | 0.54× |
| SOS before | 1.82× | 0.62× | 0.36× |
| SOS after | 1.50× | 0.51× | 0.38× |

Effective Premier points land at 12.1-12.2 once averaged over the real rank mix, consistent across every sample. Note that Sealed at 10 roughly holds its existing relative position rather than improving it, since Premier gains about 20% at the same time — reaching 0.7× would take about 13 points. Trad remains the largest gap by design.

## Board impact

On the top 50, 40 players move on MSH and 45 on SOS, mean absolute move 2.46 and 2.44, largest single swings 10 and 8 places. One player enters and one leaves the top 50 on each board. Both #1 positions hold and MSH's top four is unchanged.

Nearly all of that comes from the rank weights. Isolating Sealed 8 to 10 on its own leaves a mean move of 0.82 on MSH and 0.44 on SOS.

Retroactive application is safe on data coverage: Premier-group rank runs 92-98% every year back to 2020, and only 619 of 26,348 trophies in the entire log lack a rank, so no era is systematically penalised.

## Implementation

The blocking structural item: **`player_stats` has no rank dimension.** Its grain is `(player_id, set_id, format, expansion)` with a plain integer `trophies`, and the frontend's `public_*` views are built on it, so rank-weighted trophies cannot be expressed there today.

Add a `weighted_trophies` float column to `player_stats` rather than adding rank to the grain — putting rank in the key multiplies row count and breaks the unique constraint plus every consumer. The rebuild is already a `DELETE + INSERT … SELECT GROUP BY` per touched `(player, set)` sourced from `draft_events`, which carries `end_rank`, so the weighted sum has everything it needs at rebuild time.

1. `scoring_buckets.json` — Sealed 10 and a `rank_points` block on the Premier group. Weights are written as points in the same unit as everything else in the file, and the code divides by the group's base to get the multiplier
2. Migration `c1b5e6f8a2cd` adds `player_stats.weighted_trophies` and seeds it to `trophies`, so a row is never wrong before the rebuild runs
3. `bot/services/refresh.py` — `trophy_weight_sql` builds the rank CASE off `scoring_buckets.json` and the rebuild carries one more SUM in the GROUP BY it already runs. Generating the SQL from the JSON is what keeps the weights out of the migration, so there is still one source of truth
4. `bot/scoring.py` — `_aggregate` reads `weighted_trophies` for the numerator and `trophies` for the rate and the confidence total. A row with trophies and no weighted count scores unweighted, so a writer that predates the column degrades to the old formula instead of to zero
5. `public_player_format_breakdown` exposes the column. `public_leaderboard` needs nothing: it is a whole-set aggregate that carries no score
6. `frontend/src/data/scoring.ts` mirrors the change, and `groupTotalsFromBreakdown` replaces the four copies of the breakdown-to-GroupTotals map
7. `frontend/src/components/ScoringExplainer.tsx` — Sealed updated, and `<Leader nested>` renders the three rank rows indented under Premier Draft. The component shows on the About page and in the modal opened from `ScoringInfoButton` in `LeaderboardTable.tsx` and `PointsBreakdown.tsx`
8. Backfill with `python -m bot.scripts.rebuild_player_stats`, which re-aggregates from existing `draft_events` with no 17lands fetch

Tests cover the weighted numerator against an unweighted rate, the group aggregation across `PremierDraft` and `ContenderDraft`, and a row with no weighted count scoring unweighted. `test_scoring.py` reads group weights through `points_for` rather than repeating them, so changing a weight does not rewrite tests whose subject is which formats land in which group. Per repo convention, do not assert on user-facing copy.

## Open items

- **Whether cube boards carry the rank weights.** Cube events are `PremierDraft` rows under the `CUBE` set, so the group weight already reaches them, but neither the bot's `rank_cube_players` nor `public_cube_season_breakdown` carries a weighted count, and both fall back to unweighted. Bot and site agree today, so this is a product choice and not a defect: a Mythic cube trophy currently pays 10 while a Mythic set trophy pays 15. Weighting cube means adding the weighted sum to the cube binning SQL and to the three `public_cube_season*` views.

The earlier open item on where the rebuild applies the weights is resolved: the rebuild SQL lives in `refresh.py`, not in a migration, so it is generated from `scoring_buckets.json` at runtime and keeps both the single source of truth and the in-place SUM.

## Verification

Run against the local database unless a step says prod. Prod is read-only reachable through `SUPABASE_DB_URL` in the gitignored `.env.supabase`; never write to it.

1. `alembic check` reports no new operations, so CI's model/migration drift check stays green. Confirmed 2026-08-09.
2. Effective Premier points land at 12.1-12.2. Measured 12.19 on MSH and 12.09 on SOS against prod, and 12.15 across the whole local database after the backfill. Trad's per-event value falls to 1.41× on MSH and 1.50× on SOS with its weight untouched.
3. Bot and frontend produce identical scores for the same player, since the formula lives in two implementations. `analysis/parity.py` bundles the real `scoring.ts` with esbuild and compares it to `compute_score` over every MSH and SOS player: 219 compared, 0 mismatches.
4. Board movement on the top 50: 40 of 50 move on MSH and 45 of 50 on SOS, mean absolute move 2.46 and 2.44, both boards keep their number one, and MSH's top four is unchanged.
5. After the backfill, `weighted_trophies >= trophies` on every row, and the two are equal on every row outside the Premier group.

The `analysis/` scripts take a set code, so any prior set can be re-run through the same config. They are working tools and not part of the shipped tree.
