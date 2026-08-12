# P1P1 of the Day — Draft Pick Quiz (study / deferred spec)

**Status:** Deferred. This is a study to capture the design before building, not a committed implementation. Build order puts the Draft Review announcement and pause/stop/restart ahead of this.

**Not to be confused with P0P1** (`spec/p0p1-voting-mvp.md`) — that's a website roster-building contest scored by 17lands GIH winrate. This is a Discord daily guessing game built on our real pod-draft logs. Different feature, different surface, similar-looking name.

---

## What it is

A daily Discord post that replays the opening pack of a **real past LLU pod draft** and asks people to guess what the first four drafters actually picked (P1P1 through P1P4). Players submit four guesses, then immediately see how they did against what was really taken. It runs for fun — there is no leaderboard, no scoring points, no stats or streaks.

The idea is ported from Amelas/DraftBot's "Draft Pick Quiz". The reference screenshots below are DraftBot's **scored** version; ours drops the scoring (see Decisions).

---

## Reference: DraftBot's Draft Pick Quiz

Screenshots are gitignored under `spec/p1p1-images/` (not committed — DraftBot UI, kept locally for reference).

### 1. The public post — `spec/p1p1-images/1-quiz-post.png`

![DraftBot quiz post](p1p1-images/1-quiz-post.png)

A pinned public embed titled "Draft Pick Quiz #400":
- Draft Info: cube name, date, and "Pack: 1 (Pack 0), Picks 1-4".
- Players in pick order (the 4 drafters down the seat being quizzed).
- A "View Pack on MagicProTools" link — a **spoiler-free** pack view (shows the 15 cards, not what was picked).
- The 15 available cards listed by name, plus a composite image (5×3 grid) of all 15 card images.
- A persistent "Make Your Guesses" button.

### 2. The guess view — `spec/p1p1-images/2-guess-view.png`

![DraftBot guess view](p1p1-images/2-guess-view.png)

Ephemeral, per-user: four dropdown selects (one per pick, each listing all 15 cards) and a "Submit Guesses" button.

### 3. The results — `spec/p1p1-images/3-results.png`

![DraftBot results](p1p1-images/3-results.png)

Ephemeral results panel: per-pick correctness (exact match / right-card-wrong-seat / miss), what each player actually picked, points earned, lifetime stats (total/average/best/accuracy/perfect streak), a shareable emoji line, and a "Share Results Publicly" button.

DraftBot scoring for reference: pick weights `[2,3,4,5]`, perfect bonus `+5`, all-cards bonus `+2`, team bonus `+1` (right card, wrong seat, same team parity). Feeds a `quiz_points` leaderboard category. **We are not porting the scoring** — kept here only to document the source.

---

## Data availability — confirmed viable

DraftBot reads past drafts from private DigitalOcean Spaces. We already store the equivalent: every pod persists its full Draftmancer log gzipped in `pod_draft_events.draft_log_gz`.

The Draftmancer log shape (parsed today by `bot/scripts/draftmancer_log.py`):
- `log["carddata"]` — card id → card data (name, Scryfall id for images).
- `log["users"]` — per seat, `user["picks"][]` with `packNum`, `pickNum`, `booster` (card ids shown in that pack), `pick` (indices chosen).
- `log["boosters"]` — the raw packs.

Reconstructing a P1P1 quiz is therefore direct: pick a stored event, pick a seat, take `packNum == 0` picks `pickNum 0..3` down that seat — `booster` is the 15-card pool, `booster[pick[0]]` is the card actually taken. This is exactly DraftBot's model against our own data. No data blocker.

---

## Decisions locked

- **For fun only — no scoring, no leaderboard, no stats, no streaks, no persistence beyond the single quiz post.** Reason: our pod replays are **public** on limitedlevelups.com/pods, so the "correct answer" is lookup-able. A scored quiz would be trivially cheatable. Time-boxed scoring and 17lands-keyed scoring were both considered and rejected; the community wants this as a light daily game, not a competitive one.
- **Packs come from real past LLU pod drafts** (`draft_log_gz`), not simulated packs.
- **Discord only** to start. No website surface. A web archive can be a later spec.
- Because there is no scoring, the public-answers problem is moot and no anti-cheat mechanism is needed.

---

## Proposed design for our version

### Flow

1. **Post** (scheduled daily + a mod manual command): pick a random eligible past pod draft + a random seat, reconstruct P1P1-P1P4 down that seat, post the public embed with the 15-card composite and a "Make Your Guesses" button. Pin it.
2. **Guess** (ephemeral, per user): four dropdowns of the 15 cards + submit.
3. **Reveal** (ephemeral, on submit): show each of the four picks — the card the user guessed vs. the card actually taken, marked correct / wrong — and a "you got X/4" line. Optional public "Share" button. No points, no stored stats.

### Selection

- Eligible source = finalized pod events with a usable `draft_log_gz`.
- Avoid repeating a recently-used `(event, seat)` — a small in-memory or lightweight-table dedupe window is enough (DraftBot tracks used combos per guild). Since we don't persist results, a tiny `p1p1_posts` row per posted quiz (event id, seat, message id, posted_at) is the minimum needed for dedupe and for re-hydrating the persistent button after a restart.
- Seat choice: any of the 8 seats is a valid P1P1 vantage; DraftBot uses "valid starting seats" — for us any seat with a full P1 works.

### Cards & images

- Card names come from `carddata`.
- Composite image: port DraftBot's `helpers/pack_compositor.py` approach (download Scryfall images by the card's Scryfall id, tile 5×3, cache). Config-gate it like DraftBot's `quiz_pack_images` in case image generation is slow or flaky.
- Optional spoiler-free MagicProTools pack link — we already have `bot/services/magicprotools.py`; DraftBot builds a pack-only visualization URL. Nice-to-have, not required.

### Scheduling & commands

- Scheduled post: one configured channel + a daily time, following the existing cron/tick pattern in `bot/tasks/` (same shape as the format-schedule / awards ticks; times like `AUTO_REFRESH_TIMES`).
- Manual post: a mod-gated command to fire one on demand (DraftBot's `/post_quiz`).
- Config: quiz channel id, post time, image on/off.

### Persistence (minimal)

- No `QuizSubmission` / `QuizStats` / leaderboard tables (DraftBot has all three — we skip them).
- One small table for posted quizzes (dedupe + persistent-view rehydration) is the only DB addition. The persistent "Make Your Guesses" button must survive restarts like the leaderboard Join/Stats view (registered via `bot.add_view()` at startup).

---

## Porting map (DraftBot → us)

DraftBot source worth reading when building:
- `cogs/quiz_commands.py` — quiz creation/posting, `/post_quiz`, scheduled posting, embed + composite + MPT link.
- `quiz_views_module/quiz_views.py` — public button view, per-user dropdown guess view, scoring, results, share button. (Take the UI, drop the scoring.)
- `helpers/pack_compositor.py` — Scryfall image download + 5×3 composite.
- `services/draft_analysis.py` + `models/draft_domain.py` — pack trace reconstruction (we have our own equivalent in `bot/scripts/draftmancer_log.py`).
- `cogs/unified_scheduler_cog.py` + `cogs/quiz_scheduling_cog.py` — scheduling (we'll use our own tick pattern instead).

Our touchpoints:
- New scheduled task under `bot/tasks/`.
- New command module under `bot/commands/` for the manual post + the guess/reveal views.
- Reconstruction helper reusing `bot/scripts/draftmancer_log.py` logic against `pod_draft_events.draft_log_gz`.
- One migration for the `p1p1_posts` dedupe/rehydration table.
- Persistent view registration in `bot/main.py`.

One porting gotcha flagged in DraftBot: in `_create_and_post_quiz` the `channel.send` that assigns `message` sits only inside the `if pack_image_file:` branch, so the no-image path can leave `message` unset. Handle both paths.

---

## Open questions

- **Cadence** — truly daily, or a few times a week? One channel only?
- **Which channel** — a dedicated games channel, or an existing one?
- **Seat framing** — do we reveal the real player names (as DraftBot does) or anonymize? Real pods = real community members; naming them is more fun but exposes their picks by name. (Names are already public on the site, so likely fine.)
- **Guess window** — since it's unscored, do guesses stay open indefinitely on the message, or close after a period? Unscored means no strong reason to close, but a reveal-all summary after N hours could be a nice touch.
- **Composite image** — build it ourselves (Scryfall + Pillow) or lean on the MagicProTools pack link only, to avoid an image pipeline?

---

## Out of scope (deferred)

- Any scoring, points, stats, streaks, or leaderboard.
- Website surface (archive, results, standings).
- Simulated/random packs from a set (only real pod logs).
- Multiple concurrent quizzes / multi-guild scheduling.
