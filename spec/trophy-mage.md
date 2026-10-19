# Trophy Mage spec (2026-10-17)

## Startup prompt

Paste this into a new Claude Code session:

> Read `/home/mnoya/Projects/Personal/DischordLeaderboard/spec/trophy-mage.md` and `/home/mnoya/Projects/Personal/DischordLeaderboard-draft-games/review/HANDOFF.md`. We're building Trophy Mage, the second LLU minigame, next to Wheel of Fortune. Work in the worktree `/home/mnoya/Projects/Personal/DischordLeaderboard-draft-games` (branch `draft-games`, nothing committed), because the pixel-art styles and game chrome it reuses only exist there uncommitted. Another session is polishing Wheel of Fortune in the same worktree at the same time, so follow the file ownership rules in the spec. Run your own dev server on port 5189. Your first job is exploration: build the variations listed in the spec behind a `?v=` switcher, take screenshots at desktop, laptop and phone, run a critique round, and hand me URLs so I can pick a direction. Don't commit, don't push, and ask before any change to a shared file.

## The game

One Pod, three or four decks on screen. Exactly one of them went 3-0. The player picks the trophy deck. Bonus points for placing the rest: which deck went 2-1, 1-2 or 0-3.

- **Data per round:** one finalized Pod draft. Show the 3-0 deck plus two or three others, ideally one per remaining record so every guess has a single right answer. In an 8-player Pod with three Swiss rounds the records split 1 × 3-0, 3 × 2-1, 3 × 1-2, 1 × 0-3, so a four-deck round can show one of each.
- **Daily rounds:** a fixed set of rounds per day, the same for everyone, like Wheel of Fortune's Today's Packs. Saved in localStorage per day.
- **A second mode for more rounds:** the Wheel's "Free Play" equivalent. Its name is still open on the Wheel side too, so keep the label in one constant.
- **Scoring (placeholder, not agreed):** a point for the trophy, smaller bonuses for each correct record. Keep the numbers in named constants like the Wheel's `FIRST_PICK_POINTS`, show points in a side panel or summary and never on top of the decks.
- **Reveal:** follow the Wheel's reveal language. A right call turns green with a check in place. A wrong call extends an arrow and the real result in red, like "2-1 → 0-3". A correct trophy pick gets the most gratifying treatment on screen.

## What already exists

- **Old page:** `frontend/src/pages/TrophyMagePage.tsx` at `/tools/trophy-mage`. It uses the old non-pixel look and `GameChrome` components.
- **Data:** `useTrophyRounds(setCode, seed)` and `trophyRound()` in `frontend/src/data/draftGames.ts`. A round is 1 trophy deck plus 3 others, from Pod participants with a `deckScreenshotUrl` and a `record`. Type `TrophyDeck` has `displayName`, `record` and `deckScreenshotUrl`. It only uses the active set today.
- **Decklists:** besides screenshots, the Pod draft artifact (`fetchPodDraftArtifact`, `public_pod_draft_log`) carries `decks[seat].main`, real card lists. A variation can render decks from card data: a curve, colors, key cards. That avoids depending on screenshots, which not every player uploads.
- **Shared look, reuse it:**
  - `frontend/src/components/draftGames/pixelStyles.ts`: `GOLD_BUTTON`, `DARK_PIXEL_BUTTON`, `PIXEL_PANEL`, `PIXEL_TAG`, `PIXEL_WELL`, `PIXEL_HEADING`, `HARD_TEXT_SHADOW`.
  - Wheel components to learn from: `wheel/WheelIntro.tsx` (intro with title, premise row, carousel), `wheel/WheelTitle.tsx` (pixel wordmark with an animated sprite as a letter), `wheel/WheelEmoji.tsx` (sprite strip with spin physics), `wheel/WheelBackdrop.tsx` (faint drifting card art under the page), `wheel/WheelHelp.tsx` (How to Play dialog), `wheel/PackGrid.tsx` (reveal chips).
  - Pixel art is generated with claude-pxl, cloned at `/tmp/claude-pxl`. Recreate it if `/tmp` was wiped: the Wheel's sources are `review/wheel-ambient/wheel-emoji.px.js` and `wheel-title.px.js`.

## Visual direction

- **Pixel-art vibe:** the same as Wheel of Fortune: hard 2 to 5px shadows, square corners, `#1a120b` borders, gold `#f6c95e` accents, the display font for headings.
- **Wordmark:** a pixel "TROPHY MAGE" wordmark. The idea to explore is a pixel trophy standing in for the "Y" in TROPHY, the way the spinning wheel is the "o" in Wheel of Fortune.
- **Flavor art candidates:**
  - Trophy Mage card: https://cards.scryfall.io/display/front/5/2/5252794a-5cbe-45e3-b5c1-b27c667e9c17.webp?1783935075 . The user is unsure about using this card itself.
  - Trophy Mage full art: https://www.artofmtg.com/wp-content/uploads/2017/01/Trophy-Mage-Aether-Revolt-MtG-Art.jpg
  - Trophy Mage extended art, a backdrop candidate: https://tcgplayer-cdn.tcgplayer.com/product/125843_in_1000x1000.jpg
  - Pondering Mage, a mage holding three orbs, a pixel sprite candidate: https://cards.scryfall.io/display/front/c/0/c08c5ac8-5c0b-4c89-8f06-e5aadfccee01.webp?1783933139 , based on https://cards.scryfall.io/display/front/9/c/9cee2eb1-f60e-4626-ba4a-b543142ca950.webp?1783927563
- **Art rules:** original card art as a faint backdrop is approved, as on the Wheel. Don't use AI art prominently. Ask before downloading any image into the repo, and crop away card frames so they can never show.

## Variations to build first

Build these behind `?v=a`, `b`, `c`, and so on, all at `/trophy-mage` (a new route; leave `/tools/trophy-mage` alone until the user decides). For each one: screenshots at 1854×929, 1366×657 and 390×844, a critique list, and a URL.

1. **Intro:** two or three takes on the title screen. Wordmark with a trophy "Y", premise line ("Pack 1 Pick 1"-style tag plus a one-line question), How to Play button, today's rounds, and a way into the second mode. Reuse the Wheel intro's structure where it fits.
2. **Round layout:** how three or four decks sit on one screen with no page scroll on desktop:
   - deck screenshots side by side
   - decks rendered from card data, with curve, colors and top cards
   - a stacked, swipeable deck view for phones
3. **Making the calls:** how the player picks the trophy and assigns the other records:
   - tap a deck to crown it, then drag record tags onto the rest
   - assign 3-0, 2-1, 1-2, 0-3 like the Wheel's ordered picks
   - crown only, with records as an optional second step
4. **Reveal:** the chip language from the Wheel ("3-0 ✓", "2-1 → 0-3") plus a trophy moment for a correct crown.
5. **Mascot sprite:** a pixel trophy, and a Pondering-Mage-style figure juggling three orbs, as animated sprite strips like `wheel-emoji.png`.

## File ownership while both sessions run

- **Trophy Mage owns:** `pages/TrophyMagePage.tsx` and any new `pages/TrophyMage*.tsx`, `components/draftGames/trophy/**`, `public/games/trophy-mage/**`, `review/trophy-*`.
- **Ask first before touching:** `data/draftGames.ts` (add Trophy Mage hooks in a new `data/trophyMage.ts` instead), `components/draftGames/pixelStyles.ts`, `components/draftGames/GameChrome.tsx`, `App.tsx` (one new route line is fine, say so in the reply), `functions/_middleware.ts`, `tailwind.config.ts`.
- **Don't edit:** anything under `components/draftGames/wheel/`, `pages/WheelOfFortunePage.tsx`, `pages/WheelRevealMockupsPage.tsx`. Import from them freely.

## House rules (from the user)

- Run a critique round before presenting any UI: screenshot, list what's wrong, fix, then report.
- One screen with no page scroll on desktop; check laptop and phone too.
- Title Case for buttons, headings and tags. No em dashes. Plain literal copy. Propose copy as options unless the user gave the wording.
- High-contrast text, nothing under 12px.
- Never commit or push. Ask squash vs merge before any merge.
- Every website change ends with a running dev server and a LAN URL: `cd frontend && VITE_DATA_MODE=prod npx vite --host --port 5189`, URL `http://192.168.1.10:5189/trophy-mage`.
- Headless screenshots: puppeteer from `/home/mnoya/.npm/_npx/15c61037b1978c83/node_modules/chrome-devtools-mcp/build/src/third_party/index.js` with `/usr/bin/google-chrome`. Hover states need `--blink-settings=primaryPointerType=4,primaryHoverType=2,availablePointerTypes=4,availableHoverTypes=2`. Scratch scripts go in `/tmp`.

## Decisions (2026-10-17)

- **Uneven Pods are fine:** every round needs one 3-0 deck, and the rest can be any mix of 2-1, 1-2 and 0-3. Records may repeat inside a round.
- **Decks show as screenshots.** The card-data layout is dropped.
- **Scoring:** 1 point for each correct guess for now, the trophy included.
- **After the reveal:** show only the trophy player's name, with a link to the Pod's draft log, the way Wheel of Fortune does.
