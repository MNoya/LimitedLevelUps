# P0P1 Contests

The engineering map for how a Pack 0 Pick 1 contest is scheduled and resolved: the per-set registry,
which contest `/p0p1` features, the card-pool generator, and the archive routes. Read this before
changing contest scheduling instead of re-inferring it, and for the reasoning behind decisions that
look arbitrary from the code alone (chiefly why contest windows sit outside Postgres).

Not covered here: the ballot and results UI (`p0p1-voting-mvp.md`, `p0p1-after-submissions-closed.md`,
`p0p1-results.md`) or the ratings phase flip (the `p0p1-phase` skill). Participant history is designed
below but not built.

## Human-written high-level summary

- Support contests for future sets
- Support archived contests
- (To discuss) - Participant history pages where you can see past performance across previous contests
  - The actual pages are outside the scope of the work of this spec, but we would
    ideally decide if we want this now because it requires a decision on how we
    would link participants across contests - the identity approach should be decided now.
    (See the Participant History implementation section below)

## Glossary

- **Contest** — one P0P1 event per set, identified by set code. Per-set data:
  `{ code, name, previewsOpen, votingDeadline, cardPool, ratingsSnapshot }`.
- **Allowlist** — the set codes present in `p0p1_contests.json`. A set with no entry is not a contest.
- **Featured contest** — the single contest shown at `/p0p1`. Resolved from dates (see rule below).
- **Frozen contest** — a finished contest, permanently browsable at a stable URL.
- **Voting window** — `[previewsOpen → votingDeadline)`; picks can be submitted/changed.
  `votingDeadline` defaults to `release` but can be set earlier per contest.
- **Results window** — `[votingDeadline → release+28d)`; community stats, then midway, then final.
  Anchored to the deadline rather than `release` so a contest stays featured across the gap when
  voting closes early, which is otherwise a stretch of days handing `/p0p1` back to the last set.
- **Slots** — the shared 8-slot skeleton (5 mono-color commons, 1 multicolor uncommon, 2
  wildcards), **set-independent**. Filters by rarity + color only.
- Dates: every instant lives in the contest fixture. `release` and `name` come from `bot/sets.py`;
  `previewsOpen` is set by the generator when the pool first passes its coverage check, so voting
  opens as soon as a complete pool ships. Reveal end = `release + 28d`. Only `votingDeadline` is a
  genuine input, and it defaults to `release`.
- **Pre-contest** — a contest whose `previewsOpen` has not arrived. Never featured, and 404s at its
  archive URL, so a pool still being spoiled can be committed early without exposing a ballot.

## Decisions (settled)

1. **Rotate + keep archive.** One featured contest at a time; past contests frozen and
   permanently browsable at a stable URL.
2. **Slots are a shared constant** across all sets (`SLOTS` in `p0p1Slots.ts` stays as-is; the
   per-set MSH constants leave).
3. **Featured-contest rule** (evaluate over the contest fixtures, no DB read):
   1. If any set's **voting** window contains now → feature it (**voting wins** on overlap;
      newest release breaks a multi-match).
   2. Else if any set's **results** window contains now → feature it.
   3. Else feature the most recently finished contest (max `release+28d ≤ now`).
   4. Else (nothing has opened yet) the earliest contest, reported `pre` so no ballot renders.
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
   `p0p1-ratings-<code>.ts`). No per-set import wiring in `realApi.ts`/`mockApi.ts`; no bundle
   growth as contests accumulate. A missing ratings file (true during voting) is simply absent
   from the glob map and treated as the existing pre-results kill switch — no placeholder fixture
   needed.
7. **A contest is self-contained and generated** — one root `p0p1_contests.json`, keyed by set code,
   each entry carrying `name`, `release`, `previewsOpen` and optional `votingDeadline` (defaults to
   `release`), all as ISO instants. Same shared-config shape as `scoring_buckets.json`: the frontend
   imports it directly and the generator upserts one key at a time, so `python -m json` is the writer
   and there is no TS literal to edit. One file rather than a fixture per contest, so the whole
   schedule is readable at a glance and a deadline edit has one obvious place to go. **Superseded the original
   `public_sets`-derived design**: that view hides a set until its release day, which is exactly
   the span a P0P1 contest runs in, so a contest could not exist before its set did. Deriving
   `name`/`release` in the fixture also puts the noon-ET release boundary in one place —
   `bot/sets.py` computes it with a real tz database, instead of the browser assuming 16:00 UTC
   and being an hour off for winter releases. Values are machine-written, so `bot/sets.py` stays
   the source of truth, and hand-editing a single deadline stays a safe one-line change.
   Consequences: `/p0p1` no longer needs the sets query, and a deadline change is a one-line
   fixture edit with no migration and no query.
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

- **Is participant history in the same PR as the core plumbing, or a fast-follow?** It's designed
  below and is fairly self-contained.
- ~~Identity approach for participant history~~ — **settled**: frozen slug (see section below).

## Implementation — core (multi-set plumbing + generator + Adventure handling)

### Frontend: contest registry + featured resolution

- `frontend/src/data/p0p1Slots.ts`: keep `SLOTS` and the slot filter helpers. Remove
  `P0P1_SET_CODE` / `P0P1_SET_NAME` / `P0P1_VOTING_DEADLINE` / `P0P1_SCORING_DATE` /
  `P0P1_NEXT_SET_CODE` / `P0P1_NEXT_SET_NAME`. Add:
  - `P0P1_CONTESTS: Record<string, ContestConfig>` — the shared `p0p1_contests.json` imported
    directly, mirroring how `data/format-buckets.ts` imports `scoring_buckets.json`. Not globbed and
    not code-split: every window is needed synchronously to decide which contest is featured, and
    they are a handful of strings each.
  - `resolveFeaturedContest(now)` / `resolveContestByCode(code, now)` implementing Decision 3,
    sharing one `describeContest(contest, contests, now)` that derives `status` and `next`. Both are
    pure functions of the fixtures and the clock — no `sets` argument.
- `frontend/src/data/hooks.ts`: `useP0P1FeaturedContest` drops `useSets()`. Because the resolver no
  longer depends on a query, it needs its own clock or it freezes at first render and never crosses
  the deadline without a reload — so it memoizes on `useTick(30_000)`, hoisted from
  `components/p0p1/Countdown.tsx` to `lib/use-tick.ts` and returning its counter as a dep handle.
- `frontend/src/data/realApi.ts` (currently around L1513-1526): replace the static
  `cards-msh` / `p0p1-ratings-msh` imports with:

  ```ts
  const cardLoaders = import.meta.glob("./fixtures/cards-*.ts", {
    import: "default",
  });
  const ratingLoaders = import.meta.glob("./fixtures/p0p1-ratings-*.ts", { import: "default" });
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
  the resolved featured contest for the bare `/p0p1`. A `pre` contest 404s: `status` is derived from
  `previewsOpen` upward, so a fixture committed during spoiler season cannot serve a ballot early
  through its archive URL.
- **Out of scope:** a discovery UI (an index/list page to _find_ old contests without already
  knowing the code). Stable URLs work; reaching them requires the code or a link (e.g. a future
  result-row click). Follow-up.

### Bot: contest generator

- New `bot/scripts/fetch_p0p1_cards.py`: pull `set:<scryfall_code>` from Scryfall, filter to
  **common + uncommon**, exclude bonus-sheet / Special Guest printings and non-draftable extras,
  and emit `frontend/src/data/fixtures/cards-<code>.ts` (`export default Card[]`) using the
  per-layout extraction table in Decision 10. Confirm the Scryfall set code vs the 17lands
  expansion code up front — they can diverge for promos/Alchemy/supplemental sets, and a mismatch
  breaks the ratings join silently.
- The same run upserts this set's key in `p0p1_contests.json`, reading `name` and the noon-ET
  `release` from `bot/sets.py` and leaving every other contest byte-identical. **The script decides
  the window, not the caller** — one invocation is correct at any
  point in spoiler season, which is what makes `/p0p1 <CODE>` a single-argument call:
  no window plus an incomplete pool writes nothing; no window plus a complete pool opens voting
  immediately; an existing window is left alone so a top-up cannot reschedule a live vote. `--opens`
  and `--deadline` override explicitly, each preserving the other. Bare dates mean noon ET.
- **Slot-coverage preflight.** After writing, report commons per color plus multicolor uncommons and
  flag empty slots as `POOL INCOMPLETE`. Mid-spoiler a set is nearly all uncommons — HOB at
  2026-07-26 had 34 cards, 5 of its 6 commons basic lands, and 4 of the 8 slots unfillable. The
  report describes the pool rather than reimplementing `SLOTS`, so the check cannot drift from the
  TypeScript filters.

### New skill: p0p1

`/p0p1 <CODE>` runs the generator and validates the handoff. Never commits or pushes (matches
`p0p1-phase`'s convention). Must:

- Warn on overlap (Decision 4) and on finalize-ordering (Decision 5).
- Relay the script's window decision and name the empty slots when the pool is short. A hidden set
  mid-spoiler is the expected outcome, not a failure.
- Never reschedule an existing window unless asked, since players may be voting in it.
- Report how many days of Arena play the reveal will cover when `votingDeadline` precedes `release`
  by more than a day, since `scoringDate` is `votingDeadline + 28d` regardless.
- Report a ratings join-check when a ratings fixture exists: for each pool card, did it match a
  rating by normalized name? Flag misses (especially `//` and special-character names). The ratings
  fixture is already filtered to C/U pool cards by `fetch_p0p1_ratings`, so a count gap means
  unmatched names, not rarity differences.

`p0p1-phase` is **unchanged** — it still produces `p0p1-ratings-<code>.ts` weeks later (midway,
then final), independent of setup. Ordering dependency: the next set must already be in
`bot/sets.py` (via `/add-set`) before its contest can resolve dates.

### Bot: T-1 day vote reminder

An hourly UTC tick (`bot/tasks/p0p1_reminder_post.py`) fires one ping into the contest set's own discussion channel once `now` is inside the last day of voting. A contest whose whole window is shorter than the lead qualifies from the moment it opens, so a short contest still gets its nudge. There is deliberately no hand-invoked equivalent on production: Discord grants a role one member per call (no bulk endpoint exists), measured at ~0.64s per call, so a 90-person sweep is ~180 calls and about two minutes. That is fine unattended and far too slow to hang a command on. `!test p0p1reminder` runs the identical path on the test server, held to the caller. The set channel is matched by word overlap, so a stylised name like `#🏔️-the-hobbit` resolves without configuration.

**Targeting is a throwaway role, not DMs.** A bot can only message a user who shares a guild with it, so a DM sweep reaches nobody a role grant misses, and a burst of unsolicited DMs is the pattern Discord reads as spam. `bot/services/p0p1_reminder.py` grants the shared `Reminder` role to every non-voter present in the guild, makes it mentionable only for the send, posts, then empties it. The role is deliberately generic so any future one-off nudge can borrow the same swap; the swap itself still lives in the P0P1 module and moves out when a second caller wants it. It sits in `MANAGED_ROLES` with `REMINDER_COLOR`, so the reconcile owns its name and color, and `ManagedRole.aliases` renames an existing role in place instead of orphaning it. `reminder_role` only creates it for a guild the reconcile has not reached yet. The role is never deleted: a deleted role renders as `@deleted-role` in the history the ping leaves behind. It is emptied before the grants as well as after, so a run that died mid-strip cannot ping the previous contest's list.

**Audience** is everyone holding a P0P1 identity (`p0p1_voters` union anyone with entries) who has no entry for this contest. Identity resolves through `auth.identities`, not `players` — most voters signed in on the website and never joined the leaderboard, so `auth.identities` is the only place their Discord id exists. The reach ceiling is guild membership, which is why the run reports `pinged / targeted` and an `absent` count for voters who are not in the server: no notification surface can reach those, and a growing `absent` is the number worth watching.

**Only the production guild gets a real sweep.** Anywhere else `audience` holds the ping to whoever ran `!test p0p1reminder`, and to nobody at all when the scheduled tick fires. A test server holds real people who never signed up for a P0P1 nudge, and its audience comes from the dev fallback below anyway, so a full sweep there would ping the wrong crowd. The post itself still goes up, so the card stays reviewable.

Supabase owns `auth`, so no developer database has it. Rather than making the role-swap path testable only against production, a missing schema falls back to every local `players` row and labels the outcome `SOURCE_PLAYERS`; the bot-spam report then says outright that the audience is not the real one. Nothing links a local `players` row to a P0P1 identity, so the fallback deliberately excludes nobody.

**One post per contest** is enforced off channel history, matched on the reminder role's own mention (nothing else posts it in a set channel) plus the contest name. A history read that fails suppresses the post, since a duplicate mass ping is worse than a missed one, and the hourly tick retries on its own. Every run mirrors its reach to bot-spam, which is the only trace left once the role is emptied.

## Participant history

- **Identity (settled): frozen slug on `p0p1_voters`**, mirroring how `players.slug` works on
  the leaderboard. `user_id` stays the internal FK for cross-contest history queries; a new
  `slug` column (unique, not-null) is the public-facing URL identifier. The slug is frozen at
  first ballot submission — derived from the voter's `name` via the same slugify logic as
  `bot/slug.py`, never updated afterward. Display name continues to track Discord via the
  existing `sync_p0p1_voter` trigger; only the slug stays fixed.
  - **Collision disambiguation** (`-2`, `-3`, etc.) happens in Postgres (inside the
    `sync_p0p1_voter` trigger or a helper function), since voter creation is trigger-driven,
    not application code.
  - **Migration**: add `slug` column nullable → backfill from existing `name` values with
    disambiguation → add not-null + unique constraints. Update `public_p0p1_ballots` view to
    expose `slug` instead of the unstable `dense_rank()` `ballot_id`.
- **Routing:** `/p0p1/players/:slug` → a history page.
- **Page logic:** query the set codes where this voter has ballots (participation-scoped,
  not a full archive scan), then for each, load that contest's ballots + card fixture + ratings
  fixture and reuse the existing `rankBallots` / `buildStandingsList` to compute that entrant's
  finish per set. **No new score table.** Caveat: finish is recomputed with _current_ scoring
  logic against frozen fixtures — a future scoring-formula change would retroactively restate
  history.
- **Entry point:** a result-row click in `FinalResults` targets the history page. Bonus cleanup
  this unlocks: the "your row" highlight could stop parsing the Discord id out of the avatar URL
  (`findUserBallot` in `p0p1Results.ts`) and use the stable slug instead.

## Out of scope / follow-ups

- Archive discovery UI (a browsable index of past contests).
- transform / modal_dfc generator path (specified, not built until a set needs it).
- Moving P0P1 config into the database (the TODO that used to sit in `p0p1Slots.ts`) — the contest
  glob supersedes the need for this, and keeping windows out of Postgres is what lets a deadline
  change ship without a migration.
- Widening `public_sets` to expose upcoming sets. Considered and rejected for this: `early` and the
  release-day gate exist so an unreleased set cannot leak into the UI, six `useSets()` consumers
  build user-facing pickers straight off that list, and the guarantee would move from one SQL clause
  to a convention every future caller has to remember. Revisit only if something other than P0P1
  needs pre-release sets.
- A bot-side P0P1 surface (daily voting notices). Nothing exists today, but `p0p1_contests.json` is
  already the shared file a bot task would read, the same way `bot/scoring.py` reads
  `scoring_buckets.json`. No further config decision is pending.

## Verification (for whoever implements)

- **Multi-set plumbing:** generate a second contest (`cards-<code>.ts` + a `p0p1_contests.json` key) with
  dates that make it featured; `npm run dev`, confirm `/p0p1` renders it, the 8 slots populate from
  its pool, and `/p0p1/msh` still renders MSH frozen.
- **Featured resolution:** voting-only, reveal-only, gap, pre-previews, and the overlap case (voting
  wins). No test runner exists in `frontend/` yet, and `import.meta.glob` only resolves under Vite,
  so covering this means standing up vitest rather than a plain node script.
- **Generator fidelity:** re-running on a released set must reproduce its committed fixture byte for
  byte (verified against `cards-msh.ts`), and a bare `--deadline` date must land on noon ET in both
  EDT and EST. Cover all four window decisions: incomplete-and-unscheduled writes nothing,
  complete-and-unscheduled opens now, an existing window survives a top-up, and `--deadline` alone
  preserves `previewsOpen`.
- **Adventure handling:** run the generator on HOB (or another Adventure set), confirm an
  uncommon Adventure appears with the creature's name/cost/art and lands in
  `wildcard_uncommon`; with a ratings fixture present, confirm the normalized join matches it (no
  silent zero score).
- **Generator filters:** confirm output is common+uncommon only and excludes Special Guests.
- **Bundle:** `npm run build`, confirm card/ratings fixtures split into separate chunks rather
  than inflating the main bundle.
- **Participant history (if built):** `alembic upgrade head` + `alembic check`; a result-row
  click loads the history page and shows finishes only for sets the player actually entered.
