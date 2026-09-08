# Pod card data

A card-statistics pipeline fed by the Draftmancer logs the bot stores on every pod draft. It is set-agnostic: any set whose pods are tracked gets a board with no schema change. Peasant Cube is the first (and only) tracked set today; the site page lives at `/pods/PEASANT/data`.

The design goal is that the numbers improve on their own as pod play accumulates — no migration, no re-walk of history, no code change when a card enters the pool or another set starts being tracked.

## Design decisions (still current)

- **Website first.** A sortable card table on `/pods/<SET>/data` is the surface; there is no Discord command (an earlier `/cube-card` was dropped).
- **17lands column vocabulary.** Use the names the community already reads, verbatim.
- **Every metric sortable**, card name included.
- **All-drafts board, season-sliceable.** Storage keeps per-season raw sums, so the "All Seasons" view is just no filter and a season view is one predicate.
- **Set-agnostic rows.** Rows are keyed by `set_code`, so a second tracked set costs a row, not a schema change.
- **Maindeck at face value.** Whatever a player leaves in the maindeck counts (see the accuracy limitation below).

## Columns (shipped)

`# Seen` · `# Picked` · `ALSA` · `ATA` · `# GP` · `% GP` · `GP WR`, plus the card name column. `% GP` carries a muted `(N)` = decks maindecked. A `MIN DRAFTS` filter uses each card's draft count (dropped columns from earlier drafts: Lap %, # Pool, # Drafts as a visible column).

## Data model

- `pod_card_stats` — one row per `(event_id, card_index)`, columns `set_code`, `card_name`, sighting sums (`seen_count`, `last_seen_sum`, `saw_count`), the taken pick (`pick_num`, `seat`, `maindecked`), and card metadata. Fully derived from the stored draft log; rebuilt per event, never hand-edited.
- `public_pod_card_stats` / `public_pod_archetype_stats` — per-season raw-sum views grouped by `(set_code, season, card / deck_colors)`, season = the set whose date window contains the draft. Game columns join `pod_draft_matches` (winner-relative score, per seat) at read time. The frontend sums the rows in scope and divides (All = no season filter); the archetype view folds `deck_colors` into a main color pair, mono and 3+ into "Other".
- One migration: `alembic/versions/c0b3ca7d5747_pod_card_stats.py` (table + both views + anon grants), parented on `tr4nscr1pt5ep` so master keeps a single alembic head.

## Pipeline

`bot/services/pod_card_extract.py` (`extract_event_rows`, `rebuild_pod_card_facts`, `reingest_pod_card_facts`, `tracks_card_data` — gates to PEASANT) runs on every pod persist (`pod_draft_manager._persist_draft_log_gz`, `pod_log_ingest.py`). `bot/scripts/reprocess_pod_cards.py` replays all tracked events from stored logs with no 17lands fetch.

## Deploy to prod (not yet shipped)

1. Commit + push — the migration applies on bot startup; the two views + anon grants are created.
2. Run `python -m bot.scripts.reprocess_pod_cards` against prod `DATABASE_URL` to populate `pod_card_stats` from the pod logs already stored.
3. Confirm the site's Supabase client exposes `public_pod_card_stats` + `public_pod_archetype_stats` (they carry `GRANT SELECT ... TO anon`).

## Known limitation — maindeck accuracy

`% GP` and `GP WR` are only as accurate as each seat's Draftmancer decklist captured at draft time. Players who build or tune outside Draftmancer aren't reflected, so a few seats store the whole pool as "main". `reprocess_pod_cards` can't fix this — it re-reads the same stored compact; the real signal is missing. Counts, ALSA, ATA, `# Picked`, `# Seen` and the color/archetype win rates are unaffected.

Roadmap to improve it, in preference order:
1. **17lands-sourced decks** — cleanest real maindeck; no ingest path exists yet.
2. **OCR-reported decklists** (other branch) — let a player report a final list and rewrite `pod_card_stats.maindecked` for their `(event_id, seat)`; the views recompute for free.
3. **Interim heuristic** — discount or flag seats whose `main == full pool` so they don't skew the rate.

## Key files

Frontend: `pages/PodCardDataPage.tsx`, `components/PodCardFilterBar.tsx`, `components/ArchetypePanel.tsx`, `components/PodRecentTrophies.tsx`, `data/podCards.ts`, `data/podArchetypes.ts`, `data/cardImages.ts` (shared app-wide art cache), `data/realApi.ts` + `hooks.ts`.
Backend: `bot/services/pod_card_extract.py`, `bot/models.py` (`PodCardStat`), `bot/scripts/reprocess_pod_cards.py`.
