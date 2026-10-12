---
name: update-pro-play
description: Reconcile a Pro Play event's curated field seed with magic.gg's invitation list. Reports invitees added, removed or changed since the seed was built, researches each new player's Melee username, country and photo, edits the seed and stages it for review. Run it after each event that awards invitations, such as an Arena Championship, and again in the week before picks lock. Takes an event code, WC32 by default. Never commits or pushes.
---

# update-pro-play

Keep `bot/data/fantasy/<event>_field.json` in step with the official invitation list.

## Why this is a skill and not just the script

`fantasy_field_drift` only says what changed. The work is what comes after: a new invitee needs a Melee username so their results attach, a country code for the flag and ideally a photo, and none of that is on the invitation page.

## How the seed reaches players

The registry entry's `fieldSeed` points at the seed, and its `invitationListUrl` at the magic.gg page. From 14 days before the event, the sync tick upserts the seed into `fantasy_players` every hour, and removes players who left the seed unless a member already picked them or they have results. So a seed edit reaches the site within an hour of the user pushing it. Nothing reaches players before the push.

## Workflow

### 1. Report drift

```
.venv/bin/python -m bot.scripts.fantasy_field_drift WC32
```

It prints the invited and seeded counts, then one line per finding, and exits 1 when anything changed. If it says no invitation table was found, magic.gg changed the page layout: fix `parse_invitation_list` before anything else.

| Finding | What to do |
|---|---|
| `added: Name, Country, sources` | Add an entry, researched as in step 2. |
| `removed: Name` | Delete the entry. Tell the user the reseed keeps them in the field if a member already picked them. |
| `country changed` | Update `country` and `countryCode` after checking which side is right. magic.gg's casing differs from ours, which the script ignores. |
| `sources changed` | Copy the new `sources` as printed. Qualification groups on the site come from these strings. |

### 2. Research each new invitee

Each seed entry holds `firstName`, `lastName`, `country`, `countryCode` as ISO 3166 alpha-2, `sources`, `meleeUsername`, `photoUrl` and `photoSource`. Keep the name exactly as magic.gg spells it, since the drift check matches on it.

- **Melee username:** the event's own Melee page lists nobody before Round 1 pairings. Find the player in a recent Pro Tour or Worlds on Melee, whose `POST /Match/GetRoundMatches/<round id>` responses carry `Username` and `DisplayName`, or match their opponents round by round against the MTG Elo Project (`https://mtgeloproject.net/api/`). Confirm through a second event when the name is common. Leave it `null` when unsure: the sync links them by name at Round 1.
- **Photo:** search magic.gg's Contentful assets by name for a player card or Top 8 photo. The read-only Contentful key sits in magic.gg's public JS bundle. A player card cropped with `?w=168&h=225&fit=thumb&f=face` gives `photoSource: "magicgg-face"`. Use only a photo whose identity you can tie to the player beyond the name; otherwise leave `photoUrl` `null` so the site shows initials.
- **Country:** take it from the invitation list and set the matching alpha-2 code.

Report each new player's confidence, and say plainly which photos and usernames rest on a name match alone.

### 3. Stats

`frontend/src/data/fantasyPlayerStats.json` is a frozen snapshot of the original invitees' records over the last 7 Pro Tours and Worlds plus career highlights. A new invitee's profile shows no stats until it is regenerated. The scripts that built it live in the git-excluded `spec/fantasy-data/scripts/` on the user's machine. Tell the user which new players have no stats, and regenerate only if they ask.

### 4. Verify

```
python3 -c "import json; json.load(open('bot/data/fantasy/wc32_field.json'))"
.venv/bin/python -m bot.scripts.fantasy_field_drift WC32
.venv/bin/pytest bot/tests/test_fantasy_sync.py bot/tests/test_fantasy_field_drift.py
```

The second run should exit 0 with matching counts.

### 5. Stage, do not commit

```
git add bot/data/fantasy/wc32_field.json
```

The user reviews and commits. Never commit or push here.

### 6. Report

- Invited and seeded counts, and every finding with what was done.
- New players with their username, photo and country, and the confidence of each.
- Removed players, and whether any member picked them, if the user can check production.
- Players left without stats.
