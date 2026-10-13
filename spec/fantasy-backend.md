# Pro Play: backend

The game and its rules live in `spec/fantasy-worlds.md`. The migration is `alembic/versions/f4n7a5y1w0c1_fantasy_worlds.py`, revising `e4rlyacc3ss1`. If another migration lands on master first, rebase this one's `down_revision` onto the new head.

## Patterns copied from P0P1

- Member writes go straight from the browser through supabase-js into own-row tables. RLS policies use `auth.uid() = user_id` for select, insert, update and delete, and `authenticated` gets explicit table grants, since PostgREST checks grants before RLS.
- Display names live in a private `fantasy_members` table, filled by a `SECURITY DEFINER` trigger on every pick write, with the same Discord display name expression as `p0p1_voters`. RLS is on with no policy, so only the definer views read it. This keeps the public views off `auth.users` and Supabase's `auth_users_exposed` lint quiet.
- Public data comes from `public_*` views granted to both `anon` and `authenticated`. `bot/scripts/check_public_grants.py` passes for every fantasy view. It still reports `public_sets` missing for anon on the local database, which predates this work.
- Policies and the trigger are created only when `auth.uid()` exists, like P0P1's `has_auth` checks, so CI and plain Postgres get the tables and views without them.
- Who can play: anyone who logs in to the site with Discord, the same as P0P1 ballots, which check no server membership.
- The Podium resolves Discord ids through `auth.identities` where `provider = 'discord'`, like `bot/services/p0p1_ceremony.py`, and returns None off production where that table is missing.

## Registry

`fantasy_events.json` at the repo root, next to `p0p1_contests.json`. `invitationListUrl` points the field drift check at the official invitation page. `bot/services/fantasy_event.py` reads it the way `p0p1_contest.py` reads the P0P1 file, and the site can import the same JSON. Each entry holds the name, `scheduleName` matching a key in `PREMIER_SCHEDULES`, `meleeTournamentId`, `picksLockAt`, `swissRounds`, `cutRound`, `draftRounds`, `bracketLockAt`, `fieldSeed` and `live`. Only a `live` event gets #watch-party posts and the site's nav tab. `WC32` is the real event. `PTMSH` is a `replayOnly` entry for Pro Tour Marvel Super Heroes, used for the dry run and skipped by the live tick.

Entries without `meleeTournamentId`, such as a Pro Tour Melee hasn't listed yet, are skipped by the bot. `slug`, `shortName`, `setCode` and `crest` feed the Discord posts.

The sync copies each registry entry into the `fantasy_events` table, because the SQL views need the lock times and round structure. The JSON stays the source of truth: edit it and the next sync updates the row.

Draft rounds come from the registry. Melee's per-match `Format` label is inconsistent: Pro Tour Marvel Super Heroes reports its second draft as "Draft2". Its Top 8 label "Draft 3" was correct, since that Top 8 was a booster draft.

## Tables

- `fantasy_events`: one row per registry entry, plus `synced_at`.
- `fantasy_players`: the field per event. `slug` is unique per event and built from the accent-folded name. `melee_username` links a player to Melee and is unique per event. Also names, a nullable curated `short_name`, country, country code, invitation `sources` and `photo_url`. Seeded from the registry's `fieldSeed`, `bot/data/fantasy/wc32_field.json` for Worlds 32. A Melee player missing from the seed is added on first sight and logged. A player who leaves the seed is deleted on the next reseed unless a member picked them or they have results.
- `fantasy_results`: one row per player per round, keyed `(event_code, round_number, player_id)`. Holds the opponent, `stage` swiss, quarterfinal, semifinal or final, `format` draft or constructed, `result` W, L or D, game wins, losses and draws, `is_bye`, `bracket_position` QF1 to QF4, SF1, SF2 or F, and the Melee match guid. Top 8 rounds number on from the Swiss rounds, so Worlds runs 1 to 14 for Swiss and 15, 16 and 17 for the Top 8. A bye counts as a win, including the byes Melee gives players already locked into the Top 8.
- `fantasy_picks`: keyed `(user_id, event_code, slot, from_round)`. Day 1 picks have `from_round = 1`, and a Day 2 replacement is a second row for the same slot at `cut_round + 1`. Own-row RLS.
- `fantasy_bracket_picks`: keyed `(user_id, event_code, position)` with the predicted winner and an optional game score 3-0, 3-1 or 3-2. Own-row RLS.
- `fantasy_members`: private display names, synced by trigger.

Picks and bracket picks reference players through a composite foreign key on `(event_code, player_id)`, so a pick can never point at another event's player.

## Scoring views

Internal views are `security_invoker`, have every grant revoked from `anon` and `authenticated`, and are read only through the public views:

- `fantasy_effective_picks`: the picks that count, each with the round range it covers. A replacement counts only if it sits at `cut_round + 1` and the player it replaces has no result after the cut. Otherwise it is ignored and the Day 1 pick keeps scoring, so the replacement rule holds even against a direct API write.
- `fantasy_slot_round_points`: one row per counted pick per round with points, plus a zero row for a pick with no results yet. Swiss rounds score 3 per win and 1 per draw times the slot multiplier: Captain 2, Drafter 3 in Draft rounds and 0 in Constructed, Constructed 0 in Draft and 2 in Constructed, Player 1. The site scores the same rules in the browser, because spoiler-free mode stops at the reveal marker; the SQL scoring feeds the rank and the Podium. Top 8 rounds score the flat bonus with no multiplier: a quarterfinal is 4 for reaching the Top 8 plus 4 for a win, a semifinal win is 4 and a final win is 8.
- `fantasy_bracket_points`: each bracket pick against the real result at that position. A correct winner scores 2 in a quarterfinal, 4 in a semifinal and 8 in the final, plus 1 for the exact game score.
- `fantasy_member_scores`: per member, total points, Bracket points, whether they called the champion, and when they last saved their Day 1 lineup.

Public views:

- `public_fantasy_players`: the field, always readable.
- `public_fantasy_results`: every player's round results, always readable.
- `public_fantasy_standings`: per member per event: `member_key`, `is_me`, name, avatar, points, `bracket_points`, `champion_called` and `rank`. Rank orders by points with the Bracket included, then the champion call, then the earliest last change to the Day 1 lineup. Empty until `picks_lock_at`.
- `public_fantasy_lineups`: every member's counted pick rows: slot, `from_round` and player. Empty until `picks_lock_at`.
- `public_fantasy_bracket_picks`: every member's Bracket picks. Empty until `bracket_lock_at`.

Before the lock a member reads only their own picks, straight from `fantasy_picks` and `fantasy_bracket_picks` under RLS.

`member_key` is the first 16 hex characters of the SHA-256 of the user id. It joins rows across the public views without exposing the user id, and the browser can compute its own with SubtleCrypto. `is_me` compares the row against the `sub` claim of the request's JWT, so the site can find the signed-in member's row with no extra query. It is false for anonymous visitors and in local dev.

## Melee

Decks: each Melee match row carries every competitor's decklist id and name. The sync stores the Constructed one on `fantasy_players.deck_name` and `decklist_id` from Swiss Constructed rounds, and `public_fantasy_players` exposes both, so the site links `https://melee.gg/Decklist/View/<decklist_id>`. Draft rounds and a drafted Top 8 carry draft decklists and are skipped. The PT MSH offline resync filled all 362 players with ids matching Melee's standings.

`bot/services/melee.py` reads public pages with no login. `/Tournament/View/<id>` carries the pairing round list with round ids, names and an `is-started` flag. `POST /Match/GetRoundMatches/<round_id>` with DataTables form fields returns every match in a round: competitors with Melee username, display name and game wins, `HasResult`, `GameDraws`, table number and the match guid. Requests are spaced 1.5 seconds apart. With a cache directory set, raw responses are written there, and `offline` replays them.

Melee publishes no player list before the event. WC32's page has no pairings and no registrations, so the field comes from the invitee seed until Round 1 pairings appear. Players are matched by Melee username first, then by accent-folded full name, and the username is stored on first match.

The Top 8 bracket follows Melee table numbers. Quarterfinal tables 1 to 4 are QF1 to QF4. SF1 is fed by QF1 and QF3, SF2 by QF2 and QF4. This is confirmed against Pro Tour Marvel Super Heroes and lives in `BRACKET_FEEDS`, which the bracket UI must share. Quarterfinal pairings there followed Top 8 draft seats, 5 against 6, 1 against 2, 3 against 8 and 4 against 7, so the bracket must read its pairings from Melee and never assume 1 against 8.

## Sync

`bot/services/fantasy_sync.py` writes the registry row, upserts the field seed and resolves Melee players. It then fetches every started round from the latest stored round onward and upserts each finished match's two result rows. Older rounds are skipped unless `--full` is passed. Every write is an upsert, so a rerun or an interrupted tick is harmless.

```
DATABASE_URL=... python -m bot.scripts.fantasy_sync WC32
DATABASE_URL=... python -m bot.scripts.fantasy_sync PTMSH --offline --through-round 8
DATABASE_URL=... python -m bot.scripts.fantasy_sync WC32 --full
```

The cache lives in `/tmp/fantasy/melee/<tournament id>/`.

## Spoiler-free reveal and pick locks

Melee posts results hours before the coverage shows them, since coverage plays recorded matches between rounds. Results are kept complete in the database, and a reveal marker says how far the coverage has gone.

- `fantasy_events.revealed_through_round` is the marker. `public_fantasy_event_state` exposes it with `completed_through_round`, the lock times and `synced_at`, readable by `anon` and `authenticated`.
- `fantasy_rounds` records when the sync first sees each round with every match reported. The ten-minute tick calls `advance_auto_reveal` in `bot/services/fantasy_reveal.py`, which reveals each completed round 90 minutes after Melee completes it and only moves forward. It never auto-releases the first round of a day, Round 1 and `cut_round + 1`, or any Top 8 stage: a moderator releases those with `/round`, and auto-reveal carries on from there. The rule comes from Mike Provencher of MTG Scribe, who keeps spoiler-free standings by hand: Melee usually leads coverage by 30 to 60 minutes, the gap is widest at the start of each day because coverage starts after the draft, and Top 8 timing depends on game length.
- `/round <n>` sets the marker by hand: a round number, or quarterfinals, semifinals or final, also accepting quarters, semis and finals. Moderators only: the owner, administrators, the admin role or Moderator. On success it replies publicly with the event name in bold; errors stay private. It targets the event whose picks have locked, or the soonest upcoming one before any lock. Moving the marker fires the Day 1 and results posts. It needs `!sync` after deploy.
- Views do not filter on the marker. Spoiler-free is a per-viewer toggle on the site, so the site filters: with it on, records, round grids, standings, member points and the bracket stop at the marker.
- The sync records `day_two_started_at` and `top8_started_at` the first time Melee shows Round cut+1 or the Quarterfinals as started.
- Server-side locks: `fantasy_pick_window_open` and `fantasy_bracket_window_open` decide whether a pick can change, and a trigger on both pick tables rejects writes outside the window for the `authenticated` role. Day 1 picks close at `picks_lock_at`. Replacements open at `picks_lock_at` and close when Round cut+1 starts on Melee. Bracket picks open when `revealed_through_round` reaches the last Swiss round and close at `bracket_lock_at` or when the Quarterfinals start, whichever comes first. Writes as `postgres`, like the local proxy and tests, skip the check. A rejected save makes the site reload the saved lineup.
- Posts that carry results fire on reveal; the moderator alert in #bot-spam fires on Melee completion. The post table is in `spec/fantasy-worlds.md`.
- The site polls `public_fantasy_event_state` every 60 seconds and on window focus, and refetches the heavier views only when the marker or `completed_through_round` changes.

## Bracket positions from Melee

Melee table numbers are not a bracket: Worlds 31, PT ECL, PT EOE, PT FIN and PT DFT paired Quarterfinal tables 1 and 2 into a Semifinal, and PT SOS paired 1 with 4. When the Quarterfinals sync, `_seeded_quarterfinals` reads Melee's standings after the last Swiss round through `POST /Standing/GetRoundStandings` and names each Quarterfinal by its lower seed: 8 QF1, 7 QF2, 5 QF3, 6 QF4, matching `QUARTERFINAL_BY_LOWER_SEED` and the site's bracket. The lower seed holds even where the top four were paired unusually: PT SOS and PT DFT played 3v5 and 4v6, and their Semifinals still joined the 8-seed's and 5-seed's sides. Checked against every seeded Top 8 since Worlds 30. Melee's final standings carry Swiss-only tiebreakers, so fetching them after Top 8 results exist gives the same seeds. A Top 8 that fits no lower seed, like PT MSH's drafted one, keeps table numbers, and the tick alerts the owner in #bot-spam on the sync that writes the first Quarterfinal result. Semifinals follow `BRACKET_FEEDS` from the stored Quarterfinal positions.

## Results refresh

Data sizes: Worlds has 134 players and 17 rounds, so about 2,300 result rows. Members will number in the tens to low hundreds, at 4 to 8 pick rows each. With 500 fake members on the 16-round Pro Tour replay, `public_fantasy_standings` ran in 31 ms and `public_fantasy_lineups` in 65 ms on the local database. That needed the `(event_code, player_id)` index on results and lineups reading from one evaluation of the pick view: before those two fixes the lineups view took minutes.

Scoring stays plain SQL views over the scraped results: one writer, no deploy for new results, and the site reads one view per screen. A precomputed standings table, a static JSON snapshot scored in the browser and a Supabase Edge Function were rejected as second copies of the scoring or new infrastructure.

`bot/tasks/fantasy_sync_tick.py` runs every 10 minutes from the bot's scheduler, then runs the Pro Play posts pass from `bot/tasks/pro_play_posts.py`, so one job drives both. During an event's live window it syncs results. The window runs from 30 minutes before the first `PREMIER_SCHEDULES` day starts until 2 hours after the last day ends, and the dead hours between days cost two cheap requests per tick. In the 14 days before the window it reseeds the field once an hour, so invitation and photo updates in the seed reach the database without a deploy. `init_fantasy_sync` is wired into `bot/main.py`. A bot deploy mid-event skips at most one tick. For corrections run `fantasy_sync <code> --full` from a Railway console. The 4-hour refresh-cron service is too slow for live rounds and is left alone.

## Tests

`bot/tests/test_fantasy_scoring.py` runs the migration's own view SQL on the model-built test schema, since that schema has no views. It covers slot multipliers with the Top 8 bonus for each slot, a replacement counting only when the original missed Day 2, Bracket points with the champion call, a winner-only Bracket pick, the tiebreak order, the pick windows and the Bracket window. `test_fantasy_sync.py` covers round completion, byes, Quarterfinal positions from the lower seed and the one-time alert for a drafted Top 8. `test_fantasy_reveal.py` covers the reveal timing and the post milestones. `test_fantasy_scripts.py` runs `fantasy_sync` and `fantasy_dry_run` end to end against the test database with Melee faked. The full suite passed: 2,459 tests.

## Podium role

`bot/services/fantasy_podium.py` returns the top three of `public_fantasy_standings` with Discord ids. When the reveal marker passes the Final, `bot/tasks/pro_play_posts.py` moves the **Fantasy Champion** role, gold, to them on the production guild through the shared `rotate_role` in `bot/services/pod_roles.py`, then posts and pins the closing post with the role mention above the top 3. The role is a managed role in `bot/services/ping_roles.py`, so the reconcile creates it. It rotates like P0P1's Top P0P1 Challenger.
