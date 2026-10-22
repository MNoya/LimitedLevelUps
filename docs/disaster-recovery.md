# Disaster recovery: rotating every secret

Runbook for when a platform that holds our secrets is breached and every credential has to be replaced. Written after the Railway environment-variable incident of October 2026. It lists every secret, every place a copy of it lives, where to rotate it, and the order to bring services back.

Ask Claude "I want to go through disaster recovery to rotate our secret keys" and the `disaster-recovery` skill walks through this file one step at a time. Each step below splits into what you do in a dashboard and what the agent checks and pushes.

## Inventory

| Secret | Used for | Every copy | Rotate at | When it's stale |
|---|---|---|---|---|
| Supabase database password | Every bot read and write, the refresh cron, migrations on boot | Railway `DATABASE_URL` on DischordLeaderboard and refresh-cron, local `.env.supabase` `SUPABASE_DB_URL` | https://supabase.com/dashboard/project/yrecdosksgigpceholjl/settings/database | Bot and cron lose the database at their next reconnect |
| Discord bot token, DisChord Bot#1519 | The bot itself, botlog posts from the cron, deck screenshot link refresh on the site | Railway `DISCORD_BOT_TOKEN` on DischordLeaderboard and refresh-cron, Supabase edge function secret `DISCORD_BOT_TOKEN` | https://discord.com/developers/applications/1466076574372724819/bot | Bot offline immediately. Deck screenshots older than a day stop loading on the site |
| Cloudflare KV token, account token `llu-bot-kv` | The cron writes live card stats to the `llu-card-stats` KV namespace | Railway `CLOUDFLARE_KV_TOKEN` on refresh-cron | https://dash.cloudflare.com/a704af6840efc2087f25a52c191b4e66/api-tokens | Live card stats on the site go stale. The failure is logged and the refresh keeps running |
| YouTube Data API key | Bot media sync of new episodes, the site's `/api/youtube` video feed | Railway `YOUTUBE_API_KEY` on DischordLeaderboard, Cloudflare Pages `YOUTUBE_API_KEY` secret on project `limitedlevelups` | https://console.cloud.google.com/apis/credentials | New episodes stop syncing. The site's video sections go empty |

### Secrets Railway never held

These sit on other platforms. Rotate them only when their own platform is breached.

| Secret | Used for | Where it lives | Rotate at |
|---|---|---|---|
| Supabase `SERVICE_ROLE_JWT` | The `refresh-deck-url` edge function writes refreshed links to `pod_draft_participants` | Supabase edge function secret | Rotating it means rotating the project's legacy JWT secret, which signs out every user and changes the site's keys. Last resort only |
| Discord OAuth client secret | Website sign-in with Discord through Supabase Auth | Supabase Auth → Providers → Discord | Discord app → OAuth2 → Reset Secret, then paste it into Supabase Auth |
| Cloudflare Pages deploy token | GitHub Actions deploys the site on push to master | GitHub secret `CLOUDFLARE_API_TOKEN` on the repo, local `.env.cloudflare` | Cloudflare token page of the account that owns the token, then https://github.com/MNoya/LimitedLevelUps/settings/secrets/actions |
| Cloudflare user and DNS tokens | Local scripts and DNS work, Pages project API calls | Local `.env.cloudflare` only | https://dash.cloudflare.com/profile/api-tokens and the account token page above |
| Supabase personal access token | Supabase CLI and management API | Local `.env.supabase` | https://supabase.com/dashboard/account/tokens |

Not secrets: `SUPABASE_URL`, `SUPABASE_ANON_KEY` and the site's publishable key in `frontend/src/data/public-supabase-config.ts` are public by design. Channel, guild and account IDs are identifiers.

## Recovery order

Most important first. Each tier is independent, so a later tier can wait a day without hurting an earlier one.

0. **Preflight.** Make sure a deploy can follow the revocation.
1. **Database password and Discord bot token on Railway.** Full database write access is the most damaging leak, and the bot needs both. One deploy covers the pair.
2. **Discord bot token in the Supabase edge function.** Restores deck screenshots on the site. Easy to forget because it lives outside Railway.
3. **Cloudflare KV token.** Live card stats only.
4. **YouTube API key on Railway and Cloudflare Pages.** Media sync and the site's video feed are the least important.
5. **Cleanup.** Delete variables nothing reads anymore, revoke tokens for retired services and delete `.env.prod`.

## Shared setup

New values go in `.env.prod` at the repo root, one `KEY=value` per line. It is gitignored through `.env.*`. The agent reads it to test and push each value, so no secret goes through chat. Start it with these empty keys:

```
DATABASE_URL=
DISCORD_BOT_TOKEN=
YOUTUBE_API_KEY=
CLOUDFLARE_KV_TOKEN=
```

The agent's checks below use these bash helpers, run from the repo root:

```bash
val() { grep -E "^$1=" .env.prod | cut -d= -f2-; }
railway_val() { railway variable list --service "$1" --json | jq -r ".$2"; }
push() { val "$2" | tr -d '\n' | railway variable set "$2" --stdin --service "$1" --skip-deploys > /dev/null && echo "✅ $2 on $1"; }
```

`push` sends the value through stdin so it never lands in shell history or process arguments, and `--skip-deploys` saves it without restarting the service. Never print a secret value. Print lengths, digests or HTTP codes.

Service names: `DischordLeaderboard` is the bot, `refresh-cron` is the 4-hourly refresh. Cloudflare account ID `a704af6840efc2087f25a52c191b4e66` is the chordocoach account, which owns the Pages project and the KV namespace.

## Step 0. Preflight

**Agent:**
1. Run `railway status`. If it says Unauthorized, the user runs `railway login` and you retry.
2. Fetch https://status.railway.com and report any incident touching deploys. If deploys are paused or queued, stop and tell the user. Step 1 takes the bot offline, and it stays offline until a deploy goes through or the local fallback runs.
3. Check that no pod draft is running. Read `DATABASE_URL` from Railway and query `select name, socket_status from pod_draft_events where socket_status in ('drafting', 'in_progress')`. Any row means wait.
4. Create `.env.prod` with the empty keys above if it doesn't exist.

**Move on when** Railway can deploy and no draft is running, or the user accepts running the bot locally.

## Step 1. Database password and Discord token

**User:**
1. Open https://supabase.com/dashboard/project/yrecdosksgigpceholjl/settings/database and click **Reset database password**. Use letters and digits only: any `%`, `+`, `@`, `/` or `:` has to be URL-encoded inside the connection URL, and a raw `%` silently breaks it. **Confirm the reset dialog.** The old password keeps working until you do.
2. Put the new password into `.env.supabase` `SUPABASE_DB_URL`, replacing the old one.
3. Open https://discord.com/developers/applications/1466076574372724819/bot and click **Reset Token**. The token is shown once and the old one dies at that moment. Paste it into `.env.prod` as `DISCORD_BOT_TOKEN`.

**Agent:**
1. Copy `SUPABASE_DB_URL` from `.env.supabase` into `.env.prod` as `DATABASE_URL`. If the password has characters outside letters and digits, URL-encode the password part in both files.
2. Check the database. The new URL connects and the old one is rejected:

```bash
psql "$(val DATABASE_URL)" -XAtc "select 'ok'"
psql "$(railway_val DischordLeaderboard DATABASE_URL)" -XAtc "select 'ok'"
```

   The second must fail with `password authentication failed`. If it still connects, the reset was not confirmed.
3. Check the Discord token. The new one is DisChordBot and the old one gets 401:

```bash
curl -s -H "Authorization: Bot $(val DISCORD_BOT_TOKEN)" https://discord.com/api/v10/users/@me | jq -r .username
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bot $(railway_val DischordLeaderboard DISCORD_BOT_TOKEN)" https://discord.com/api/v10/users/@me
```

4. Push both values to both services, then deploy each service once:

```bash
for s in DischordLeaderboard refresh-cron; do push $s DATABASE_URL; push $s DISCORD_BOT_TOKEN; done
railway redeploy --service DischordLeaderboard --yes
railway redeploy --service refresh-cron --yes
```

5. Watch `railway deployment list --service DischordLeaderboard` until SUCCESS, then confirm `railway logs --service DischordLeaderboard` shows `logged in as DisChordBot#1519` with no database errors. If the redeploy answers that deploys are paused, start the local fallback at the end of this file.

**Move on when** the bot is logged in and its log is clean.

## Step 2. Supabase edge function token

**User:** open https://supabase.com/dashboard/project/yrecdosksgigpceholjl/functions/secrets, open the **⋯** menu on `DISCORD_BOT_TOKEN`, choose **Edit**, paste the `DISCORD_BOT_TOKEN` value from `.env.prod` and save. No redeploy, because edge functions read secrets per call.

**Agent:**
1. Compare digests. The page shows a SHA256 digest per secret, and it must start with the same characters as:

```bash
val DISCORD_BOT_TOKEN | tr -d '\n' | sha256sum | cut -c1-16
```

2. Call the function for a real deck. Take any participant with a screenshot from `select event_id, display_name from pod_draft_participants where deck_screenshot_url like '%discord%' limit 1`, and the publishable key from `frontend/src/data/public-supabase-config.ts`:

```bash
curl -s -X POST https://yrecdosksgigpceholjl.supabase.co/functions/v1/refresh-deck-url -H "Authorization: Bearer <publishable key>" -H "apikey: <publishable key>" -H "Content-Type: application/json" -d '{"eventId":"<event_id>","displayName":"<display_name>"}' | jq .refreshed
```

**Move on when** it returns `true`.

## Step 3. Cloudflare KV token

**User:** open https://dash.cloudflare.com/a704af6840efc2087f25a52c191b4e66/api-tokens, find `llu-bot-kv`, open its **⋯** menu and choose **Roll**. Paste the new value into `.env.prod` as `CLOUDFLARE_KV_TOKEN`. This is an **account** token on the chordocoach account. My Profile → API Tokens only lists user tokens and won't show it.

**Agent:**
1. Verify with the account endpoint. The user endpoint reports account tokens as invalid:

```bash
acct=a704af6840efc2087f25a52c191b4e66
ns=$(railway_val refresh-cron CLOUDFLARE_KV_NAMESPACE_ID)
set_code=$(.venv/bin/python -c "from bot.sets import active_set_code; print(active_set_code())")
curl -s -H "Authorization: Bearer $(val CLOUDFLARE_KV_TOKEN)" https://api.cloudflare.com/client/v4/accounts/$acct/tokens/verify | jq -r .result.status
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $(val CLOUDFLARE_KV_TOKEN)" https://api.cloudflare.com/client/v4/accounts/$acct/storage/kv/namespaces/$ns/values/$set_code
```

   Expect `active` and `200`. The same read with `railway_val refresh-cron CLOUDFLARE_KV_TOKEN` must give `401`.
2. Push it and redeploy the cron:

```bash
push refresh-cron CLOUDFLARE_KV_TOKEN
railway redeploy --service refresh-cron --yes
```

**Move on when** the new token reads the value and the old one gets 401.

## Step 4. YouTube API key

**User:** open https://console.cloud.google.com/apis/credentials, check the project picker at the top, open the API key and click **Regenerate key**. Paste it into `.env.prod` as `YOUTUBE_API_KEY`.

**Agent:**
1. Check it reads the channel:

```bash
curl -s "https://www.googleapis.com/youtube/v3/channels?part=id&forHandle=limitedlevel-ups&key=$(val YOUTUBE_API_KEY)" | jq -r '.items[0].id // .error.message'
```

2. Push it to the bot and redeploy:

```bash
push DischordLeaderboard YOUTUBE_API_KEY
railway redeploy --service DischordLeaderboard --yes
```

3. Set the Cloudflare Pages copy with `CLOUDFLARE_API_TOKEN_CHORDO` from `.env.cloudflare`, and confirm the response still lists the `CARD_STATS` binding:

```bash
cf=$(grep -E '^CLOUDFLARE_API_TOKEN_CHORDO=' .env.cloudflare | cut -d= -f2-)
pages=https://api.cloudflare.com/client/v4/accounts/a704af6840efc2087f25a52c191b4e66/pages/projects/limitedlevelups
jq -n --arg k "$(val YOUTUBE_API_KEY)" '{deployment_configs:{production:{env_vars:{YOUTUBE_API_KEY:{type:"secret_text",value:$k}}}}}' | curl -s -X PATCH -H "Authorization: Bearer $cf" -H "Content-Type: application/json" --data @- $pages | jq -c '.result.deployment_configs.production | {env: (.env_vars | keys), kv: (.kv_namespaces | keys)}'
```

4. Pages reads the new value only on its next deployment. The site ships as a Direct Upload from GitHub Actions, so the Pages retry API refuses it. Re-run the latest successful site deploy, which redeploys the same commit:

```bash
gh run rerun "$(gh run list --workflow deploy-pages.yml --status success --limit 1 --json databaseId -q '.[0].databaseId')"
```

5. After the run succeeds, `curl -s https://limitedlevelups.com/api/youtube | jq '.videos | length'` must be above zero.

**Move on when** the site returns videos.

## Step 5. Cleanup

**Agent:**
1. List variable names per service with `railway variable list --service <name> --json | jq -r 'keys[]'` and compare them against what the code reads in `bot/config.py`. Report any secret-looking variable no code reads and delete it once the user agrees. `railway variable delete` has no skip-deploys flag, so each delete redeploys the service.
2. Remind the user to revoke keys for retired services at the provider and to delete expired tokens on each platform.
3. Delete `.env.prod` once everything is verified. Its values live on Railway and in the local env files now.

## Fallback: run the production bot locally

Use it when Railway can't deploy. Runs the bot from this machine with Railway's variables.

1. Pick the commit. The bot applies pending migrations against prod on startup, so run a commit you are willing to migrate prod to. `railway deployment list --service DischordLeaderboard --json | jq -r '.[0].meta.commitHash'` gives the last commit Railway ran.
2. Make a clean worktree. It has no `.env`, so local dev settings stay out:

```bash
git worktree add --detach /tmp/llu-prod-bot <commit>
```

3. Start it in the background with Railway's variables, clearing the git variables so it skips the "Bot redeployed" post:

```bash
railway run --service DischordLeaderboard -- bash -c 'unset RAILWAY_GIT_COMMIT_SHA RAILWAY_GIT_COMMIT_MESSAGE; cd /tmp/llu-prod-bot && exec /home/mnoya/Projects/Personal/DischordLeaderboard/.venv/bin/python -u -m bot.main' > /tmp/llu-prod-bot.log 2>&1
```

4. Confirm `/tmp/llu-prod-bot.log` shows `logged in as DisChordBot#1519`.
5. Before Railway deploys again, stop the local bot. Two instances on one token answer every command twice, and a push to master counts as a deploy. Then run `git worktree remove /tmp/llu-prod-bot`.

## Lessons from October 2026

- Check deploy health first. Revoking a token commits you to a deploy, and Railway's deploys were paused that day.
- A Supabase password reset needs its confirmation clicked, and the old password keeps working until then. Test old and new together.
- Special characters in the database password broke the URL. Letters and digits only.
- The Discord token had a third copy in the Supabase edge function, and the YouTube key had a second one in Cloudflare Pages. Both broke the site quietly until found.
- Cloudflare account tokens and user tokens live on different pages and verify at different endpoints.
- The site's YouTube function used to cache an empty feed for an hour after a key failure. It no longer caches empty results.
