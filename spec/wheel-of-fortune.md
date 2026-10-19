# Wheel of Fortune

A daily mini game on limitedlevelups.com built from finished Pod drafts. The player sees the first pack of a Pod at pack 1, pick 1, ranks the eight cards they think the table took first, and calls the rest as the wheel. Shipped 2026-10-18 together with Trophy Mage, merged into master in 7afd8182.

This doc records what was built and the decisions behind it. For how it works today, read the code it points to.

## The game

- **One pack per round, pack 1 only.** The pack is the opener's first booster in a finished Pod with 6 to 8 players. Later packs were left out on purpose: pack 1 is the only one every player can reason about without knowing the table's colors.
- **The player orders 8 picks.** The cards left out are their wheel guess.
- **Scoring:** +1 per correct wheel card, +3 for naming the exact first pick. Picks 2 to 8 score nothing; their order only matters for which cards are left out. Constants live in `data/draftGames.ts` as `WHEEL_CARD_POINTS` and `FIRST_PICK_POINTS`.
- **A pack has 14 or 15 cards** depending on the format. Duplicate copies of a card in one booster each get their own index through `separateCopies` in `buildWheelPack`, so picking one copy only removes that copy from the wheel.

## Modes

- **Today's packs.** Three packs a day, the same for everyone: the latest set, Peasant Cube, then a flashback set picked by the day's seed from the other eligible sets. Three was chosen to echo the three packs of a draft and Trophy Mage's three decks. Days turn over at 10 AM Eastern, matching the bot's daily launcher. Progress is saved in the browser per day.
- **Yesterday.** The home carousel holds yesterday's packs to the left of today's. Only one past day is offered; Quick Mode fills the "something else to play" role that Trophy Mage gives to a second past day.
- **Next and Endless.** Once today is finished, the main button reads Next and opens the next unfinished open day, with a Results button beside it. When every open day is done it reads Endless and opens Free Play on the newest set. The Results screen's Next follows the same rule. This mirrors Trophy Mage and fixes the earlier dead end where a finished day left no way to reach other days.
- **Free Play.** Endless packs from one set, or all sets. It has no mode name in the header; the title is the set and pack number.
- **Quick Mode.** A shorter game added after playtest feedback: three cards from one pack, guess which one wheeled. Normal mixes an early pick and a late pick with the wheeled card; Hard uses two late picks. Basic lands and wheeled cards graded D or F by 17lands are skipped so every round has a fair answer. Best streak is kept per difficulty. The streak number changes color by tier, topping out at 7, which the user set as the point where a streak is already remarkable.

## Stable pack numbers

Every Pod gets a number within its set, oldest first, so "Reality Fracture Pack #40" means one specific booster for every player. `/wheel-of-fortune/fra/40` opens it directly. Both Free Play and today's packs build the booster from a seed derived from the Pod id, `podSeed`, so a number shows the same opener seat in every mode. Today's packs show the same number in their title. The point is that players can talk about a pack by its number across accounts. Plain `/wheel-of-fortune/fra` starts at a random pack and updates the address to its number.

## Routes

- `/wheel-of-fortune`: home
- `/wheel-of-fortune/<YYYY-MM-DD>`: a day's packs
- `/wheel-of-fortune/<set>` and `/wheel-of-fortune/<set>/<number>`: Free Play
- `/wheel-of-fortune/quick`: Quick Mode

Old `?play=` links redirect. Every Wheel path unfurls on Discord with the pixel wheel card from `functions/_middleware.ts`.

## Look and feel decisions

- **Pixel game style** shared with Trophy Mage through `components/draftGames/pixelStyles.ts`: pixel wordmark with an animated wheel sprite, gold buttons, dark panels, the faint wheel art backdrop. No prominent AI art.
- **Everything fits one screen** with no page scroll at desktop 1854×929, laptops 1366×657 and 1200×959, and phones 390×844 and 375×667. The card grid picks its column count from the space available; the sidebar shrinks its spacing on short screens. The exception is the phone game screen, where the card grid scrolls behind a docked bottom panel.
- **Reveal language.** A right call turns green with a check. A wrong call extends an arrow to the actual result in red. Gold means points only. A correct first pick gets a raised +3 badge. After Confirm, cards dim and light up in the order they were picked, wheel cards last, in about 1.5s for a pack. Revisiting a confirmed pack shows the result still, with no replayed animation.
- **Loading.** No forced delay. Cards render as soon as their pack is known and cross-fade in a snake order: row 1 left to right, row 2 right to left. A clockwise spiral was tried and rejected as confusing. The next pack's art downloads in the background while the current one is played, so Next Pack is near instant. When the format changes between packs the grid clears first, which hides the change from 14 to 15 cards. The home draws its pack layout from the first frame and caches the day's sets in the browser so a return visit is instant; the deal animation plays once and never replays when data arrives.
- **Card name strips** in the order list are crops of the card image, framed to show the title bar with a thin band of frame. Double-faced and split cards use Scryfall's layout, which `/api/card-images` now returns next to each image URL.
- **Results screen** mirrors Trophy Mage's recap: one row per pack with the set icon, the actual first pick with your call, the wheel cards with your correct calls lit, and points. The row is symmetric so Menu and Next line up under the two images. Opening a pack from Results adds a history entry, so the browser Back button returns to Results.
- **Copy rules.** Title Case for buttons and headings, no em dashes, plain words, and no "real" in game copy. Peasant Cube reads CUBE on the home and Peasant elsewhere, by choice.

## Deliberately left out

- **Share to Discord.** Deferred until after release, and only if players ask. The recommended start is a result link that unfurls with the score.
- **Replay Today stays** on today's packs until sharing exists, since with no shared results there is nothing to protect.
- **Accounts and leaderboards.** Progress lives in the browser. Saving plays needs a decision on how the site writes data, since today only the bot writes to the database.
- **Battle cards** still show a plain color bar in the order list instead of a cropped title.

## Where things live

- `pages/WheelOfFortunePage.tsx`: routing, the daily game and Free Play
- `pages/WheelQuickPage.tsx`: Quick Mode
- `components/draftGames/wheel/`: intro, pack grid, order panel, header, results and guides
- `data/draftGames.ts`: pack building, daily selection, numbering and scoring
- `data/cardImages.ts` and `functions/api/card-images.ts`: card art and layouts

 Open follow-ups for both games are tracked in `spec/mini-games-roadmap.html`.
