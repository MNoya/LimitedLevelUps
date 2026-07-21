# P0P1 Multiple Set Support

Support for future p0p1 contests. Today everything is hard-coded to MSH — set code, name,
voting deadline, scoring date, the eligible-card pool, and the ratings fixture wiring. This
spec makes adding a future contest a repeatable operation, and designs (pending maintainer
sign-off) a participant-history view across contests.

This came out of a grilling/domain-modeling session.

## Glossary

- **Contest** — one P0P1 event per set, identified by set code. Per-set data:
  `{ code, name, previewsOpen, cardPool, ratingsSnapshot }`.
- **Allowlist** — the set codes that have a P0P1 contest = the set codes present in the
  `previewsOpen` map. A set with no entry is not a contest.
- **Featured contest** — the single contest shown at `/p0p1`. Resolved from dates (see rule below).
- **Frozen contest** — a finished contest, permanently browsable at a stable URL.
- **Voting window** — `[previewsOpen → release)`; picks can be submitted/changed.
- **Reveal window** — `[release → release+28d)`; results shown (midway, then final).
- **Slots** — the shared 8-slot skeleton (5 mono-color commons, 1 multicolor uncommon, 2
  wildcards), **set-independent**. Filters by rarity + color only.
- Dates: `release` and `name` come from `public_sets` (already driven by `bot/sets.py`).
  `previewsOpen` is the only genuinely P0P1-specific per-set scalar (it's ~full-spoiler time, not
  the earlier `PreviewWindow` already in `bot/sets.py`). Reveal end = `release + 28d`.

## Decisions (settled)

1. **Rotate + keep archive.** One featured contest at a time; past contests frozen and
   permanently browsable at a stable URL.
2. **Slots are a shared constant** across all sets (`SLOTS` in `p0p1Slots.ts` stays as-is; the
   per-set MSH constants leave).
3. **Featured-contest rule** (evaluate over allowlisted sets, dates from `public_sets`):
   1. If any set's **voting** window contains now → feature it (**voting wins** on overlap;
      newest release breaks a multi-match).
   2. Else if any set's **reveal** window contains now → feature it.
   3. Else feature the most recently finished contest (max `release+28d ≤ now`).
4. **Overlap tiebreak = voting wins.** Rationale: voting is time-boxed (miss the release deadline
   and it's gone forever); a reveal is static and stays reachable at its archived URL, so it can
   lose the front slot a few days early at no real cost. Additionally, the setup skill **warns**
   when a new contest's `previewsOpen` falls before the prior set's `release+28d` (i.e. it's about
   to create an overlap) — so the overlap is deliberate, not a surprise.
5. **Finalize-ordering guard.** The setup skill **warns** if the outgoing set's ratings fixture
   isn't `phase: final` before the incoming set could become featured, so an archived contest
   never gets stuck mid-reveal.
6. **Frontend data via `import.meta.glob`.** Card pools and ratings fixtures become lazily-loaded,
   code-split chunks, auto-discovered by filename (`cards-<code>.ts`,
   `p0p1-ratings-<code>.json`). No per-set import wiring in `realApi.ts`/`mockApi.ts`; no bundle
   growth as contests accumulate. A missing ratings file (true during voting) is simply absent
   from the glob map and treated as the existing pre-results kill switch — no placeholder fixture
   needed.
7. **Only static per-set config is a one-line `previewsOpen` map.** `name`/dates derive from
   `public_sets`.
8. **Card fixtures standardize on `export default`** (migrate `cards-msh.ts` off its named
   `cardsMshFixture` export) so the glob loader can load them uniformly.
9. **Generator emits common + uncommon only** — no rare/mythic. No slot filter accepts rarity
   `rare` today (checked: `buildBestTeam` only ever considers slot-eligible cards, and every slot
   filters to common/uncommon), so rares are currently dead weight. Can add a rare tier later if a
   future slot needs one. Also excludes bonus-sheet / Special Guest printings (17lands folds these
   under the same expansion code, but they're not part of the drafted set).
10. **Multi-face card handling.** MSH's only multi-face cards are mythic (out of the pool by rule
    9), which is why this was never hit. HOB introduces **uncommon Adventures**, which will be in
    the pool. Two parts:
    - **Generator:** per-layout field extraction (table below). Slot classification always uses
      top-level `colors` + `rarity` (so an uncommon Adventure lands correctly in
      `wildcard_uncommon`, or `multicolor_uncommon` if its combined color identity is 2+).
    - **Scoring join:** add front-face name normalization
      (`name.split(" // ")[0].trim()`) applied on both sides of the ratings lookup, so Scryfall's
      `"Brazen Borrower // Petty Theft"` matches 17lands' `"Brazen Borrower"`.
    - Adventures are implemented this round; transform/modal-DFC layouts are specified below but
      not built until a set actually needs them.

    | layout                                        | name (display)       | mana_cost                 | colors    | image                      |
    | --------------------------------------------- | -------------------- | ------------------------- | --------- | -------------------------- |
    | normal                                        | top-level            | top-level                 | top-level | top-level `image_uris`     |
    | adventure                                     | `card_faces[0].name` | `card_faces[0].mana_cost` | top-level | top-level `image_uris`     |
    | transform / modal dfc(spec only, not built)\_ | `card_faces[0].name` | `card_faces[0].mana_cost` | top-level | `card_faces[0].image_uris` |

## Open questions — **for the maintainer**, not to be decided unilaterally

- **Privacy reversal for participant history.** The existing `public_p0p1_ballots` view was
  _deliberately_ built to be non-identifying — see migration
  `h1v2o3t4e5r6_p0p1_ballots_drop_auth_users`, whose `ballot_id` is a `dense_rank()` over
  `user_id` that **renumbers whenever a new voter joins** (so it's not a stable identifier by
  design, only "opaque within a fetch" per its own docstring). Giving each voter a stable random
  `public_id` intentionally makes every entrant's full ballot history **durably correlatable
  across all contests** by anyone with the link. That's inherent to a history feature, and using a
  random id (never the real auth UUID) preserves the "don't leak real identity" intent — but it
  reverses a choice someone made on purpose. **Needs an explicit yes before building.**
- **Is participant history in the same PR as the core plumbing, or a fast-follow?** It's designed
  below and is fairly self-contained, but gated on the answer above.

## Implementation — core (multi-set plumbing + generator + Adventure handling)

### Frontend: contest registry + featured resolution

- `frontend/src/data/p0p1Slots.ts`: keep `SLOTS` and the slot filter helpers. Remove
  `P0P1_SET_CODE` / `P0P1_SET_NAME` / `P0P1_VOTING_DEADLINE` / `P0P1_SCORING_DATE` /
  `P0P1_NEXT_SET_CODE` / `P0P1_NEXT_SET_NAME`. Add:
  - `P0P1_PREVIEWS_OPEN: Record<string, string>` — the allowlist + `previewsOpen` dates (the setup
    skill appends one line per set).
  - `resolveFeaturedContest(sets, now)` implementing the rule in Decision 3, where `sets` comes
    from `public_sets` (release date + name) intersected with the allowlist. Returns
    `{ code, name, previewsOpen, votingDeadline, revealEnd, isVoting/isReveal/isFrozen }`.
- `frontend/src/data/realApi.ts` (currently around L1513-1526): replace the static
  `cards-msh` / `p0p1-ratings-msh` imports with:

  ```ts
  const cardLoaders = import.meta.glob('./fixtures/cards-*.ts', {
    import: 'default',
  });
  const ratingLoaders = import.meta.glob('./fixtures/p0p1-ratings-*.json');
  ```

  `fetchP0P1Cards(code)` / `fetchP0P1Ratings(code)` index by `code` and `await` the matching
  loader; ratings resolves to `null` when absent. Mirror the same change in
  `frontend/src/data/mockApi.ts`.

- `frontend/src/data/useP0P1Ballot.ts` (`deriveP0P1Phase` and its inputs): source the featured
  contest's code + dates from `resolveFeaturedContest(...)` instead of the module constants. Phase
  derivation logic itself is unchanged.
- `frontend/src/data/fixtures/cards-msh.ts`: convert its named export to `export default`.

### Frontend: name normalization (Adventures)

- `frontend/src/data/p0p1Results.ts`: add `normalizeCardName(name)`. Apply it when building the
  ratings lookup and when looking up a pick's rating (see Decision 10). `buildBestTeam` already
  only considers slot-eligible cards — no other change needed there.

### Frontend: archive routing

- `frontend/src/App.tsx`: add `/p0p1/:setCode` → `P0P1Page`, rendering a frozen/terminal view for
  any allowlisted set regardless of date (reuses `FinalResults`). `/p0p1` (no param) stays = the
  resolved featured contest.
- `frontend/src/pages/P0P1Page.tsx`: take the contest code from the route param, falling back to
  the resolved featured contest for the bare `/p0p1`.
- **Out of scope:** a discovery UI (an index/list page to _find_ old contests without already
  knowing the code). Stable URLs work; reaching them requires the code or a link (e.g. a future
  result-row click). Follow-up.

### Bot: card-pool generator

- New `bot/scripts/fetch_p0p1_cards.py`: pull `set:<scryfall_code>` from Scryfall, filter to
  **common + uncommon**, exclude bonus-sheet / Special Guest printings and non-draftable extras,
  and emit `frontend/src/data/fixtures/cards-<code>.ts` (`export default Card[]`) using the
  per-layout extraction table in Decision 10. Confirm the Scryfall set code vs the 17lands
  expansion code up front — they can diverge for promos/Alchemy/supplemental sets, and a mismatch
  breaks the ratings join silently.

### New skill: p0p1-contest-setup

Runs the generator, appends the `previewsOpen` allowlist entry, and validates the handoff. Never
commits or pushes (matches `p0p1-phase`'s convention). Must:

- Warn on overlap (Decision 4) and on finalize-ordering (Decision 5).
- Run at/after full spoiler (voting needs the complete card pool); a late-spoiler top-up re-run is
  fine.
- Report a ratings join-check when a ratings fixture exists: for each pool card, did it match a
  rating by normalized name? Flag misses (especially `//` and special-character names). Note that
  a pool-vs-ratings count gap is _expected_ (17lands folds bonus sheets into the same expansion
  code; the pool excludes rare/mythic) and is not itself an error signal — only unmatched
  _pool_ cards are.

`p0p1-phase` is **unchanged** — it still produces `p0p1-ratings-<code>.json` weeks later (midway,
then final), independent of setup. Ordering dependency: the next set must already be in
`bot/sets.py` (via `/add-set`) before its contest can resolve dates.

## Participant history — designed, **pending maintainer sign-off** (see Open Questions)

- **DB:** `ALTER TABLE p0p1_voters ADD COLUMN public_id` (random, e.g. `gen_random_uuid()`;
  backfill existing rows). The existing `sync_p0p1_voter()` trigger already keeps name/avatar
  current, no change needed there. Update `public_p0p1_ballots` to expose `public_id` (replacing
  or augmenting the unstable `ballot_id`). New alembic migration, guarding the `auth` schema
  absence the way the existing p0p1 migrations already do.
- **Routing:** `/p0p1/players/:publicId` → a history page.
- **Page logic:** query the set codes where this `public_id` has ballots (participation-scoped,
  not a full archive scan), then for each, load that contest's ballots + card fixture + ratings
  fixture and reuse the existing `rankBallots` / `buildStandingsList` to compute that entrant's
  finish per set. **No new score table.** Caveat: finish is recomputed with _current_ scoring
  logic against frozen fixtures — deterministic today, but a future scoring-formula change would
  retroactively restate history.
- **Entry point:** a result-row click in `FinalResults` would target
  `/p0p1/players/:publicId` (needs `public_id` carried through the ballots data). Bonus cleanup
  this unlocks (not required for history itself): the main results page's "your row" highlight
  could stop parsing the Discord id out of the avatar URL (`findUserBallot` in
  `p0p1Results.ts`) and use `public_id` instead — though wiring the logged-in viewer's own
  `public_id` to the client needs a small authenticated lookup.

## Out of scope / follow-ups

- Archive discovery UI (a browsable index of past contests).
- transform / modal_dfc generator path (specified, not built until a set needs it).
- Moving P0P1 config into the database (the TODO that used to sit in `p0p1Slots.ts`) — the glob +
  tiny `previewsOpen` map supersede the need for this.

## Verification (for whoever implements)

- **Multi-set plumbing:** add a second fixture pair (`cards-<code>.ts` +
  `p0p1-ratings-<code>.json`) and a `previewsOpen` entry with dates that make it the featured
  contest; `npm run dev`, confirm `/p0p1` renders it, the 8 slots populate from its pool, and
  `/p0p1/msh` still renders MSH frozen.
- **Featured resolution:** unit-test `resolveFeaturedContest` for voting-only, reveal-only, gap,
  and the overlap case (voting wins).
- **Adventure handling:** run the generator on HOB (or another Adventure set), confirm an
  uncommon Adventure appears with the creature's name/cost/art and lands in
  `wildcard_uncommon`; with a ratings fixture present, confirm the normalized join matches it (no
  silent zero score).
- **Generator filters:** confirm output is common+uncommon only and excludes Special Guests.
- **Bundle:** `npm run build`, confirm card/ratings fixtures split into separate chunks rather
  than inflating the main bundle.
- **Participant history (if built):** `alembic upgrade head` + `alembic check`; backfill
  populates `public_id`; a result-row click loads `/p0p1/players/:publicId` and shows finishes
  only for sets the player actually entered.
