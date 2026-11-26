# Daily Sealed

A daily practice Sealed on limitedlevelups.com. Every morning everyone gets the same Sealed pool, builds a 40-card deck on the site and submits it. After submitting, a player sees what the community built and how the player who opened the pool did. The bot posts the new pool and yesterday's results on Discord. It gives players practice builds ahead of big Sealed events and something new waiting every morning.

Status: built end to end on master, uncommitted. The site lives at `/daily-sealed` and `/daily-sealed/<YYYY-MM-DD>`. The builder and the Discord post are reviewed; the Card Breakdown is built.

## Decisions so far

- **Daily, never spaced out.** A new pool every day at 8 AM Eastern, the same turnover as Wheel of Fortune and Trophy Mage. A pool every few days is too arbitrary to build a habit around.
- **Real pools from LLU players.** The pool is the full pool of a finished Sealed event an LLU player played on Arena, pulled from 17lands. It is not generated. A real pool comes with a real outcome to compare against.
- **Active set only.** Pools come only from the set Arena is currently on. During Star Trek season every pool is Star Trek, and older sets are never picked. At rotation the daily switches to the new set.
- **The new set from the morning after release.** Arena releases at noon Eastern, four hours after the 8 AM turnover, so release day still serves the outgoing set. The next morning's pool is picked from about 17 hours of new-set data. Star Trek had about 50 finished Sealed events on its release day, so that is enough.
- **Past days stay open.** Players can browse earlier pools and builds. A set filter comes later.
- **Anonymous reveal.** After submitting, a player sees the original player's colors and record, without their name.
- **Any Discord login can submit.** No linked LLU player account needed.
- **Builds are public and anonymous.** Anyone can browse a past day's builds, and none shows who made it.
- **Lives under Tools** next to the mini games.
- **Voting on the best build is a later extension.**

## Pool supply

Prod on 2026-11-24 holds 815 finished Star Trek Sealed events from 125 players three weeks into the set. The four sets before it ended with 1,300 to 2,400 each, which shows what a full season supplies. That counts Sealed, Trad Sealed, Arena Direct, Qualifier Play-In and Qualifier events. Midweek Sealed is left out.

`draft_events` stores no pools. The tracker's `/api/deck/draft/?draft_id=<id>&deck_index=0` call in `bot/services/tracker_detail.py` returns the main deck and sideboard, which together are the whole Sealed pool. A live Star Trek check returned 29 nonbasic main deck cards plus a 52-card sideboard. The few basics from the land slot cannot be told apart from added basics, which does not matter since the builder offers unlimited basics. The same response carries the original colors, wins and losses and per-card details.

## Picking a pool

The refresh-cron Railway service picks the pool, since it already calls 17lands on a schedule. It fetches the pool server-side because 17lands sends no CORS headers and stores it. The pick happens at the end of the 09:00 UTC run, right after its 17lands sync. The set is the one active at the coming turnover.

The cron runs at 01, 05, 09, 13, 17 and 21 UTC, and on 2026-11-24 a run took about 46 minutes for 390 players at 7 seconds each. The 09:00 UTC run ends around 09:46 UTC, which is 4:46 AM Eastern in winter. Turnover at 8 AM Eastern is 13:00 UTC in winter and 12:00 UTC in summer, so the pick has more than 2 hours of slack, enough for about 1,500 players. Only a run that ends within 5 hours of turnover picks the next day, so the 05:00 UTC run never takes it even when it ends after 06:00 UTC in summer. The pool only misses events that finish between about 5 and 8 AM Eastern, the quietest stretch of the day. The later 13:00 UTC run starts at or after turnover, so it only serves as the fallback. On the morning after a release the pick sees about 17 hours of new-set data, since Arena releases at noon Eastern. If the 09:00 UTC run fails, the 13:00 UTC run picks the pool within an hour or two of turnover and the Discord post waits for it. Storing it freezes the day: later 17lands changes never alter a pool people already built.

Selection rules:

- The active set from `active_set_code()`, never an older set.
- Finished events only, so nobody sees a pool someone is still playing.
- Skip Midweek Sealed events.
- Never a pool that was already served. The source `draft_events` id is unique on `daily_sealed_pools`.
- Never the same player as the day before.
- One pool per player per set before any player repeats, so the dailies spread across the community.
- Never pick by record. A pool drawn from trophy decks would give away that it is strong.
- If the fetch fails or returns too few cards, try the next candidate.

## Data model

Two new tables, both needing sign-off:

- `daily_sealed_pools`: one row per day. Day key, set code, source `draft_events` id, the pool's card list with the per-card fields the builder sorts by, the original colors and record. Readable by everyone through a `public_*` view that leaves out the source event id and player so the reveal stays anonymous.
- `daily_sealed_builds`: one row per user per day. Main deck card list and basics. Written from the browser by the signed-in user with RLS on `auth.uid() = user_id`, the same pattern as `fantasy_picks` in `f4n7a5y1w0c1_fantasy_worlds.py`. A player can change their build until the day turns over.

A `public_daily_sealed_builds` view exposes every build of a visible day with an anonymous key, and the site aggregates them in `breakdown()` in `data/dailySealed.ts`. Builds are tagged with colors the same way 17lands encodes them, so splashes show.

## The site

- **Builder:** our own, held to sealeddeck.tech's usability. See Deck builder below.
- **Submit:** needs Discord login. Without login the builder still works, but the build is not saved and does not count.
- **Card Breakdown:** unlocks after submitting, and opens first on past days. Before submitting it doesn't show, so it can't steer a build. On desktop it is its own full-width mode switched from the header, built from the same panels, panes and piles as Build in `components/dailySealed/Breakdown.tsx`. It has tabs for On-Color and Played rates, Split, Splashes, You and Decks, and a sidebar with the original build, colors and insights.
- **Past days:** earlier pools with their final breakdown and the submitted builds, newest first. Yesterday is the one the Discord post links. A set filter is added once more than one set has pools.
- **Sharing:** every pool has a stable link that keeps working after its day ends, keyed by date like Wheel of Fortune's `/wheel-of-fortune/<YYYY-MM-DD>`. A Copy Link button sits next to the pool. The link unfurls on Discord with a pool-specific image and title through `functions/_middleware.ts`, the way the other games unfurl.

## Deck builder

We build our own builder. sealeddeck.tech and Draftmancer both allow framing, but neither can hand a finished build back to our page, and a paste-your-link step would lose players every day. sealeddeck.tech is the usability bar: a player who builds there should find everything they use in ours, on desktop and on a phone. The feature list below comes from sealeddeck.tech's own UI.

### Zones

- **Deck** and **Sideboard**, with the whole pool starting in the Sideboard.
- **Hidden**, for cards a player has ruled out. On desktop it is a toggle chip in the Sideboard header, closed by default, that opens a resizable panel at the Sideboard's right; the chip also takes drops while closed. On the phone it is a Show hidden toggle on the Pool tab.

### Moving cards

- Free piles like sealeddeck.tech: Sort By Mana Value, Color or Rarity rearranges a zone once, and after that cards stay exactly where they are dropped. The layout is rows of piles of ordered cards in `data/dailySealedLayout.ts`, saved per day in the browser.
- Dragging uses `@dnd-kit` only for the pointer sensor, the drag ghost and edge auto-scroll. The drop target comes from `components/dailySealed/pileHitTest.ts`: the column from the pointer's x, with each gap split between its neighbours, and the slot from its y counted down from the pile's top, so targets stay put while cards shift. Past the last column makes a new pile. Dropping outside both panes puts the card back.
- The dragged card never tilts and stays exactly where it was grabbed, moving with the pointer. The drop target comes from the card itself, its title row for the slot and its center for the column, so a card grabbed anywhere drops where its title points. The Hidden chip and panel take a drop wherever the pointer is. Cards that change slot during a drag glide into place. Card size is frozen for the length of a drag, and auto-scroll only runs in the pane under the pointer.
- Drag a whole pile by its header; with a filter on, only the visible cards move.
- Click or tap a card to send it to the other zone, into the pile matching that zone's last sort. This is the main way on a phone.
- Undo for the last move, plus Reset.

### Layout

The page is `pages/DailySealedPage.tsx`, with its pieces in `components/dailySealed/`. While the pool loads, `BuilderSkeleton.tsx` draws the same layout with placeholders.

Desktop fills the screen with no page scroll and no site header:

- A 48px header with the logo, set, pool, day arrows, the countdown, the Build and Card Breakdown tabs, then Undo, Reset, the deck count against 40, Copy Link, Export for Arena and Submit.
- A left panel sized to its widest filter row, with the Sideboard filters, the basic land counters and the deck stats, then the Sideboard over the Deck, flush panels with single dividing lines. The Deck header is the pod draft log's panel bar from `components/pod/review/resizablePanel.tsx`: drag it to resize the Deck, click it to collapse or expand, both remembered in the browser.
- Pile headers show the count centered with a symbol right after it: the land symbol for the lands pile, a color pip for Color, the set's rarity symbol for Rarity, and nothing for mana values. The symbol only shows while every card in the pile, filtered or not, belongs to that group, so a pile mixed by dragging shows just its count. Empty piles keep their space with a blank header. While filtering, the Sideboard header shows the total struck through and the filtered count.
- Card width fits at least 7 columns across, 118 to 220px. Hover follows the pod draft log's `StackColumn`, and stacked cards under 140px wide drop their shadow through `stackedCardShadow` in `ReviewCard.tsx`.
- Mana Value piles put lands first. A sort makes piles only for the cards in that zone, and an emptied pile is removed, so neither panel shows blank columns. Basics get a lands column whenever any are in the deck.
- Separate noncreatures in the Deck header puts creatures and noncreatures in two rows.
- Right-click opens a card modal with Prev and Next and arrow keys, stepping in the order the cards show where it was opened.

The phone keeps the site header and is built for density:

- A sticky row with the set glyph, Pool and Deck tabs with their counts, and Copy Link and Export as icon buttons.
- The Pool tab has colors, rarities and the Hidden, Filters and full-card buttons on one row, then a full-card grid grouped by color or name strips, defaulting to the grid, the choice saved. A count line with the struck total shows only while filtering.
- The Deck tab shows the summary, basic counters, Auto-fill lands, the Split creatures toggle and a grid toggle, then the same piles as the desktop Deck, defaulting to card piles over name strips.
- A pinned bottom bar holds the count, Undo and Submit. Tapping a strip moves the card; long-press opens the card modal.

### Feedback

Copy Link and Export for Arena confirm on the button itself through `useCopyFeedback` in `components/CopyTextButton.tsx`, the site's existing copy pattern. Submit results and errors show as a dark notice card with a green or red border, centered below the header on desktop and above the bottom bar on the phone.

### Card ratings

- A toggle shows 17lands GIH WR on each card, off by default, like sealeddeck.tech: stacked cards grow a second row under the title with the rating as a percentage at the left. The full-card grid shows it in the same spot and the phone name strips show it just left of the mana cost. Ratings come from our `/api/card-stats`.

### Sideboard filters

- Color: the five colors plus Colorless. A card shows when it has any selected color, and colorless cards show only when Colorless is selected. The phone's quick row adds Colorless on screens 420px and wider, where it fits on one row; it is always in the Filters sheet.
- Rarity, with the GIH WR ratings toggle on the same row.
- Type: the tier list's groups from `TYPE_GROUPS`, with Instant, Sorcery, Artifact and Enchantment split out. Planeswalker and Battle only appear when the pool has one. Multi-select.
- Text search over name and type line. 17lands sends no rules text with the pool.

### Basic lands

- Plus and minus counters per basic land type.
- Auto-fill lands aims for 17 lands in total, counting the nonbasic lands already in the deck, and splits the basics by the colored pips on the deck's nonland cards. It rebuilds the basics each time.
- Basics also show in the Deck's lands column as one card per type with an xN count in the mtg-draft-logger style; clicking one removes one. The art is the set's basics through `/api/card-images`.

### Deck stats

- A card count against 40, shown at all times and colored when the deck is short or over.
- Mana curve split into creatures and noncreatures.
- Pips by color next to mana sources by color, so a weak splash is visible.
- Creature count.

### Saving and export

- The in-progress build saves in the browser on every move, so a reload or a closed tab loses nothing. It saves to the account on Submit.
- Export for Arena copies the deck in Arena's import format. A daily practice build is meant to be played afterwards.
- Submit unlocks at 40 cards or more. A submitted build can be changed until turnover.

### Bar for done

Each item above is checked on a desktop and on a phone against the same pool loaded in sealeddeck.tech, and a pool turns into a 40-card deck in about as many clicks as there.

## Discord

A bot task in `bot/tasks/daily_sealed_post.py` posts at turnover in the latest set channel, which `latest_set_channel` in `bot/services/format_schedule.py` finds. The post text is built in `bot/services/daily_sealed_post.py`: a header pinging the Daily Sealed role with the set code and pool number, the build link, then a Yesterday line with the original player's event, record and colors, linked to yesterday's pool, and a Builds line with up to three color combinations and their counts in the pod draft color emojis. Lines with nothing to show are left out. Pool numbers count per set, so the first pool at launch is #1.

A Notify me button on every post toggles the Daily Sealed role and answers with the pod drafts' Added and Removed replies. `!test dailysealed` previews the post, and it is allowed on the production server.

## Rules the build chose

These came out of the build and are open to change:

- A build's colors use 17lands' encoding. A color on three or more nonland cards is a main color and one on one or two cards is a splash, written lowercase.
- Auto-fill lands hands out leftover lands by the largest remainder, so ties go to the first color in WUBRG order.
- Builds are saved by card position in the pool, so two copies of the same card stay separate.
- The Discord post retries every 30 minutes from 8 AM to 12:30 PM Eastern until today's pool exists, and posts once a day.

## Later

- Voting on the best build among a few submitted builds.
- A set filter on past days.
- A streak for submitting on consecutive days.
- Comparing your build to the original player's deck, which 17lands also returns.
