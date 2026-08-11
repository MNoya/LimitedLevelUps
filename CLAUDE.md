# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Discord bot + public website for an MTGA community leaderboard called **LLU**. Players link their 17lands profile through Discord; the bot pulls draft data, computes a custom score, and ranks them within the current Magic set. Multi-server-capable (single shared leaderboard across all guilds the bot is invited to). Fully automated — no manual score submission.

- **Bot** (`bot/`): Python, `discord.py`, SQLAlchemy 2.0 + Alembic, deployed on Railway from `master`
- **Frontend** (`frontend/`): React 18 + Vite + TanStack Query + Tailwind, deployed on Cloudflare Pages at `https://limitedlevelups.com/` (production fed by `master`; `dischord.pages.dev` redirects here, branch previews at `<branch>.dischord.pages.dev`)
- **Database**: Postgres — local Docker for dev, Supabase (project `yrecdosksgigpceholjl`) for prod

Spec documents live under `spec/`. Each one opens with what it covers and when to read it — check there before re-inferring a subsystem's design.

## Common commands

All Python commands assume the venv: `.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/alembic`.

### Bot

```bash
# Run the bot (reads .env)
.venv/bin/python -u -m bot.main

# Tests (spins up a Postgres testcontainer unless TEST_DATABASE_URL is set)
.venv/bin/pytest bot/tests/
.venv/bin/pytest bot/tests/test_scoring.py::test_specific_thing  # single test

# Migrations (DATABASE_URL must be set)
.venv/bin/alembic upgrade head
.venv/bin/alembic check                # verify models match migrations
.venv/bin/alembic revision --autogenerate -m "msg"

# Seed + refresh against local DB
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord .venv/bin/python -m bot.scripts.seed_sets
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord .venv/bin/python -m bot.scripts.seed_local_players
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord .venv/bin/python -m bot.scripts.refresh_stats --cache  # uses cache/17lands/
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord .venv/bin/python -m bot.scripts.refresh_stats          # live fetch
```

### Frontend

```bash
cd frontend
npm run dev       # http://localhost:5173/
npm run build     # tsc -b && vite build → dist/
npm run preview
```

### Local Postgres (one-time setup, then `docker start dischord-pg`)

```bash
docker run -d --name dischord-pg -p 5433:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=devpw -e POSTGRES_DB=dischord \
  postgres:17-alpine
```

To wipe and re-seed:
```bash
docker exec dischord-pg psql -U postgres -d dischord -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
# then alembic upgrade head + seed_sets + seed_local_players + refresh_stats --cache
```

### Owner-only prefix commands (DM the bot)

- `!sync` — push slash-command schema changes to Discord. Run after editing any command's name/description/options. Body-only changes don't need it.
- `!guide` — sync the Server Guide channels (channel-overview, quick-links, rules, limitedlevelups-com) from `bot/server_guide/*.md`: a channel holding one message per page is edited in place so the sync leaves no unread mark, a page added or removed falls back to deleting and reposting the whole channel in page order, with per-channel results reported. Open to the bot owner, administrators and the Moderator role, not owner-only. Pages post through a webhook wearing the server owner's identity (needs Manage Webhooks; falls back to posting as the bot). Guide channels need channel-level overwrites for the bot's role (View Channel, Send Messages, Read Message History, Embed Links) — native Server Guide resource channels carry an @everyone deny that beats server-level role grants. The format-schedule tick archives stale set channels but syncs no guide page, so channel-overview's `{latest-set-channel}` mention and the set-tracking To-Do only follow a new set channel once someone runs this.
- `!test <word>` — the manual preview surfaces (`bot/commands/test*.py`). On the production guild a subcommand runs only when `PRODUCTION_SAFE_TESTS` in `bot/commands/test_group.py` names it: the render-only previews stay available there so copy can be eyeballed live, and anything that creates real pods, signals, or roles is refused. The allowlist is opt-in, so a new subcommand is blocked on prod until it is listed. `testlobby.py` is the exception to the layout: it registers no subcommand of its own, its states are the group's fallback, so each is invoked as `!test <state>` (`!test champ`), never `!test lobby <state>`, where `lobby` is itself a state that seeds a live pod. The testlobby fallback states that seed live pods (`_PRODUCTION_BLOCKED_STATES`) are refused the same way.
- `!refresh` — re-pull 17lands for active players against the active set's window and recompute scores. Same code path as the periodic tick. Posted leaderboards are frozen snapshots, so this edits no messages; fresh standings appear on the next `/leaderboard` or on the website. For full-history reconciliation (formula change, retroactive set add, drift recovery) run `python -m bot.scripts.refresh_stats` from a console instead.

## Architecture

### Data flow

```
17lands API → bot/services/seventeenlands.py → bot/services/refresh.py
                                                       ↓
                                       draft_events (source of truth, additive)
                                                       ↓
                            player_stats (derived aggregates, rebuilt per refresh)
                                                       ↓
                          Postgres (public_* views — raw aggregates only)
                                                       ↓
                              Frontend (supabase-js, anon key, browser-direct)
```

`draft_events` is keyed on `(player_id, seventeenlands_event_id)` and only grows — never wiped. `player_stats` is recomputed from `draft_events` after every refresh, so a partial-window fetch is safe (writes only the events it returned; aggregates rebuild from the full history already on disk).

There are **no precomputed score tables** — score and rank are computed live from the raw aggregates on every read. The bot reads `player_stats` directly and scores in Python (`bot/scoring.py`); the frontend reads the `public_*` views and scores in JS (`frontend/src/data/scoring.ts`). Both pull bucket labels and point weights from the shared `scoring_buckets.json`, but the formula itself is implemented twice and must stay in sync.

The bot is the only writer. The frontend reads through curated `public_*` Postgres views (no service-role key in the client). View row shapes are mirrored as camelCase TS types in `frontend/src/types/leaderboard.ts`; `frontend/src/data/adapter.ts` converts snake_case → camelCase.

### Set rotation — `bot/sets.py` is the single source of truth

```python
ALL_SETS = (..., SetSeed("SOS", "Secrets of Strixhaven", date(2026, 4, 21), date(2026, 6, 22)),
                 SetSeed("MSH", "Marvel Super Heroes", date(2026, 6, 23), date(2026, 8, 10)))
```

The active set is **derived from today's date** by `active_set_code()` — there is **no `ACTIVE_SET_CODE` constant**, no `is_current` flag on `sets`, and no env var. Each `SetSeed` carries its Arena `start_date`/`end_date`; the active set turns over at noon ET on its `start_date`. Rotation = add the new set to `ALL_SETS` with its dates + push to master; the flip happens on its own when the date arrives.

**The active set is not the board.** `active_set_code()` is the set *Arena* is drafting, which pods, the refresh window, the championship, the Set Awards and the format schedule all follow. The *leaderboard board* runs ahead of it: Early Access and the paper prerelease put results on record days before the Arena drop, so the next set claims the board the moment its first result exists — a `player_stats` row or a `/trophy` self-report. That needs the database, so it lives in `resolve_board_set()` (`bot/services/active_set.py`) and drives `/leaderboard`'s default set and `/stats`. `public_sets.is_active` computes the same answer in SQL for the site, which keys its default set, player profiles and tier list off it. **Keep the two implementations in lockstep.** The `early` column stays "not yet released", so a prerelease board is both `is_active` and `early` and the site's set chip labels it EARLY ACCESS. Use the `/add-set <CODE>` Claude Code skill (`.claude/skills/add-set/`) to automate: it web-looks-up the official name + Arena release date, edits `bot/sets.py`, runs `seed_sets` + `refresh_stats`, and commits locally.

Discord set channels rotate separately and are **not** driven by `!guide`: two crons in `bot/tasks/format_schedule_post.py` split it: `fire_rotation` posts the outgoing set's send-off standings into its channel at the noon-ET release instant, and `fire_archive` moves that channel to "Format Archive" and notifies the `-admin` channel `ARCHIVE_DELAY` (one hour) later, so the boards get an hour in front of the players already reading there. The 3×/day announce tick re-runs the archive pass as an idempotent fallback, not the send-off. The eve of a rotation, `bot/tasks/set_awards_post.py` runs the Set Awards ceremony (8 AM PT, with a T-15 warning) in that same channel and pins it. Creating the incoming set's channel is manual by design — the bot never creates channels, so a mod adds it during preview season for old/new coexistence.

### Cube boards — `cube_variants.json`

Arena swaps its cube every few sets and 17lands files each under its own expansion, so the one `CUBE` set row holds every cube and the boards split by variant. `cube_variants.json` at the repo root is the registry both sides read (`bot/sets.py` and `frontend/src/data/cubeVariants.ts`), one entry per cube: `slug`, `name`, the 17lands `expansion`, a `keyrune:`/`mana:` `glyph` spec, and `seasoned`.

- Cube expansions are **kept verbatim** on `draft_events` (`Cube`, `Cube - Powered`, `Cube - Planar`) — `normalize_expansion` rewrites only `expansion_alias` sets like MAT → MOM. `SetSeed.expansion_matches` routes each cube expansion to `CUBE` without touching the string, which is what keeps the boards separable.
- Board codes are virtual: `CUBE-<SLUG>` for a whole cube, plus `CUBE-<SET>` per-set seasons for the one `seasoned` cube (the powered cube). Bare `CUBE` is not a board — it resolves to whichever cube ran most recently (`latest_cube_board` in the bot, `ongoingCubeBoard` on the site). `CUBE-ALL` is a retired alias that lands on the seasoned cube's board.
- The three `public_cube_season*` views emit both kinds of row, discriminated by `kind`. They derive the slug from the expansion (`Cube - Planar` → `PLANAR`, bare `Cube` → `ARENA`), so a cube Arena introduces later becomes a board with no migration — only a registry entry for its name and glyph.
- `/leaderboard set:` takes any board code and refuses format/color filters on them; the site keeps full filtering.

### Scoring formula — `bot/scoring.py`

Per queue group (Premier / Traditional / Sealed / Quick / LCQ Draft 1 / LCQ Draft 2):
```
raw_group = trophies × group_points × trophy_rate          (trophy_rate = trophies / events)
total     = (Σ raw_group) × T/(T+2) + pod_points            (T = total trophies across groups)
```
- **Confidence `T/(T+2)` is aggregate** — one shrinkage from total trophy count scales the summed raw, not a per-group penalty. `compute_score` / `compute_score_breakdown` both derive from one `_aggregate()`; breakdown contributions are `raw_group × T/(T+2)` so they sum to the total.
- LCQ Draft 2 is a special case: `wins × winrate × points` (exempt from confidence).
- **Pod points** are a separate flat term: 5 per trophy (a 3-0 record OR a pod win by placement), 2 per 2-1; added to the leaderboard total outside `compute_score`. Pods are always public (active-only, never opt-in gated) — pod-only players enter the board on pod points alone.

`DEFAULT_QUEUE_GROUPS` + pod point values are built from `scoring_buckets.json`. The formula is implemented twice — bot (`bot/scoring.py`) and frontend (`frontend/src/data/scoring.ts`) — plus the frontend reads pod aggregates from the `public_pod_scoring` view. Keep both in sync when either changes.

After editing `scoring_buckets.json`:
- Formula/weights/pod points only → nothing to run; scores recompute on the next read. Deploy and the bot picks it up.
- New format strings added → `python -m bot.scripts.rebuild_player_stats` (re-aggregates from existing `draft_events`, no 17L fetch)

The formula may diverge per set in the future — `DEFAULT_QUEUE_GROUPS` is global today but plausibly becomes per-set.

### Data model — key invariants

- **All `DateTime` columns are `DateTime(timezone=True)` (TIMESTAMPTZ).** Naive UTC was misinterpreted as local time by `discord.py`, shifting embed timestamps. Don't reintroduce naive datetimes.
- `players.seventeenlands_token` is nullable so `/pod-link-arena` can create lightweight pod-draft-only players without a 17lands profile.
- `player_stats` is unique per `(player, set, format, expansion)` and **fully derived** from `draft_events` — rebuilt via `DELETE + INSERT … SELECT GROUP BY` per touched (player, set) on every refresh. Alchemy variants like `Y26ECL` get their own row but bucket under `ECL` for scoring. `last_fetched_at` is set on every rebuild (not just on data change); the "Last updated" footer is the max `last_fetched_at` across a player's rows.
- `draft_events` is the additive event log — one row per individual 17lands draft, keyed on `(player_id, seventeenlands_event_id)`. `set_id` is nullable so drafts in not-yet-registered expansions still persist; `/add-set` claims orphans by matching `expansion` to the new set's `code`. 17lands' case-encoded color string (`WBg` = WB main + green splash) is preserved verbatim in `colors`.
- `leaderboard_messages` tracks the bot's posted leaderboard per `(channel, set, filter)` so `/leaderboard` delete-and-reposts instead of duplicating. Posted boards are **frozen snapshots** — never auto-edited after posting (the broadcast/live-edit subsystem was removed); the 🔎 Filter button opens a per-user **ephemeral** board rather than mutating the shared message. Fresh standings come from re-running `/leaderboard` or the website.

### Frontend swap point — `frontend/src/data/api.ts`

Selects backend at module-load time via `useSupabase` from `data/supabase.ts`, driven by **`VITE_DATA_MODE`** (`prod` | `local` | `mock`; default `prod`). `prod`/`local` run `realApi.ts` against the prod public config or the `local_supabase_proxy` on `:3001`; `mock` runs the fixture-backed `mockApi.ts`. An explicit `VITE_SUPABASE_URL` + `VITE_SUPABASE_PUBLISHABLE_KEY` pair overrides prod/local for staging; `mock` always wins. The hook layer (`data/hooks.ts`) imports from `api.ts` and never knows which is live.

Vite `base: "/"` + React Router at the domain root: the app serves from `/`, with the leaderboard as one section (`/leaderboard`) alongside `/tier-list`, `/episodes`, `/community`, `/pods`, `/about`. Static assets in `frontend/public/` (e.g. `set-symbols/<code>.png`) serve from the root too. SPA fallback for CF Pages is **`functions/_middleware.ts`** (a Pages Function), not `_redirects` — `_redirects 200`-rewrites are over-greedy on Cloudflare.

### CI — `.github/workflows/ci.yml`

On push/PR to `master`: spin up Postgres service container → `alembic upgrade head` → `alembic check` (catches model/migration drift) → `pytest bot/tests/`.

## Conventions (do not violate)

- **Branch is `master`**, never `main`.
- **Never `git push`.** Pushing to `master` deploys via CI/CD; the user pushes manually from their git IDE. Commits are fine — the push itself is always the user's call, even right after they approved a commit.
- **Solo repo: commit directly to `master`** for routine changes. Large changesets get a branch — **never a PR**. Merge back by squash, or with a merge commit when the intermediate history is worth keeping; ask which when finishing a branch.
- **Hold commits until the user asks; bundle backend + frontend in one commit.** Leave changes staged in the working tree and don't prompt to commit after each task — the user iterates locally and commits everything together on their own timing.
- **Tests target logic, not framework behavior, and stay few.** Aggregator / scoring / branch logic, fewest cases that cover it. None for a one-key fix, a library's own signature, or values just written — verify those by running the thing. **A test is a specification: never pin product behavior the user did not ask for.** An invented invariant is one nobody agreed to, and every later edit has to litigate whether it matters. State a new invariant in the reply instead and let the user decide whether it becomes a test. The exception is code that can silently do nothing, like a write that never persists — guard that.
- **Shared user-facing message strings live in `bot/commands/messages.py`** (the `MSG_*` constants), parallel to `descriptions.py` for command descriptions. Any string used by more than one command/listener goes there — never duplicate the same copy inline across modules, and don't park shared strings in a service module just because the first caller lived there. A string used by exactly one command may stay as a local `MSG_*` in that command's module; promote it to `messages.py` the moment a second caller needs it. Service modules (`bot/services/`) hold logic, not user copy.
- **User-facing copy is plain declarative microcopy.** Name the real thing and the real action in the plainest accurate word. Literal, compositional verbs only, never phrasal verbs or idioms (many readers are non-native). No em dashes: one joining a statement to its reason becomes a second sentence, one introducing a list becomes a colon, and the clause after it is often filler worth cutting outright. No marketing register. Full guidance and examples in the `plain_declarative_copy` memory.
- **A user-facing message is one short sentence. Don't end a message with a period.** Players skim, and everything past the first sentence costs them. Cut until one sentence carries it. A second sentence is the exception, tells the reader what to do about the first, and never joins it with a comma and "and", "but" or "so".
- **Code comments: default to none.** If a comment runs longer than one line, delete the whole block — don't shrink it, delete it. The code is already self-explanatory if names are right. No periods at end of single-line comments (they're labels, not sentences). No parenthetical asides. Don't paraphrase library / decorator behavior at the declaration site — that belongs in upstream docs, not your file.
- **When a pod behavior change ships, update `spec/pod-coordination.md` in the same commit.** It's the plain-language player guide describing only live behavior, destined to become a Discord Server Guide page, so it must never describe a state the bot isn't in.
- **Commit style**: subjects start with uppercase; no manual line wrapping in description paragraphs; no `Co-Authored-By: Claude` or any AI trailer; plain senior-engineer prose, no AI/ML jargon. Use `- ` bullets when a commit has 2+ distinct changes; prefer one bullet per distinct change over fewer "and"-joined bullets.
- **A button answers before it works.** Never put a chain of DB queries, API calls, or message edits in front of the first response to an interaction. Discord allows 3 seconds to acknowledge, and anything slower than instant reads as a broken button. Send or `defer(thinking=True)` first, then do the rest: read only what the answer itself needs, run independent reads with `asyncio.gather`, put every follow-on write, card re-render, role grant, and thread admission behind `run_detached`. Prefer one session over several — four `SessionLocal()` blocks is four pool checkouts. Skip work the common case doesn't need instead of computing it and throwing it away. `apply_card_rsvp` and `JoinDraftButton.callback` are the worked examples. This applies to every button, select, and modal, not only new ones.
- **Batch edits to a message a crowd can click.** One repaint per click hits Discord's edit limit and leaves the card behind the clicks. Queue the shared repaint through `RenderQueue` (`bot/discord_helpers.py`) so a burst collapses to one, and have it re-read state rather than close over one click's copy.
- **Don't hand back a check you could run yourself.** The user's manual verification is the last gate, not the first. Run the command, query the database, read the row back, then report what it returned. Ask them to look only at what needs a human in Discord or on the site.
- **Every Discord-facing change ends with how to look at it.** Close the reply with a `**Check on Discord:**` line: the exact `!test` invocation on the local test server, plus any clicks needed to reach the state that changed. Last line, nothing after it. A passing test suite is not a look at the output, so don't open with pytest results. Read the state's branch in `bot/commands/test*.py` before naming it, never inferring from its name or docstring: confirm what it creates, where it posts, and that it truly reaches the state the change touches. A wrong invocation costs a round trip.
- **Every website change ends with a running server and a URL.** Don't hand back a command to run. Start the dev server in the background if it isn't already running, with the `VITE_DATA_MODE` that shows the change and any supporting process (the `local_supabase_proxy` for `local` mode), and do whatever data setup the changed state needs (seed the row, apply the migration) before handing over. Close the reply with a `**Check on the site:**` line: the live URL, already on the right path, plus what to click to reach the changed state. The user eyeballs it, so automate every step in front of that. Don't drive a browser to verify it unless told to. A change touching both carries this and the Discord line, the Discord one last.
- **Ask before saving memory** and **ask before architectural decisions** — raise structural questions rather than auto-deciding.

## Operational notes

- Local Postgres: container `dischord-pg` on host `:5433`, db `dischord`, user `postgres`, password `devpw`.
- Tests truncate every table in their database. Set `TEST_DATABASE_URL` to skip the testcontainer (`…:5433/dischord_test`); the db name must contain `test` or the fixtures refuse it.
- Supabase prod pooler URL (with encoded password) lives in gitignored `.env.supabase`.
- 17lands cache: per-token JSONs at `cache/17lands/<token>__YYYY-MM-DD.json`. Use `refresh_stats --cache` for free re-aggregation, omit `--cache` for live fetch.
- Bot logs: `logs/bot.log` (gitignored). Audit log: append-only JSONL at `logs/events.jsonl`.
- Prod log history survives a redeploy: Railway keeps stdout per deployment, but bare `railway logs` reads only the current one, so an older incident looks erased. Find the deployment covering the timestamp with `railway deployment list`, then `railway logs <deployment_id> --since <ISO> --until <ISO>`. One listed as REMOVED still serves logs; `-n` rejects large values. The container filesystem is ephemeral, so `logs/bot.log` and `logs/events.jsonl` read over `railway ssh` only cover the running deployment.
- Production guild: LLU community server, guild ID `775371722065051658`. Bot is `DisChord Bot#1519`, app ID `1466076574372724819`.
- Discord application emojis are generated and uploaded with `python -m bot.scripts.upload_app_emojis <keyrune|mana>:<glyph>[:<name>]`. It targets the app `DISCORD_BOT_TOKEN` belongs to, so the test and prod apps each need one run. Runtime lookup is by name via `bot/emojis.py`.
- Discord fields in `bot/config.py` are optional so non-bot entry points (alembic CLI, seed scripts, tests) can construct `Settings` without them.
