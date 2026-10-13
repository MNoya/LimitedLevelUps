# Pro Play: Fantasy Magic

Members pick a lineup of real competitors at a Pro Tour or World Championship on limitedlevelups.com and score on their match results. It runs with no manual work from setup to the closing ceremony beyond `/round` releases. Modeled on P0P1: Discord login on the site, the bot announces and posts results, and each event is one entry in the `fantasy_events.json` registry. Backend details live in `spec/fantasy-backend.md`.

First event: Magic World Championship 32, November 13–15, 2026, at MagicCon Atlanta, Star Trek Booster Draft and Standard, Melee tournament 471980.

## Status and launch

Built, tested and committed. Not deployed. Every production step is the user's call:

- Migration `f4n7a5y1w0c1` revises `e4rlyacc3ss1`. If another migration lands first, rebase its `down_revision`. The deploy applies it on bot boot. Check prod's `alembic_version` first and confirm `check_public_grants` covers anon and authenticated on every `public_fantasy_*` view.
- The site stays blank on production until the Worlds 32 row and field exist. The sync tick reseeds the field hourly from Oct 30; a one-time `fantasy_sync WC32` from a Railway console fills it sooner.
- `!sync` once after deploy so `/round` appears.
- The production bot app needs the `trk` set-symbol emoji: `python -m bot.scripts.upload_app_emojis keyrune:trk` with the production token.
- The bot creates the Fantasy Champion role on its next role reconcile.
- Soft launch: without `"live": true` on the event there is no nav tab and no #watch-party post; testers use `/pro-play/worlds-32` or the Tools card. Setting `"live": true` turns on both, and post 1 fires 7 days before picks lock.

## Event structure, Worlds

- 14 Swiss rounds over Friday and Saturday, each day 3 Draft rounds then 4 Standard rounds: Draft 1–3 and 8–10, Constructed 4–7 and 11–14. Pro Tours run 16 rounds with Draft 1–3 and 9–11.
- 12 or more match points after the cut round plays Day 2, at Worlds and every Pro Tour in the data.
- Sunday Top 8 is single elimination in Standard, best of five. Picks lock when Round 1 starts, November 13 at 9:00 ET.
- Source: https://magic.gg/news/world-championship-32-fact-sheet-for-competitors

## Game rules

- Pick 4 players, one per slot. Players only: no cards, no packs, no grinding, and scoring is verifiable from public results.
- 3 points per match win, 1 per draw. Byes score as wins, including the byes Melee gives players already locked into the Top 8, matching Melee's standings.
- Captain, gold: double in all rounds. Drafter, LLU green: triple in Draft rounds, nothing in Constructed. Constructed, blue: double in Constructed rounds, nothing in Draft. Player, purple: single in all rounds.
- Day 2 replacements: a pick who misses Day 2 can be replaced before the first Day 2 round. The replacement scores from that round on and the Day 1 points stay.
- Top 8 lineup bonus, flat with no slot multiplier: 4 for reaching the Top 8, 4 per Quarterfinal or Semifinal win, 8 for winning the Final, so the champion's run is worth 20.
- Bracket, added to the total: before the Quarterfinals each member picks a winner for all 7 matches, with an optional game score. Later picks follow the member's own earlier winners. A correct winner scores 2, 4 and 8 by stage, and the exact game score adds 1. A later pick scores only if that player reached and won the match. Maximum 31. A winner with no game score saves and scores the winner points.
- The Bracket opens when the reveal marker passes the last Swiss round and locks when the Quarterfinals start or at `bracketLockAt`.
- Standings: total points, then the champion call, then the earliest last change to the Day 1 lineup.
- The points were reviewed against Worlds 31 and kept. Expected Swiss value at Worlds: Captain 42, Drafter 27, Constructed 24, Player 21. Day 2 win rates were about 50% whatever the Day 1 record, so a replacement gains no hot hand.

## Discord

Posts are green embeds with the set symbol before the title and the event crest as thumbnail, built in `bot/services/fantasy_posts.py`, sent by `bot/tasks/pro_play_posts.py` and previewed with `!test proplay`. Only events with `"live": true` post to #watch-party.

| # | Fires | Channel |
|---|---|---|
| 1 | Picks open, 7 days before picks close | #watch-party |
| 2 | Picks closing, 24 hours and 1 hour before | #watch-party |
| 3 | Day 1, Day 2 and Top 8 live, at each day's coverage start | #watch-party |
| 4 | Day 1 complete, when the marker passes the cut round | #watch-party |
| 5 | Top 8 Bracket open, when the marker passes the last Swiss round | #watch-party |
| 6 | Results on Melee for a round that waits for `/round` | #bot-spam, mentions the owner |
| 7 | Results with the top 3, when the marker passes the Final | #watch-party, pinned |

- Spoiler-free reveals: Melee posts results before coverage shows them. The marker auto-reveals a round 90 minutes after Melee completes it; each day's first round and every Top 8 stage wait for a moderator's `/round`. Source: Mike Provencher of MTG Scribe.
- **Fantasy Champion**: a gold managed role that moves to each event's top 3 on the production guild when the Final is revealed. The closing post mentions it above the top 3.
- Local runs: `.env` sets `WATCH_PARTY_CHANNEL_ID` to the dev server's watch-party channel, so the local bot posts there for a live event.

## Site

- Pro Play lives at `/pro-play/<slug>`, with tabs as URLs: `/players`, `/standings`, `/top-8`, `/leaderboard`. `/fantasy/*` redirects. "FANTASY MAGIC" sits above the title as the game's name; Worlds 32's title is WORLD CHAMPS beside its crest.
- Nav: a PRO PLAY tab with the crest and an OPEN, LIVE or RESULTS pill, from one month before a live event to 7 days after it. Year round, a Pro Play card on Tools, "Fantasy Magic and past Pro Tour results", opens the next Melee-listed event with picks open, otherwise the current or latest event.
- Live data: the team sheet reads the `public_fantasy_*` views. A per-browser spoiler-free eye, on by default, stops every number at the reveal marker; on mobile a tap shows its meaning for 2.5 seconds. Event state refreshes every 60 seconds and on focus, results and members only when the marker or Melee's completed round moves.
- Standings highlight the member's team with each slot's color and tag, Day 1 picks that were replaced included. While replacements are open, clicking a Day 2 player's row replaces the eliminated pick, the same as a field tile; otherwise a click opens the profile.
- Standings per round rank by match points, opponents' match-win percentage with a one-third floor, game-win percentage, then opponents' game-win percentage.
- The Top 8 shows finished matches as they land, the real entrants of undecided matches with the member's pick highlighted, and "N of M picks right". The Podium waits for the Final. Before Melee posts Quarterfinal pairings, the site predicts 1v8, 2v7, 4v5 and 3v6 from its own standings.
- Replays: read-only Worlds 30, Worlds 31 and six Pro Tours from `frontend/src/data/fantasyReplay<Code>.json`, with players, standings by round, the Top 8 bracket and player profiles. Names come from Melee, magic.gg and the MTG Elo Project; players who publish only a Melee username in a single event show the username.
- Player profiles: photo, country, qualification, recent stats over the last 7 Pro Tours and Worlds from `fantasyPlayerStats.json`, career highlights and the match history.

## Field

`bot/data/fantasy/wc32_field.json` is the curated Worlds 32 seed: 134 invitees from magic.gg's invitation list with country, qualification, Melee username and photo. Photos hotlink magic.gg's Contentful CDN, Melee and X; 120 have one. Name-only photo matches that couldn't be confirmed show initials. The authoritative field is the Melee registration once Round 1 pairings appear; a Melee player missing from the seed is added on sight.

Invitations change until the event: Arena Championship 13 on October 24 still awards spots, and players withdraw. The `update-pro-play` skill runs `bot/scripts/fantasy_field_drift.py` against the registry's `invitationListUrl`, researches new invitees and stages the seed edit. Run it after each invitation-awarding event and in the week before picks lock. The hourly reseed removes a player who left the seed unless a member picked them or they have results. A pick who never plays scores nothing on Day 1 and can be replaced for Day 2 like anyone who misses it. New invitees have no profile stats until `fantasyPlayerStats.json` is regenerated.

Qualification groups, in this order: Worlds 31 Top 8, Pro Tour, Points, Arena Championship, MOCS Showcase, Regional.

## Copy

- Rules: "**3 points** per match win and **1** per draw", "Captain scores double in All rounds", "Drafter scores triple in Draft rounds", "Constructed scores double in Constructed rounds", "Players who miss Day 2 can be replaced before Round 8".
- Premise while picks are open: "Put together a team of four Pro Players from **Worlds 32**", then "You score points every time they win a match".
- Countdown "Closes in 32 days, 10 hours", then "Picks are closed". Lock line "Round 1 starts Fri, Nov 13 at 11 AM GMT-3", time in green.
- Field status: "Picking Captain", "✓ Picks saved", "Log in to save picks", "Picks are locked", "Replace before Round 8".
- Header status: "Round N of 14" with a pulse, "Day 1 complete", "Top 8 plays Sunday", "Top 8 Live" with a pulse, "Event complete".
- Spoiler-free tooltip: "SPOILER FREE: live coverage results only" or "SPOILERS ON: latest results from melee.gg".
- Bracket: "Pick the winner of each match for 2 points in Quarterfinals, 4 in Semifinals and 8 in Finals", "Pick the exact games for 1 more point", "Your pick: X", "No pick", "N of M picks right".
- Names: tabs PLAYERS, STANDINGS, TOP 8, LEADERBOARD; Podium label CHAMPION; leaderboard column TOP 8. The Top 8 predictions are the Bracket everywhere; "pick'em" was rejected.

## Tried and rejected

- Layouts: the P0P1 card pool, a scouting report table, a fanned card hand.
- Profile access: a docked scouting column, a two-step pick through the profile, a full-screen or scrolling mobile profile, a chart icon on every tile.
- Win rates or "picked by" percentages on picking cards: they anchor everyone onto the same players.
- Snake draft on Discord, packs, earning picks from LLU activity, a Dota-style daily lineup reset, 5 slots, a Rogue bonus.
- Mythic orange for the Captain, "WORLDS 32" as the title, a crest stacked above the title on mobile.
- Fixed `bracketOpensAt` times: the Bracket follows the reveal marker.

## Local testing

The DEV pill in the bottom-right corner, shared with P0P1, switches the team sheet between Live and every phase: picking signed in or logged out, Day 1, the cut, Day 2, Bracket open, Quarterfinals done and Event complete. On production the same pill reads DEMO and shows on an event's page until it gets `"live": true`.

- Live shows the real event. Locally, `fantasy_dry_run --reset` puts Worlds 32 back to its registry entry and field seed, with no results or picks, so Live matches production before the event.
- While the event has no results, every preset reads `frontend/src/data/fantasyDemo.json`, a snapshot of Worlds 31 staged as a finished dry run, loaded only when chosen. Each preset reshapes the event state and cuts the results at its round in the browser.
- Every preset is read-only: edits stay in the browser, and switching presets remounts the team sheet so nothing carries into Live. Saved picks follow the preset's phase: the lineup starts empty while picking, and replacements only appear from Day 2.
- The snapshot's own lineup is a fixture in the dry run: Captain Ha Pham replaced by Javier Dominguez, Drafter Arne Huschenbeth, Constructed Jean-Emmanuel Depraz and Player Simon Nielsen.

`bot/scripts/fantasy_dry_run.py` copies a finished event's real field and results into another event on a local database, frozen at any round, with 30 members plus the dev user. It refuses a non-local `DATABASE_URL`. Round 0 stages the picking phase; 7 is the cut, 11 Day 2, 14 Bracket picking, 17 final. To rebuild the snapshot, stage Round 17, run the snapshot script, then reset:

```
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord \
  .venv/bin/python -m bot.scripts.fantasy_dry_run --through-round 17
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord \
  .venv/bin/python -m bot.scripts.fantasy_demo_snapshot
DATABASE_URL=postgresql://postgres:devpw@localhost:5433/dischord \
  .venv/bin/python -m bot.scripts.fantasy_dry_run --reset
```

## Data sources

- Melee's API is restricted to organizers; public tournament pages carry pairings, game scores and standings with no login.
- Event ids: Worlds 30 146430, Worlds 31 375961, PT Aetherdrift 228372, Final Fantasy 303784, Edge of Eternities 355905, Lorwyn Eclipsed 394299, Secrets of Strixhaven 415628, Marvel Super Heroes 434455.
- magic.gg's public Contentful key makes player photos searchable by name; the MTG Elo Project API gives career records and named match histories.
- 2027 calendar: PT Nauctis Detroit Feb 26–28, PT Tokyo May 14–16, PT Las Vegas Aug 27–29, Worlds 33 Amsterdam Dec 3–5.
