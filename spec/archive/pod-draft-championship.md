# Pod Draft — Set Championship (engineering note)

The season-closing 8-player invitational: one pod whose seats go to the top of the active-set leaderboard among whoever shows up. The plain-language flow (when it runs, the invitation waves, seeding, how it plays) lives in `spec/set-championship.md` — read that first. This note only records the engineering facts that are not obvious from the player-facing guide.

The whole flow is now **automated and bot-created**. The earlier design in this file — a manually-created Sesh event with a hand-pasted announcement from `prompts/championship-announcement.md`, driven by a `championship_date` in `UPCOMING_RELEASES` — is gone. Do not reintroduce it.

## Where the code lives

- `bot/services/championship.py` — date derivation over `bot/sets.py` (no Discord), the frozen seed snapshot, invite-wave tiers. The championship is the Saturday before the successor set's prerelease weekend at 2 PM ET, created `CREATION_LEAD_DAYS` ahead; the prerelease date comes from the successor's `SetSeed`, which falls back to the Friday before its Arena release when none is recorded. `plan_for` returns None when the active set is the newest registered entry, so a missing successor simply skips the season.
- `bot/tasks/championship_post.py` — the daily ET tick that posts the card on its creation day, freezes the standings, posts the thread standings, then arms the invite waves and the Yes-tally seeding table. Idempotent per set: it never posts a second card once one exists.
- `bot/services/championship_copy.py` — the single source of every user-facing string, so the live flow and `!test championship` render from the same builders.
- `bot/commands/testchampionship.py` — the owner-only end-to-end preview.
- `bot/services/pod_launch.py` + `bot/tasks/pod_daily_poll.py` — the launcher lane override on championship day (read-only pointer into the thread, no join toggle; the Late pod is untouched).
- `bot/models.py` + the `pod_championship_seeds` table — the frozen-standings snapshot the seeds lock to at creation.

## Enduring facts (unchanged from the original design)

- **Not a new event type.** The championship is a normal `PodDraftEvent` recognized by name: `is_championship(name)` in `bot/services/pod_drafts.py` is the single source of truth (substring `"championship"`, case-insensitive, None-safe). No `is_championship` column.
- **The only rule that flips is seating → `leaderboard`.** Format stays the active set and pairings stay `swiss` (both already the defaults). The leaderboard-seating flip also activates the 8-seat cap and the presence-honoring draft-time cut, both of which already lived in that path. Everything downstream of "8 players are seated" (Swiss, result reporting, champion finalization, standings, recap) is the existing `pod_tournament` flow, unchanged.
- **Two-phase seeding, one embed.** Phase 1 (before the lobby): the RSVP'd Yes list ranked by leaderboard, top 8 seated, the rest alternates. Phase 2 (lobby up): the connected Draftmancer players are the pool, rank-sorted, over-cap players shown as kick candidates. Presence beats a stale Yes automatically. For the championship the seeding table auto-posts and refreshes in place; non-championship pods keep the post-on-demand behavior.
- **Championship seeds off the frozen snapshot, not live standings.** The seat order and the top-8 cut rank confirmed players by the `pod_championship_seeds` snapshot frozen at card-post time, so seeds do not shift after the card goes up. Threaded as `rank_override` (player_id → frozen rank) through `seating_message_for_event` → `_rank_ordered_names_sync` / `seed_attendees`; players outside the snapshot fall back to live rank, and non-championship pods pass no override so they stay fully live. Slug and trophies still read live (the snapshot has neither), which is inert at event time since the set is over.
- **Draftmancer session name** uses a fixed championship base (`LLU-<SET>-Championship`) with the existing `-A`/`-B` collision suffixing, so the player-facing session URL stays clean.
- **Crown 👑 marks the season championship**, distinct from the per-pod champion 🏆, so the two never blur.

## Known follow-ups (not built)

- **Crowning role move** — winner → `Set Champion`, previous holder → `Previous Set Champion`. Post-event, unbuilt. The card resolves the `Set Champion` role by name and needs a role named exactly "Set Champion" in the guild, falling back to plain text otherwise.

## Out of scope

- Multi-pod split for 9+ qualified players.
- Under-fill / fewer-than-8 handling.
- Auto-kicking non-qualified walk-ins (the bot surfaces the cut; the organizer kicks).
