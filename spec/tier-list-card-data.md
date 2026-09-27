# Tier List card data

17Lands play data next to Alex and Marc's Set Review grades on the Tier List card popup, so a reader can compare the hosts' early read with how the card actually performs.

## Design decisions

- **Tier-listed sets.** `card_stats_sets.json` at the repo root lists the sets that get card data, and the three-color sets (`threeColorSets`) that also get the ten three-color decks. The bot and the site both read it.
- **Premier Draft only.** One cut of the data per set, the one players quote. No Traditional or top-player split.
- **Source is 17Lands `api/card_data` directly.**
- **Percentile grading.** Per deck, a normal distribution is fitted to GIH WR over cards with at least 100 games in hand, and a card's percentile maps to A+ through F with fixed cutoffs (A+ 99, A 95, A- 90, B+ 85, B 76, B- 68, C+ 57, C 45, C- 36, D+ 27, D 17, D- 5). Only cards over 500 games in hand get a grade.
- **Raw stats in the file, grading in the browser.** A baked file stays valid if the grading changes, and the grading lives in one TypeScript module.
- **Decks.** Every set gets the ten two-color pairs; sets built around three-color decks (TDM, KTK, SNC) also get the ten three-color combinations, in WUBRG order as 17Lands expects.
- **The data grade is labelled "17L" / "17LANDS".** It never says "Data grade" in the UI.

## Data

The file shape (`CardStatsFile`, keyed by card name: one overall block plus a GIH WR and games-in-hand pair per deck) is built in two places that must stay in sync: `bot/services/card_stats.py` for the live set and `frontend/src/data/cardStats.ts` for baking, which also owns `gradeCardStats` and the 17Lands URL helpers. Cards join to the Tier List by name; 17Lands' `card_id` on its card detail page is the `mtga_id` stored in the file.

Every 17Lands call is sequential, 7 seconds apart, matching the bot's leaderboard limiter. Parallel calls got this machine rate-limited for an hour during the first backfill. A refresh fetches the overall list first and reuses the previous per-deck data when every card's game count is unchanged, so a quiet refresh costs one call.

## Serving

`/api/card-stats/<SET>` (`functions/api/card-stats/[setCode].ts`) is the one URL the site reads.

- **Rotated sets** are baked to `frontend/public/card-stats/<set>.json` and served from the CDN with a one-day browser cache. They never reach 17Lands.
- **The live set** is the active set when it has no baked file. It is refreshed at the start of each scheduled leaderboard refresh for its first 30 days, then once a day, skipping runs while the KV copy is under 20 hours old, ahead of the player fetches that take tens of minutes, by the `refresh-cron` Railway service (`bot/scripts/refresh_periodic.py`, cron `0 1,5,9,13,17,21 * * *` UTC), using the same 7-second limiter, and written to Cloudflare KV through the API (`CardStatsKv` in `bot/services/card_stats.py`). The Function never calls 17Lands: it reads KV (binding `CARD_STATS`), keeping a local Cache API copy in each data center that is fresh for 15 minutes and served instantly while it refreshes. The namespace is `llu-card-stats` on the chordocoach Cloudflare account, bound to the `limitedlevelups` Pages project for Production and Preview. The in-bot tick (`AUTO_REFRESH_TIMES`, only when `AUTO_REFRESH_ENABLED`, which is off in production) does the same. Both need `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_KV_NAMESPACE_ID` and `CLOUDFLARE_KV_TOKEN`, set on `refresh-cron`; the token is a KV-only chordocoach account token. Without them the refresh is skipped.
- **Before release** 17Lands returns no cards, so the live set's file is empty and the Data button shows disabled. The first cron refresh after games exist fills it in; nothing needs to be switched on.
- **Local dev** has a Vite stand-in (`cardStatsDevApi` in `frontend/vite.config.ts`) that reads a gitignored override in `cache/card-stats/<set>.json` first, then the baked file, and builds live from 17Lands only when called with `?bake=1`.

## UI

- **Card popup** (`frontend/src/components/TierGrid.tsx`, `CardDataPanel.tsx`): a Data button next to Video and Transcript opens a side panel on desktop, three columns in total: card, decks, stats. Data replaces Video and Transcript rather than stacking with them, and it is wider than they are. The grades strip shows a 17LANDS grade cell, hidden while the Data panel is open because the panel's header already shows it. On phones the Data view stacks under the card like the other views.
- **Deck column**: AVG first, then every deck with at least 100 Games In Hand, most Games In Hand first. Decks at or under 500 show dimmed with no grade. Every deck with enough games shows, not only the set's signpost archetypes. Each row is the pair's mana symbols and a chip with the grade and win rate. No collapse; everything shows.
- **Stats**: full-word labels, each with a one-line description as its tooltip. A tooltip opens anywhere on a stat, label or value. Desktop keeps ALSA, ATA and IWD as a header row over a six-row grid; phones fold them into a single ten-row list, draft picks first, then game counts, then win rates.
- **Grid**: a GRADES toggle in the filter bar places cards by 17L grade instead of the LLU grade, hides the LLU trend arrows, and swaps the subtitle for a link to the set's 17Lands card data. An over- or under-performer badge was tried and dropped as noise.
- **Header**: a 17LANDS link to the card's 17Lands detail page (by `mtga_id`, falling back to the set's card data page) sits on the caption row, next to the overall GIH WR grade over the deck column.
- **Motion**: the Data panel slides open and closed by width only, keeping its height and its width until the slide ends so nothing reflows mid-animation. The 17LANDS cell on the card fades and collapses with the slide instead of vanishing in one frame. The Expand button only belongs to Video and Transcript; it slides in with their panel and hides instantly on close.
- **URL**: `?review=data` opens the Data view, like `transcript` and `video`.

## Performance work shipped alongside

Measured on production before and after, fresh browser contexts:

| Scenario | Before | After |
|---|---|---|
| Card link HTML first byte | 2073ms | 45ms |
| `/tier-list/HOB` grid rendered | 2750ms cold | 369ms |
| Supabase requests on a Tier List load | 1 | 0 |
| Supabase requests when opening a card | 2 | 0 |

- Link-preview card meta is resolved only for crawler user agents (`isLinkPreviewCrawler` in `functions/_middleware.ts`); people get the set meta with no lookup.
- `restGet` in `functions/_shared/public-data.ts` caches Supabase reads with the Cache API; the `cf.cacheTtl` subrequest cache it used before did not hold Supabase responses.
- The set list, Set Review mentions and transcripts are served from cached Functions (`/api/sets`, `/api/set-review-mentions/<SET>`, `/api/transcript/<id>`), one hour each, so the Tier List makes no Supabase calls.
- The consensus tier list refreshes in the background after 10 minutes; Alex's and Marc's lists are kept 30 days.

## Adding a set

1. Add the code to `sets` in `card_stats_sets.json` when the set's Tier List is added, and to `threeColorSets` if its decks are three-color. The bot starts refreshing it once it's the active set.
2. After the set rotates, bake it: delete any old `frontend/public/card-stats/<set>.json` and any local override in `cache/card-stats/<set>.json` (the dev server serves the override first), fetch `/api/card-stats/<SET>?bake=1` from the local dev server, save the response there, and commit it.
