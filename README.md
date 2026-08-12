# DischordLeaderboard

A community leaderboard for an MTG Arena Discord server (**LLU** — Limited Level-Ups). Players link their [17lands](https://17lands.com) profile through a Discord bot; their drafts are pulled, scored with a custom formula, and ranked on a public site.

- **Site**: https://limitedlevelups.com/ (`dischord.pages.dev` redirects here; branch previews live at `<branch>.dischord.pages.dev`)
- **Bot**: invite-only to the LLU server; commands work in-server and in DM
- **Stack**: Python `discord.py` bot · React + Vite frontend · Supabase Postgres · Railway + Cloudflare Pages

## Repo layout

```
bot/          Discord bot, 17lands integration, scoring, migrations
frontend/     React + Vite SPA, deployed to Cloudflare Pages
functions/    Cloudflare Pages Functions (SPA fallback)
docs/         Player-facing guides
spec/archive/ Point-in-time design notes, not current behavior
alembic/      DB migrations
legacy/       Original spreadsheet-era code, kept for reference
```

## Quickstart (local dev)

```bash
# 1. Postgres
docker run -d --name dischord-pg -p 5433:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=devpw -e POSTGRES_DB=dischord \
  postgres:16-alpine

# 2. Python
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env  # then fill in DISCORD_BOT_TOKEN, DISCORD_GUILD_ID

# 3. Schema + seed
.venv/bin/alembic upgrade head
.venv/bin/python -m bot.scripts.seed_sets

# 4. Run
.venv/bin/python -u -m bot.main
```

Frontend:
```bash
cd frontend && npm install && npm run dev   # http://localhost:5173/
```

Without `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY`, the frontend runs against bundled fixtures.

## Tests

```bash
.venv/bin/pytest bot/tests/
```

Tests use [`testcontainers[postgres]`](https://testcontainers.com/modules/postgres/) — Docker must be running.

## Further reading

- `CLAUDE.md` — architecture, conventions, operational notes
- `docs/guide/pod-coordination.md` — how pod drafts work, for players
- `spec/archive/` — how features were designed at the time they were built; the code is the truth now
