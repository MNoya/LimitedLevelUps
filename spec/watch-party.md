# Watch Party channel automation

The watch party channel is where the server talks about pro-level Magic events while they run. Mods keep its name and topic up to date by hand today, so it drifts: the topic still reads "Next up: Spotlight Dallas - Sep 4-6" weeks later. The bot takes that over, reading the MTG Scribe calendar it already bundles.

## Scope

- The channel's name and topic follow the calendar: the event running now, or the next one.
- A Discord Scheduled Event for each World Championship, Pro Tour and Arena Championship, so it shows in the server's Events list with an Interested button.
- A green embed for each weekend of events: "upcoming" when the channel moves to it, and "is live!" when its headliner starts. Both lead with the headliner and list the rest of the weekend.
- An announcement post for Pro Tour and World Championship events only, in the shape of the post template mods use today.

Out of scope: per-round coverage and results. Nothing here pings anyone.

## The channel

- Found by ID through a `watch_party_channel_id` setting, never by name, because the bot renames it. Today that is `📺🎉-mocs` (`1007375760484470984`), which moves from Events to MTG General.
- Name pattern `📺🎉-<slug>-watch-party` while an event is running or coming up soon, `📺🎉-watch-party` otherwise. Slugs: `rc-<set>`, `spotlight-<set>` and `pt-<set>` with the set Arena is drafting when the event starts, `ac<number>` read from the Arena Championship title, and `worlds`. The topic names the city or event.
- The topic names what is running now and what is next, with dates and the stream where one is known. It replaces the hand-written "Next up:" line. World Championship and Pro Tour stream on twitch.tv/magic, and events tagged `star-city-games` on SCG's Twitch. Scribe also tags the organizer of events abroad, but the organizer does not always run the coverage, so those carry no stream link.
- The name moves to the next covered event the day after the current one ends.
- Discord allows two renames per channel every ten minutes. The bot renames only when the name it computes differs from the current one, so a tick that finds nothing new makes no API call.

## Which events count

An event counts when Scribe tags it `coverage`. Mike Provencher, who runs MTG Scribe, tags the events that belong in this channel, so the choice lives in Scribe. The bot reads them through `load_events(arena_only=False)`.

The type picks the slug and the headliner, top first. It matches on the tag or the title, so a tag Scribe misses still leaves the event typed by its name:

| Event | Tag | Title |
|---|---|---|
| World Championship | `magic-world-championship` | `World Championship` |
| Pro Tour | none yet | `Pro Tour` |
| Arena Championship | `arena-championship` | `Arena Championship` |
| Spotlight Series | `magic-spotlight-series` | `Spotlight Series` |
| Regional Championship | `regional-championship` | `Regional Championship` |

A World Championship, Pro Tour or Arena Championship always counts, even with no `coverage` tag. A Spotlight Series or Regional Championship counts only with `coverage`, because Scribe picks which of those get coverage.

An event tagged `qualifier`, or with `Qualifier` or `ACQ` in its title, is never an Arena Championship. "ACQ Weekend" carries `arena-championship`, and the legacy "Arena Championship Qualifier Weekend" title contains the full name, so without this check both would count as always covered.

Big events overlap: Oct 23–25 2026 carries two Regional Championships, Spotlight Hartford and Arena Championship 13. The channel name shows one headliner, picked in the table's order, and holds it for the whole overlapping window: Oct 23–25 reads `ac13` from Friday, though Spotlight Hartford starts first. The topic lists every covered event in that window.

The bundle refreshes only when someone runs `/update-scribe`, so an event Scribe adds reaches the channel on the next capture and deploy.

## Scheduled Events

- One External scheduled event per World Championship, Pro Tour and Arena Championship, with the channel link as its location.
- Scribe gives whole days and no start times, because they depend on the event and its timezone. Start and end come from a hand-kept schedule in `bot/services/watch_party.py`, read from each event's official fact sheet, with an estimate where none is published: Arena Championship 13 is estimated at 9 AM to 6 PM Pacific. An event with no row falls back to 9 AM to 6 PM Eastern, and `scribe_drift` flags it. World Championship 32 runs 9 AM to about 8 PM Atlanta time on Nov 13–14 and 9 AM to about 5 PM on Nov 15.
- The same schedule numbers each Pro Tour within its year, which the announcement needs, and gives the first day's subject such as "Draft Day 1".
- The `/update-scribe` skill keeps the schedule current. When a capture brings a new World Championship, Pro Tour or Arena Championship, the skill looks up its official times and adds a row.
- The bot finds an event it already created by matching name and start among the guild's scheduled events, so no new table is needed.
- The bot role already has Manage Events, Create Events and Manage Channels on prod.

## Announcement post

World Championship and Pro Tour only, posted once when the event starts, in the watch party channel, with no ping. The mods' current template carries a heading, one sentence that names the event and its ordinal for the year ("the third PT of 2026"), and the first day's subject ("PT Marvel Super Heroes - Draft Day 1"). The template's channel link is left out, because the post lands in that same channel. The copy lives in `bot/tasks/watch_party_post.py`. This doc does not mirror it.

## Premier events ahead

The 2026 Pro Tours are over, so World Championship 32 is the last one this year. The 2027 schedule is published:

| Dates | Event | City | Formats |
|---|---|---|---|
| Nov 13–15 2026 | World Championship 32 | Atlanta | Star Trek Draft, Standard |
| Feb 26–28 2027 | Pro Tour Nauctis | Detroit | Nauctis: The Sunken Realm Draft, Modern |
| May 14–16 2027 | Pro Tour 2 | Tokyo | Draft, Standard |
| Jun 18–20 2027 | Magic Limited Championship, deferred | Minneapolis | Limited |
| Aug 27–29 2027 | Pro Tour 3 | Las Vegas | Draft, Standard |
| Dec 3–5 2027 | World Championship 33 | Amsterdam | Draft, Standard |

The Magic Limited Championship is deferred until it is known whether it streams. If it does, its channel is `📺🎉-limited-champs-watch-party`.

## /event-scribe Coverage choice

A Coverage entry in `/event-scribe`'s format menu lists the covered events ahead, from the same `coverage` tag the channel follows. Today the command reads Arena events only, so tabletop events like Regional Championships never show.

## Where it runs

- The pure logic, meaning headliner pick, slug, name and topic, goes in `bot/services/watch_party.py`.
- The Discord side goes in a `bot/tasks/watch_party_post.py` tick every 15 minutes. It edits the channel only when the name or topic changed.
- A render-only `!test watchparty` preview shows the name, topic and post the bot would apply today, and is listed in `PRODUCTION_SAFE_TESTS`.
- Tests cover the headliner pick across overlapping windows and the slug for each tier.

