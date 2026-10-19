# Trophy Mage

How the game works today. Read the code for details; this is the map. The original build brief is in `spec/archive/trophy-mage-build-brief.md`.

## The game

Each round shows 3 decks from one Pod. The player picks the deck that went 3-0, then can place the other two as 2-1, 1-2 or 0-3. A right 3-0 call is 2 points and each right record 1, so a round is out of 4 and a day out of 12. Endless plays Pods of one set with no daily limit and keeps a running total.

## Where things live

- **Page and routes:** `frontend/src/pages/TrophyMageLabPage.tsx`, routed in `App.tsx` at `/trophy-mage` and `/trophy-mage/:play`
- **Game components:** `frontend/src/components/draftGames/trophy/`. `TrophyIntro` and `TrophyShelf` are home, `TrophyGame` is a round, `TrophyRecap` is the day's results, `DeckViewer` is the full-screen deck
- **Data and rules:** `frontend/src/data/trophyMage.ts`: the daily deal, round building and scoring. Tests sit next to it in `trophyMage.test.ts`
- **Shared with Wheel of Fortune:** `frontend/src/data/draftGames.ts` (day keys, the Pod list, `featuredSlots`, `clearSavedDaysOnRequest`) and `components/draftGames/` (`pixelStyles.ts`, `GameChrome.tsx`, `GameDialog.tsx`)
- **Link previews:** `functions/_middleware.ts` serves `public/games/trophy-mage/og-image.gif`, rebuilt by `frontend/scripts/pixel-art/build_og_gifs.py`
- **Pixel art sources:** `frontend/scripts/pixel-art/trophy-mage/`

## Rules that are easy to break

- **The day is dealt from its date.** Each day is the latest set, then Peasant Cube, then a flashback set, seeded by the date so every player gets the same Pods. Latest set Pods must be at least a week older than the day. Changing the deal reshuffles past days.
- **Saved progress belongs to specific Pods.** It lives in localStorage per day under `trophy-mage-daily:<date>`, keyed by Pod. A changed deal leaves old saves pointing at Pods the day no longer shows.
- **The game day starts at 10 AM Eastern,** the bot's daily launcher time. Home shows today plus the two days before.
- **A Pod is playable** when it is a finalized 6 to 8 player tournament with a 3-0 deck and at least two other decks that have a record and a screenshot. Each slot carries 4 candidate Pods in case one is not playable.

## Reaching any state

- `/trophy-mage/<YYYY-MM-DD>` plays a day; a future date redirects to today
- `/trophy-mage/<set>` is Endless for that set, lowercase code
- `?round=N` starts an unfinished day at round N, `?review=N` reviews round N of a finished day, `?results=1` opens the recap. Rounds count from 1
- `?reset` clears every saved Trophy Mage day, on the live site too

## Styling traps

- `cn()` drops a `leading-*` class when a later `text-*` size sets its own line height. Use `text-lg/none` style sizes.
- The empty shelf plaque uses a non-breaking space, which the Edit tool cannot match; edit around that line.
