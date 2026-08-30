# Community pod format schedule + vote — as built

The pod draft schedule is community-driven: players vote for the flashback sets they want, and a cheap sweep lays the season's daily formats from that vote onto a DB overlay that the calendar, the launcher and the vote card all read. This is the as-built record of what shipped; read the code for how it works today.

## The day model

A scheduled day offers exactly **two formats**, and each runs in **both the Early and Late slot**, so the calendar shows two icons a day. The allocator's unit is the day: it writes the same two formats to both `(day, SLOT_EARLY)` and `(day, SLOT_LATE)` overlay rows.

Two rotating pools by weekday:

- **Flashback days (Mon/Wed/Fri/Sun):** the season's featured pick plus one voted flashback set.
- **Staple days (Tue/Thu/Sat):** the latest set plus the Peasant cube.

Default weekly grid:

| | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---|---|---|---|---|---|---|
| Pool A | MEMA | HOB | MEMA | HOB | MEMA | HOB | MEMA |
| Pool B | Flashback | Peasant | Flashback | Peasant | Flashback | Peasant | Flashback |

The featured pick is per season: `FEATURED_BY_SEASON = {"HOB": MEMA_CODE}` in `bot/services/pod_format_allocator.py`. A season with no entry runs the voted flashback alone on flashback days. Cubes are fixed on the schedule and never compete in the vote.

## The overlay

`pod_schedule_slots` (migration `ea16a2dee098`) is a per-`(day, slot)` overlay of `formats[]` with a `source` of `manual` (organizer) or `auto` (allocator). `set_slot` is the one writer. An empty overlay renders byte-identical to the old hardcoded schedule. `LATEST` resolves to the active set; `FLASHBACK` is a placeholder for a flashback day with no set chosen. Helpers in `pod_format_schedule.py`: `set_slot`, `manual_slots`, `auto_slots`, `clear_auto_slots(except_days=…)`, `scheduled_formats`, `planned_on`, `formats_on`.

## Voting

Backed by `pod_format_votes`. Approval voting: a player toggles a vote for every format they would draft. The ballot **seeds the curated flashback sets** (`seed_formats` → `flashback_picker_sets`), so a season opens with every candidate clickable; write-ins reach anything off the list. The ballot order is **fixed by release date, newest first**, never by votes, so a button never moves under a clicker. When the list overflows the 20-button grid, voted options are always kept and unvoted ones drop oldest first. Long set names fall back to the bare code past 24 chars; a leading "The" and colon subtitles are trimmed. Fields pad to a multiple of three so a short last row aligns.

**Posting is manual.** There is no automated open or reminder. `/openvote` (`[Admin]`, moderator-gated, in `bot/commands/pod_schedule.py`) posts and pins the vote card in pod chat with the `@Pod Drafters` ping; re-running it reposts and re-pings. The card's option buttons defer first and repaint the public card through a `RenderQueue`.

Row 0 carries Add Format, 📊 Voters and an organizer-only ⚙️. The Voters view lists only formats that have voters. The ⚙️ (gated by `organizer_authorized_interaction`) removes a written-in format off the curated seed, purging its votes so a bad write-in leaves the ballot; seeded formats are not offered since they cannot be removed.

## The allocator — `bot/services/pod_format_allocator.py`

`run_allocation(session, start, rewrite=True)` plans from `start` to the day before the next rotation and writes `auto` overlay rows. Flashback-set choice per flashback day:

- **Eligibility:** a flashback set needs `VOTE_FLOOR = 6` raw votes; below that it is invisible.
- **Weighting:** ranking uses votes weighted by recent pod attendance, split at the terciles of the drafters who showed up over the **last two seasons** (`_attendance_window_start`), floored at 1 so a new player still counts. Vote surfaces always show raw counts.
- **Placement:** proportional to weighted score, no set two flashback days in a row, and **spread across weekdays and weeks** so a popular set does not settle onto one weekday.

Left untouched by a sweep: **manual overrides**, the **championship day**, and any **day already on the launcher** (`_launched_days`, matched on existing poll signals) so a fresh vote never changes a format players are already looking at.

## Freshness — 3×/day re-sweep

The math is cheap (~5 ms), so the schedule-post tick (`bot/tasks/pod_schedule_post.py`, 10:30 / 15:00 / 20:30 ET) re-runs the full sweep before repainting the card. The overlay tracks the vote within hours and the card, launcher and calendar keep reading one source. `!test allocate` runs the same sweep on demand. There is no separate weekly allocator tick.

## Surfaces

- **Schedule card + calendar image** (`pod_schedule_card.py`, `pod_schedule_image.py`): the `/pod-schedule` calendar posts and pins to pod chat, kept fresh by the tick. Cells list the day's actual formats; a day running only the latest set shows its symbol faintly. Set symbols resolve to the code's own PNG first, then the cube glyph for a cube without one. The TBD placeholder renders in blurple. The embed states the two-a-day shape during the community window and `Latest Set every day` during a set's own run.
- **Curated flashback pickers:** `flashback_picker_sets` (`bot/sets.py`, `FLASHBACK_PICKER_CODES`) feeds `/draft`, the launcher set select and the override, newest release first, capped so no select exceeds Discord's 25 options. `/draft` and the launcher keep a write-in for anything off the list.
- **Override wizard (⚙️ on the schedule card):** organizer-only. Picks a day, slot and formats from the curated list plus an **Add Format** write-in, writes a `manual` row the allocator never overwrites. When the day is already on the launcher it also **retargets** the still-gathering pods (`retarget_launcher_day` in `pod_daily_poll.py` + `expire_dropped_poll_signals_sync` in `pod_launch.py`); a pod that already fired keeps its draft.

## Player guide

`docs/guide/pod-coordination.md` describes the live behavior for players.
