# Pods on the Site

The features that finish what pod seasons started. Seasons gave the site a way to browse pods that already played; these gave it the standings that only existed in Discord, a `/pods` page that reads on a phone, and the guide a newcomer needs.

Four of the five are shipped. **Feature 1, the guide, is all that is left.** Sections are numbered in the order they were asked for, not the order they were built: see **Build order**.

## Decisions already made

These constrain the work below and should not be relitigated inside it.

| | |
|---|---|
| **Pod points stay per set** | The HOB leaderboard means people drafting HOB, so flashback and cube pods never contribute to a set's board. Seasons are a pods-page concept for browsing, not a scoring key. Peasant and flashback pod points reach no set leaderboard, and their season standings are the leaderboard for them |
| **A board window is a URL, a filter is not** | `/pods/PEASANT-MSH` is a board scoped to a window, the way `CUBE-SOS` is. Narrowing a season by format stays local state, because it only narrows a view |
| **Cube and pod runs are declared** | Dates come from Scribe or the announcement and live in `cube_variants.json`. Nothing infers a window from draft activity |

---

# 1. Pod guide on the website — `/pods/guide`

The page a newcomer reads before they turn up, and after it ships the only pod documentation this project keeps.

## Decided, 2026-08-15

| | |
|---|---|
| **Route** | `/pods/guide`. React Router ranks a static segment above `/pods/:slug`, so it wins whatever the declaration order, but declare it above anyway for whoever reads `App.tsx` next |
| **Shape** | The `AboutPage.tsx` shape: `AppHeader` + `max-w-[1040px]` main + `Footer`, hand-authored JSX. There is no markdown pipeline in `frontend/` and this adds none |
| **`docs/guide/pod-coordination.md` is retired** | Deleted in the commit that ships the page. It started as a reference and turned into 206 lines of over-explained detail nobody reads end to end. The page replaces it outright: there is no second document and nothing to keep in sync |
| **Organizer material is a collapsed section on the same page** | One URL, one title entry, one `og:` block, and no height cost to a newcomer who never opens it |
| **Screenshots are real, cropped, served from `frontend/public/guide/`** | Captured off the test server through `!test`, not rebuilt in markup |
| **Copy is written for a player, not ported** | The retired doc is source material for what is true, never for how to say it |

## How the copy is written

This is the point of the feature, so it is a constraint and not a preference.

- Explain only what a player cannot work out by looking at the card in front of them. Everything else is either a screenshot or nothing.
- One idea per sentence, short sentences, no subordinate clauses stacking qualifications. No em dashes.
- Name the button, the command and the thing. `Sign Up`, `!pod`, the thread, the lobby.
- Second person, present tense. "You click the pod that fits your day", not "players may elect to".
- No paragraph longer than three sentences at the top level. Anything that wants a fourth belongs behind a disclosure.
- The retired doc's own opening paragraphs are close to the target register. Its later sections, the ones that qualify every case, are the thing to avoid.

The progressive disclosure the page is built on: a short spine anyone can read in a minute, with sub-sections, collapsibles and info hovers holding the detail. A reader who wants the rules of a 10-player pod opens it. A reader deciding whether to turn up never sees it.

## Structure

1. **What a pod draft is.** Three sentences and one screenshot of a finished pod. Free, daily, 6 to 8 players, results count on the leaderboard.
2. **Your first pod, in five steps.** The spine. Each step is one line of copy plus one cropped screenshot: the launcher, the signup card, the roster reminder, the Draftmancer lobby, the results card. This is the part someone reads before their first pod and nothing else on the page competes with it.
3. **Playing the pod.** Ready check, rounds, reporting results, sharing your deck. Screenshot-led.
4. **The details, collapsed.** One disclosure each: signing up for two formats at one time, leaving, Maybe versus Confirm, `!pod` when a table is short, what happens when a pod splits into tables, team draft, round robin, closed decklists, mock drafts, voice.
5. **Formats and when pods run.** The two daily slots and where the schedule lives. Static copy, and the same narrow exception noted under build order 3 applies: do not derive a calendar in TypeScript.
6. **For organizers, collapsed.** See below.
7. **Watch the walkthrough.** A slot for the episode Alex is recording. Ships empty or omitted until the URL exists.

## The organizer section

The reason it is written: the bot has features only one person knows in depth, and that is the constraint on anyone else running a pod.

Behind one disclosure, each item one or two sentences: `/draft` and its presets, the lobby Settings panel, Draft Setup (pick timer, packs, cube pack size), Mode (Pick One / Pick Two), Max Players, Force Start, Restart Draft, Manage Rounds and the round editor, Drop Player, Closed Decklist, the scheduled-pod Description, and the disconnect vote. Each names the surface it lives on, since finding the panel is the actual problem.

Not in it: anything a player never sees the effect of, and anything that only exists as a code path.

## Screenshots to capture

All from the test server, all cropped tight to the card, saved as PNG under `frontend/public/guide/`. Every command below was read in `bot/commands/test*.py` and posts the surface named.

| file | command | what to crop |
|---|---|---|
| `launcher.png` | `!test launcher` | the Daily Pod Launcher with its slot buttons |
| `signup-card.png` | `!test rsvp 60 5` | the signup card with Sign Up / Maybe / Can't and five seeded Yes |
| `roster-reminder.png` | `!test reminder` | the roster card with Confirm and Leave |
| `tables.png` | `!test tables` | the split shape, for the collapsed tables disclosure |
| `lobby.png` | `!test lobbyopen` | the lobby card with the Draftmancer link |
| `ready-check.png` | `!test ready` | I'm Ready / Not Ready / Stop |
| `round.png` | `!test round1` | a round's pairings |
| `report.png` | `!test submit` | the result dropdown |
| `podium.png` | `!test podium` | the pod result post. Blocked on production, so run it on the test server |
| `rally.png` | `!test rally` | one `!pod` rally line |
| `settings.png` | `!test settings` | the Settings panel, for the organizer section |

Treatment: crop to the card, no Discord chrome beyond what makes it read as Discord, consistent width, dark theme. The reference screenshots the user already has from the other draft bot set the bar.

They go stale when copy or buttons change. That is accepted, and it is the cost of retiring the markdown: a stale screenshot misleads less than 206 lines nobody reads.

## Where it is linked from

- `/pods`: a link in the page chrome, the way `/leaderboard` reaches `/leaderboard/about`.
- The `SIGN UP ON DISCORD` CTA area, so someone who has never played reads the guide before the invite.
- No `NAV` entry. `POD DRAFTS` already matches every path under `/pods`, and a second pod row in the header would be the only nested nav on the site.

## Touch points

`<Route>` in `App.tsx` above `/pods/:slug` (the `*` catch-all stays last), the page file, and **both** `DocumentTitle.tsx` and `functions/_middleware.ts` for the tab title and the crawler `og:` tags.

Plus two outside `frontend/`: delete `docs/guide/pod-coordination.md`, and change the CLAUDE.md rule that points at it so it points at the page instead. **Ask before editing CLAUDE.md.**

## Open

- Does this page also become a Discord guide channel through `!guide`? The pages there are markdown in `bot/server_guide/`, so feeding both from one source means going back to markdown, which is the thing this decision just walked away from. Leaving it out means a Discord reader gets the channel-overview pages and a link to the site.
- The interactive treatment. A stepper that highlights the button each step describes is the version the user described. It is more build than a static column of screenshots and can land second: write the copy and the screenshots first, then decide whether steps 2 and 3 become a stepper.

---

# 2. Upcoming pods, the next 24 hours

## Narrower than it sounds

A pod that reaches six players becomes a `PodDraftEvent` row, and `public_pod_draft_events` has no time filter, so **committed future pods already appear** on `/pods` under UPCOMING with a live countdown. The gap is only the slots that have not fired yet.

## Why it is not one query

Those slots live in two places and only one is queryable.

**`pod_signals` + `pod_signal_members`** hold a row per (launcher message, slot, day): `bucket` encodes the slot and format, `slot_time` the start, `status` is `open`/`fired`/`expired`, and `event_id` links to the pod once it fires. Members carry `rsvp` and `created_at`, which is signup order. **There is no `public_*` view over either table** — confirmed against every migration — so the site currently knows nothing about slots, signups or RSVPs.

**A hardcoded Python config grid.** `poll_buckets_for(day)` gives the day's time slots and `FORMATS_BY_DAY` in `pod_format_schedule.py` gives the formats each offers. There is no table of future slots anywhere. `PodSignal` rows are created one launcher post at a time, and lanes roll forward independently, which is why a live board can carry rows with two different `signal_date`s.

## Shape

A `public_pod_slots` view over `pod_signals` covers most of it: real slot times, formats, status, signup counts, and the `guild_id`/`channel_id`/`message_id` needed to deep-link at the launcher post. That reaches roughly today plus the rolled-forward next-day lane, which is about the 24 hours asked for.

Anything beyond that is config, and there the choice is:

- Port the format grid to a shared JSON registry, the way `cube_variants.json` is read by both sides. Costs a third implementation to keep in sync.
- Have the launcher tick write a small lookahead snapshot the site reads. One writer, no duplicated logic.
- Do not render past what signals cover.

The registry is only worth it if the whole `/pod-schedule` calendar should appear on the site.

## Decided, 2026-08-14

1. **Counts, not names.** A slot shows its time, format and a signup count. No join to players, no Discord identities on a public page.
2. **No writes from the site.** A slot deep-links to the launcher message in Discord and you sign up there. The bot stays the only writer on pod state, so `claim_slot_fire_sync` keeps its assumption that nothing races it.

Both answers keep feature 2 to one read-only view plus a link, which is why it stays the smallest of the three.

---

# 3. Final standings on every pod page — SHIPPED

The full field in rank order is what `/pods/<slug>`'s right rail shows by default, so the standings are the first thing the page says. Rank, player, colors, record and a per-row deck or draft-log button, under the same column headings the index page uses. Clicking a row opens that player's rounds and puts a `‹ STANDINGS` link above their header: the rail is a list that drills down to a detail, not two sibling tabs. Mobile works the same way, standings under the seat grid until a player is picked.

A team draft splits into **Green Team** and **Blue Team** with each side's match wins in its heading and a trophy on the winner. Sides come from draft-seat parity, which is how Draftmancer's team mode seats them and what `assign_teams` records, so the split needs nothing new on the row. A mock has no standings at all and keeps the centered table.

## Tiebreakers are not on the site

`compute_standings` returns OMW%/GW%/OGW% per player and the Discord embed prints them for the win-count groups a tiebreaker actually decided. **The site shows none of them** — rank, name, colors and record only. `placement` is already stored at finalize, so rank order needs no recomputation and there was nothing left for persisted percentages to buy: no reader wanted them, and the only path that zeroes them (`_load_participant_standings_sync`, record-only backfills) has no match rows to derive them from in the first place.

## The record discrepancy: stored wins

`pod_draft_participants.record` is written at finalize from `played_record`, and the view COALESCEs it over a count computed from matches, so the stored one already wins wherever it exists. It is canonical, for three reasons: `public_pod_scoring` reads it straight off the table for pod points, it is the string the Discord thread posted, and it deliberately excludes a forfeited bye so a player who dropped shows only the matches they played.

The live fallback disagreed on exactly that last point, counting a drop's forfeits as losses, so a running pod's record changed the moment it finalized. `c3e5a7b9d1f4` brings the fallback in line and restores two columns a 2026-06-14 view rebuild dropped by accident: `draftmancer_name`, which the site's adapter has been reading as null ever since, and the `kind = 'mock'` CASE, without which all 131 mock participants read as `0-0`.

## Still true, for whatever touches this next

- `pod_draft_matches` references players by `draftmancer_name` strings, not foreign keys. Anything joining matches to players goes through `normalize_player_name`.
- A team draft writes no `placement`, so nothing may key a rank off one. Its rows carry individual records and the sides carry the result.

---

# 4. What `/pods` is trying to be, on mobile most of all

## The complaint, measured

Numbers below are from the running site at 390 x 780, HOB season, 38 players and 10 events. Left column is the y where a block starts, right column is its height.

| block | y | height |
|---|---|---|
| `AppHeader` | 0 | 56 |
| set + window band | 56 | 49 |
| events tabs | 104 | 36 |
| events list, LAST EVENT with its top four expanded | 140 | 317 |
| STANDINGS heading | 457 | 29 |
| column header | 486 | 26 |
| first standing row | 512 | 45 per row |

The standings begin at 65% of the fold, so six rows are visible at 780 and three or four on a phone that shows browser chrome. Tapping ALL grows the events block to 974 and pushes the standings to 1078, a screen and a half down. Tapping UPCOMING with nothing scheduled leaves an 84px block reading "No upcoming pod drafts." and pulls the standings up to 188. The first screen belongs to whichever tab was last touched.

Two corrections to the earlier draft of this section:

- **Mock drafts are not a fourth mobile block in the common case.** A season view filters `e.kind !== "mock"` when no format axis is picked, so `MockDraftsBlock` renders only on the MOCK axis or on a set or cube board route, where `events` is unfiltered. Mobile stacks three blocks, not four.
- **On desktop the events column is not the long one.** At 1440 x 900 the standings column's content ends at 2144 and the events column's at 1275, leaving an 869px hole at the bottom right. Both grid columns are equal width and uncapped, so whichever object has more rows sets the page height and the other leaves a gap. Which one that is depends on the season: 38 players outrun 10 events, 6 players would not.

## What feature 3 made redundant

`EventStandings` expands an event row into its top four, a "+N MORE PLAYERS" line and a VIEW BREAKDOWN button. It exists because there was nowhere better to look. There is now: `/pods/<slug>` opens on the full field in rank order with per-row deck and draft-log buttons, beside the seat grid.

So the expansion spends 190 to 240px of the mobile fold on a worse version of a page one tap away, and on an in-progress pod it spends it on nothing at all: no records exist yet, so all four rows render as columns of dashes. That is the default state of `/pods` right now, mid-pod.

**Removing the inline expansion is the largest single win here and it adds no surface.** Every option below assumes it goes.

## The pattern to steal

`LeaderboardPage` builds one sticky chrome block (`AppHeader`, the filter bar, `ColorsSwitcher`, `LeaderboardInsightsStrip`, then `LeaderboardColumnHeader`) and lets the table scroll under it with `stickyTop={chromeHeight}`, measured by a `ResizeObserver`. Secondary content is compressed into a two-cell strip *inside* the chrome that opens an overlay, instead of stacking above the list.

The parts are already exported and take a `variant="mobile"`: `LeaderboardColumnHeader`, and `LeaderboardTable` with `showHeader={false}` + `stickyTop`. `/pods` can adopt the sticky-chrome shape without touching either component. `StripToggle` is private to `LeaderboardSidebar.tsx` and would need lifting if an option wanted it.

---

In every wireframe below the left gutter is the y a block starts at, the number inside a row is that row's height in px, and `*` marks a pod champion.

## Option A: two tabs, one object at a time

```
0    ┌────────────────────────────────────────────┐
     │ ≡  LIMITED LEVEL-UPS | POD DRAFTS       56 │
56   ├────────────────────────────────────────────┤ ┐ sticky
     │ [ The Hobbit ▾ ]   [ HOB SEASON ▾ ]     49 │ │ chrome
105  ├─────────────────────┬──────────────────────┤ │ 178
     │ EVENTS        10    │  STANDINGS      38   │ │
141  ├─────────────────────┴──────────────────────┤ │
     │ #  PLAYER            TR  PODS  RECORD   26 │ ┘
167  │ 1  ELFANDOR [THE WASHED]  2   2    6-0  45 │
     │ 2  UNI                    1   4    7-2     │
     │ ... 13 rows to the fold, standings scroll  │
780  └ ─ ─ ─ ─ ─ ─ ─ ─ ─  fold   ─ ─ ─ ─ ─ ─ ─ ─ ─┘
```

Cheapest structural change: the two blocks stop coexisting, whichever is showing owns the whole scroll, and both keep their current internals. Costs: a tab pair is symmetric, so it says the two objects are peers, which is the thing the complaint objects to. The tab has to live in the URL or a set switch resets it. And EVENTS as the default tab means a first-time visitor never learns the page has standings unless they read the tab.

## Option B: standings collapse into a podium strip

```
0    ┌────────────────────────────────────────────┐
     │ ≡  LIMITED LEVEL-UPS | POD DRAFTS       56 │
56   ├────────────────────────────────────────────┤ ┐ sticky
     │ [ The Hobbit ▾ ]   [ HOB SEASON ▾ ]     49 │ │ chrome 152
105  ├────────────────────────────────────────────┤ │
     │ 1 ELFANDOR 2  2 UNI 1  3 PHLOX 1  38 ›  47 │ ┘ scrolls sideways
152  ├────────────────────────────────────────────┤
     │ AUG │ #24 CUBE AUG 14 EARLY POD DRAFT      │
     │  14 │ TEAM DRAFT        IN PROGRESS ›   68 │
     │ AUG │ #23 HOB AUG 13 LATE POD DRAFT        │
     │  13 │                     * UNI    ›    68 │
     │ ... all 10 events, 680px, own the scroll   │
780  └ ─ ─ ─ ─ ─ ─ ─ ─ ─  fold   ─ ─ ─ ─ ─ ─ ─ ─ ─┘
```

Events own the scroll outright and the standings compress to the leaderboard's own trick: a strip in the chrome, tapping through to the full table. Costs: the full table needs a home, either a new route (`/pods/HOB/standings`, a fourth slug shape on a route that already resolves seasons, boards, board windows and event slugs) or an overlay, and a 38-row sortable table in a 62vh overlay is a worse table than the one it replaces. The strip also has to say something on a board with one player.

## Option C: standings as a bottom sheet

```
0    ┌────────────────────────────────────────────┐
     │ chrome: header + set and window band   105 │
105  ├────────────────────────────────────────────┤
     │ events list, full height, owns the scroll  │
     │ ...                                        │
732  ├────────────────────────────────────────────┤
     │ ▲  SEASON STANDINGS         38 PLAYERS  48 │ fixed to the bottom
780  └────────────────────────────────────────────┘
```

Same division as B, but the standings stay one gesture away instead of one navigation, and the sheet can be full height so the table keeps its shape. `SwipeableDrawer` already exists. Costs: a persistently docked bar over a scrolling list is the heaviest chrome on the site and would be the only one of its kind; a sheet holding a sortable table has to solve nested scrolling; and it makes the standings feel like a utility panel on a page that is partly about them.

## Option D: events take the fold, standings take the scroll

```
0    ┌────────────────────────────────────────────┐
     │ ≡  LIMITED LEVEL-UPS | POD DRAFTS       56 │
56   ├────────────────────────────────────────────┤ ┐ sticky
     │ [ The Hobbit ▾ ]   [ HOB SEASON ▾ ]     49 │ ┘ chrome 105
105  ├────────────────────────────────────────────┤
     │ EVENTS                           10     29 │
     │ AUG 14 │ #24 CUBE EARLY  IN PROGRESS ›  48 │  ← live and upcoming first
     │ AUG 13 │ #23 HOB LATE POD    * UNI   ›  48 │
     │ AUG 12 │ #22 HOB EARLY POD   * PHLOX ›  48 │
     │ AUG  7 │ #21 PEASANT CUBE    * ARCYL ›  48 │
     │ ALL 10 EVENTS                      ›    36 │
362  ├────────────────────────────────────────────┤ ┐ pins under
     │ STANDINGS       38 PLAYERS, 10 EVENTS   29 │ │ the chrome
     │ #  PLAYER            TR  PODS  RECORD   26 │ ┘ at y=105
417  │ 1  ELFANDOR [THE WASHED]  2   2    6-0  45 │
     │ 2  UNI                    1   4    7-2     │
     │ ... 8 rows to the fold, then the scroll    │
780  └ ─ ─ ─ ─ ─ ─ ─ ─ ─  fold   ─ ─ ─ ─ ─ ─ ─ ─ ─┘
```

One page, no tabs, no new route, no overlay. The events list is finite and short, so it takes the fold: four rows plus every upcoming or live pod, then one line that expands the rest in place. The standings are long, so they take the scroll, and their heading and column header pin under the chrome the way the leaderboard's do, which is what stops a 38-row table from becoming an anonymous list halfway down.

First standing row moves from 512 to 417, and unlike today that number does not move when a tab is tapped. Costs: it does not give the events the scroll, so it reads the primary-object judgment as being about position and prominence instead of scroll ownership. See **The judgment, re-read**. It also needs one new piece of behaviour, the expand-in-place footer row, though that is strictly less than the tab state it deletes.

---

## The pick: D

A, B and C all hand the scroll to the events. That is the literal reading of "events are primary", and it costs more than it returns, because the events are the short object. Ten events at 48px are 480px, one fold. Thirty-eight players at 45px are 1710px. Giving the scroll to the list that ends after one screen means the list that does not ends up in an overlay, a sheet or behind a tab, and every one of those is a worse home for a sortable table than the page it is already on.

### The judgment, re-read

**Primary is about what the page opens on, not about what scrolls.** D gives the events the entire first screen under the chrome, complete, in date order, with the live and upcoming pods on top. Nothing about the standings competes for that space: their heading is the boundary of the fold, not a peer block above it. The standings then get what they need, which is length and a pinned header.

This is the one place this spec re-reads the brief, and it is the user's call to overrule. If the events must own the scroll, take A: it is honest about the tradeoff and costs the least of the three.

## Desktop follows the same model

Two columns stay, with three changes:

```
┌── HOB  THE HOBBIT  [ HOB SEASON ▾ ]     AUG 5 - SEP 15     [ set switcher ] ┐
├──────────────────────────────┬───────────────────────────────────────────────┤
│ EVENTS                  10   │ STANDINGS                          38 PLAYERS │
│ AUG 14 │ #24 CUBE EARLY  ›   │ RANK PLAYER     TROPHIES PODS RECORD  ← pins  │
│ AUG 13 │ #23 HOB LATE  ›     │ 1  ELFANDOR [THE WASHED]   2    2   6-0       │
│ ... 10 rows, ends at 1056    │ 2  UNI                     1    4   7-2       │
│                              │ ... 38 rows, own the page scroll              │
│    (the column simply ends)  │                                               │
└──────────────────────────────┴───────────────────────────────────────────────┘
            40%                                  60%
```

1. **Swap the columns.** Events left, standings right. The primary object reads first, and it matches the mobile order.
2. **40/60, not 50/50.** The events rows lose the expansion and carry a date, a title and a champion. The standings table carries six columns and wants the width.
3. **Pin the standings column header** with the same `stickyTop` the leaderboard passes, so 38 rows stay readable.

The hole under the shorter column stays. Two uncapped columns of different length always leave one, and the only fixes are a nested scroll or a cap, both worse. With the events on the left the hole sits under the object that visibly ended, which reads as finished instead of broken.

## Where feature 2 lands in this

D reserves the top of the events list for pods that have not happened yet, so `public_pod_slots` rows drop in above the played ones with a countdown and a JOIN link, and nothing about the layout has to move to accept them. That is the ordering argument for specifying 4 before building 2 rather than after.

## What changes, by file

All in `frontend/src/pages/PodDraftsPage.tsx` unless noted.

- Delete `EventStandings` and its deck-modal plumbing (`usePodDraftArtifact`, `usePodDecklistAccess`, `cycleDeck`, `DeckScreenshotModal`) from this page. `/pods/<slug>` already owns all of it. `PodStandingRow` stays imported by `PodStandings`, so nothing is orphaned.
- Delete `MobileEventsBlock`, `EventsTabButton`, `EventsTab` and `useRowDisclosure`. Rows stop expanding, so `EventRow` loses `open`, `onToggle` and `EventRowMeta`, and becomes a `Link` to `/pods/<slug>` on every kind of event except an upcoming one, which keeps its Discord CTA.
- Add the sticky chrome wrapper (`chromeRef` + `ResizeObserver`, copied from `LeaderboardPage`) around `AppHeader` and `MobileFilterBar`, and pass `stickyTop={chromeHeight}` plus `showHeader={false}` to `LeaderboardTable`, rendering `LeaderboardColumnHeader` next to the STANDINGS heading so both pin together.
- Add the digest cap: latest four played events plus all upcoming and in-progress, then an ALL N EVENTS row that flips a local `expanded` flag. Not a route, not a tab.
- Reorder the grid: `order-1` on events, `order-2` on standings, both mobile and `lg:`, and `lg:grid-cols-[2fr_3fr]` for the 40/60 split.
- `MockDraftsBlock` stays as it is, still last, still only on the MOCK axis or a board route.

Nothing here touches a view, a hook, an adapter or the scoring path.

## Not in question

Pod points stay per set (see **Decisions already made**), and a board window stays a URL. This is a layout question only: no view changes, no scoring changes.

---

# Build order

1. ~~**Standings.**~~ Shipped.
2. ~~**The `/pods` layout.**~~ Built 2026-08-14. Not option D: the tabs came back on the user's call, as **UPCOMING (default) and ALL**, with LAST EVENT demoted from a tab to a 40px link inside UPCOMING. Rows were rebuilt at leaderboard density instead (event row 68px to 52px, participant row 53px to 36px via `compact` on `PodStandingRow`), which paid for an expanded pod showing **all eight players** rather than four and a "+N MORE" line. Mobile carries the sticky chrome and pinned standings header; desktop pins nothing, matching the leaderboard. Standings sit left on desktop, and both grid sections carry `min-w-0` so the 3fr/2fr split stops drifting per board.
3. ~~**Upcoming pods.**~~ **Cut 2026-08-15, deliberately.** Built in full, then removed: `public_pod_slots` over open `pod_signals`, and `public_pod_schedule` projecting each slot's next run from its own history. Both worked. The reason they went is that every row's way in was the same Discord link the section's own CTA already carried, so the list cost a lot of mobile width and returned nothing the CTA did not. UPCOMING is now one **SIGN UP ON DISCORD** row pointing at `SITE_LINKS.discordPods`.

   Worth knowing if this is ever revisited:
   - **Never deep-link a Discord message from the site.** `discord.com/channels/<g>/<c>/<m>` is a dead end for anyone not already in the guild, and nothing on a public page can tell who is. An invite works for both audiences, and an invite created *in* a channel lands the joiner in that channel.
   - **Do not mirror the slot schedule in TypeScript.** Postgres can derive it from `pod_signals` history: the time-of-day per `slot_key`, the weekdays it runs, and the next occurrence. That found a `MORNING` slot nobody remembered and correctly dropped `EVENING`-on-Saturday once `SATURDAY_EVENING` replaced it. Rule that worked: keep a (slot_key, weekday) pair only if it ran the last time that weekday came around.
   - Two SQL traps cost real time: window functions cannot sit in `WHERE`, and `generate_series` with date bounds plus an interval step returns `timestamptz`, which silently inverts `AT TIME ZONE`. Cast the series back to `date`.
4. **The guide.** The only feature left. Specified 2026-08-15, not started. It is a copy and screenshot job, not a data one: no views, no migrations, no bot changes, and one deletion outside `frontend/`.
5. ~~**Polish the `/pods` UI.**~~ Shipped in `6808f0d1`.

# Where the UI stands, 2026-08-15

Shipped in `6808f0d1`. Bot untouched, no migrations, frontend only.

Landed this session: two-tab mobile block (UPCOMING default, PAST EVENTS), expansions showing the full field with no "+N MORE" line, `compact` on `PodStandingRow`, breakdown moved from a dead footer into the row header (desktop only), team drafts showing the winning three with a per-seat colour ring instead of a champion, `orderedDeckColors` putting mains before splashes, `podSlotName` no longer appending "Draft" and stripping a mid-name date, sticky mobile chrome, own-row highlight, and `min-w-0` on both desktop grid sections.

Landed later the same day, the polish pass. All four rough points are closed.

- **Desktop rows are 52px, the same as mobile.** `DateRail` lost its `md:` step-up and runs one size everywhere: 56px wide, month 11px, day 16px. `EventRowSkeleton` and `MockEventRow` follow. `MockEventRow` also drops its oversized `ChamferedButton` for the same details link every other row carries.
- **`EventDetailsLink` is icon-only, with the label in a tooltip.** The events column is the narrow one at `3fr_2fr`, and a repeated `BREAKDOWN →` button cost about 130px of it on every row. Reclaiming that is what lets a title render in full and a champion name stop truncating.
- **A one-line mobile row replaces the date rail.** `EventRow`, `EventRowBody` and `MockEventRow` take `stacked`, set wherever `isMobile` already decides the layout. The identity leads, the outcome sits beside it, and `DateStamp` closes the line with the date alone, in the display face at 13px. Rows come out at 52px.
- **A pod with no champion reads as running, so no row says IN PROGRESS.** `RoundLabel` replaced it and prints only when a round number is actually known.
- **A stacked team draft names the format and nothing else.** Three seats with avatars and pips crowded the title out entirely, and passing `undefined` to `usePodEventParticipants` when stacked also spares a query per row. The sides stay in the expansion.
- **The mobile tab bar is the section heading.** UPCOMING was printing twice, once as a tab and once as a heading over the CTA. The heading is gone and the tabs run at the heading's own 14px, so the column reads UPCOMING | PAST EVENTS, then the CTA, then LAST EVENT, then STANDINGS.
- **SIGN UP ON DISCORD reads as a CTA**: green on `bg-green/10` with a `border-green/30`, 52px tall.
- **The expansion carries `BreakdownFooterLink`.** That is the phone's route to `/pods/<slug>`, and LAST EVENT now expands like every other row instead of being the one row that navigated.
- **`stacked` replaced `lg:` on every affordance that was really about layout mode.** `useIsMobile(POD_DESKTOP_WIDTH)` is 900 and Tailwind's `lg:` is 1024, so between them the desktop rows rendered with no breakdown link, no champion avatar and no team pips. Anything keyed to which layout is running now reads the prop, and `lg:` is left to real width work.
- Section-heading normalisation took: UPCOMING, LAST EVENT and STANDINGS all read at one level on mobile.

The desktop UPCOMING heading carries the slot times in prose, and `POD_SLOTS` in `PodDraftsPage.tsx` holds the two Eastern hours. That is a narrow exception to "do not mirror the slot schedule in TypeScript" under build order 3: it is one static sentence of copy, not a derived calendar, and it drops Saturday's later late pod rather than encode the exception. If the sentence ever needs to be right about which slots actually run, derive it from `pod_signals` as that note describes.

## Open, found during the pass

~~**Committed upcoming pods stopped rendering.**~~ Closed. The product call went to dropping them: a pod that has not started has no result to show, and UPCOMING is the Discord CTA. `EventRow`'s countdown and join branches went with it.

**Mock rows were not eyeballed.** Still true. Every mock event in prod is HOB-coded and dated inside the MSH window, and MSH has no pod events, so it is not a listed season and no route reaches them. `MockDraftsBlock` is still gated on `kind === "mock"` reaching a board route, so `MockEventRow` compiles and matches `EventRow`'s shape but nothing has rendered it.

# Out of scope

Anything that moves pod points onto a set's leaderboard. That was decided against and the reasoning is in **Decisions already made**.

---

# Starting a session on this

Paste as the opening message. Swap the named feature to pick a different one; the rest holds either way.

> Continue the pods-on-the-site work. Read `spec/pods-on-the-site.md` first: it carries the remaining features, the decisions already made, and the build order. It is uncommitted, so it exists only in the working tree.
>
> Start with **feature 1, the pod guide at `/pods/guide`**. It is the only feature left. Read its section for the decisions, the structure, the copy rules and the screenshot list. It is a copy and screenshot job: no migrations, no views, no bot changes.
>
> Context that is not in the repo:
> - The guide replaces `docs/guide/pod-coordination.md`, which gets deleted. Do not port its prose. It is source material for what is true, never for how to say it.
> - The copy rule is the feature. Short sentences, one idea each, second person, no em dashes, nothing explained that a screenshot already shows. Detail goes behind collapsibles.
> - Screenshots are real and cropped, captured from the test server through the `!test` commands listed in the spec, saved under `frontend/public/guide/`.
> - Pod seasons shipped in `30bf0c00`. `/pods` is season-framed, Peasant is a board at `/pods/PEASANT` and `/pods/PEASANT-<SET>`, and the pod standings carry points and rank on them.
> - Pod points stay attributed per `set_code`, decided deliberately: a set's leaderboard means people drafting that set. Do not propose moving them onto seasons.
> - Cube and pod windows are declared in `cube_variants.json`, never inferred from draft activity. If a run is missing, get its dates from `bot/services/scribe_calendar.json` or the announcement.
> - Feature 3 shipped: the standings tab on `/pods/<slug>`, plus migration `c3e5a7b9d1f4` on the participants view. Tiebreaker percentages were ruled out for the site, so nothing persists them.
> - Feature 2 was built and then cut on purpose. Do not rebuild the upcoming-pods list. UPCOMING is one CTA row and that is the decision.
> - The site never writes pod state and never deep-links a Discord message. Every way in is `SITE_LINKS.discordPods`.
>
> The spec stays uncommitted on purpose. Update it as decisions land, but do not commit it.
