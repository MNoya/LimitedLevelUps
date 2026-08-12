# Pod Draft — Test Bot Setup

How to run a second bot account locally against the **LLU Test** guild for
pod-draft development, without touching the live Railway bot.

## One-time Discord setup

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application** — name it e.g. `DisChord Test`.
2. Under **Bot**:
   - Click **Reset Token** → copy the token, store as `DISCORD_BOT_TOKEN` in `.env`.
   - Toggle on **Message Content Intent** and **Server Members Intent**.
3. Under **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Manage Threads`, `Manage Messages`, `Use Slash Commands`
4. Open the generated URL → invite the new app to **LLU Test**.
5. In LLU Test, create a text channel named `#pod-draft-coordination`. Copy its ID (right-click → Copy Channel ID with developer mode on).
6. Invite the live `sesh.fyi` bot to LLU Test as well (same invite link sesh publishes), so the listener has a real producer to match against. Copy sesh's user ID once it's joined.

## `.env` (local, gitignored)

The repo root `.env` should point at the **test** bot and **local** Postgres. The
prod token lives only in Railway's env settings.

```
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord

# Test bot (NOT the production token)
DISCORD_BOT_TOKEN=<test-app token from step 2>
DISCORD_GUILD_ID=<LLU Test guild ID>

# Pod draft
POD_DRAFT_CHANNEL_ID=<#pod-draft-coordination ID in LLU Test>
POD_DRAFT_SESSION_PREFIX=LLUT       # different from prod's LLU so Draftmancer sessions don't collide
POD_DRAFT_MAX_PLAYERS=8
POD_DRAFT_PICK_TIMER=60
POD_DRAFT_FALLBACK_TZ=America/New_York  # IANA tz used to derive event_date from the unix timestamp
SESH_BOT_ID=<sesh.fyi user ID>
DRAFTMANCER_WS_URL=wss://draftmancer.com
```

## Running

```
docker start dischord-pg                     # local Postgres, port 5433
.venv/bin/alembic upgrade head               # picks up the pod_draft_* tables
.venv/bin/python -u -m bot.main              # runs the test bot
```

In the test bot's DM, run `!sync` once after any slash-command name/description change. The test bot is owner-scoped to your own Discord user ID (set during app creation), so `!sync` and `!refresh` work the same as on prod.

## Keeping production untouched

- The branch `pod-draft-phase-1` is **not** merged to `master` until the feature is verified end-to-end in LLU Test.
- Railway deploys from `master`. As long as the branch isn't merged, Railway has no awareness of pod-draft code.
- Once we're ready to enable on prod, we'll decide whether to gate behind a `POD_DRAFT_ENABLED` flag or rely on `POD_DRAFT_CHANNEL_ID` being unset on Railway.

## What you'll exercise during testing

- Have sesh.fyi post a real event in LLU Test → listener should catch it, create the DB row, join the thread, schedule the reminder.
- At T-5, the bot pings attendees and posts the Draftmancer link.
- A few test accounts join the Draftmancer session; one runs `/pod-ready`; the bot drives the ready check + start.
- Players self-report match results in Draftmancer; the bot posts pairings and result lines as the bracket advances; finalizes the champion at the end.
