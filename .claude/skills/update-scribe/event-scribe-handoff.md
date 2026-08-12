# Event schedule from MTG Scribe (handoff)

Shipped `/event-scribe` (commit `655a441`): an on-demand command that renders the MTG Arena event calendar from a committed snapshot of mtgscribe.com, showing the in-progress + upcoming Limited schedule, grouped by set. This doc captures how that data layer works and what carries forward into **Format Schedule integration** (Todoist `6gmr6C7Vr3R7qxpj`): proactive announcements of Flashback/Quick Draft rotations, Cube, Qualifiers, etc. in their channels.

## What shipped

| File | Role |
|---|---|
| `bot/services/scribe_calendar.json` | **The calendar the bot serves.** Captured by `snapshot_scribe`, committed, read on every render. |
| `bot/scripts/snapshot_scribe.py` | The only code that requests anything from mtgscribe.com. Run it from a clean IP, commit, deploy. |
| `bot/services/mtgscribe.py` | `load_events` (bundled read) + grouping/partition, plus the REST client the snapshot script drives. |
| `bot/services/scribe_formats.py` | Standalone format short-name map (`Premier Draft` → `Premier`); vendorable, no bot imports. |
| `bot/commands/event_scribe.py` | The `/event-scribe` cog: pipeline, filters, embed render, link button. |
| `bot/commands/testscribe.py` | `!test scribe` owner command — renders synthetic fixtures through the **same** pipeline so it can't drift. |
| `bot/assets/mtg-scribe.png` | 128px logo used as the embed thumbnail (attachment, not emoji). |
| `frontend/public/set-symbols/cube.png` | The CUBE set symbol, generated from the keyrune `pz1` glyph (keyrune has no `cube.svg`). |

## Data source — a committed snapshot, refreshed by hand

Nothing at runtime calls mtgscribe.com. `load_events` reads `scribe_calendar.json` and parses it in ~3ms; `snapshot_scribe` is the single writer.

Two reasons the live fetch was dropped. **Bot protection:** mtgscribe.com is on SiteGround, whose account-level anti-bot (`/.well-known/sgcaptcha/`) challenges datacenter egress with a 202 HTML page, and the site owner could not turn it off — so repeated requests from Railway get locked out, unpredictably. **Latency:** the API hard-caps a page at 50 events regardless of `per_page` (verified: `per_page=100` and `200` both return 50), so a 150-day window is four sequential pages at ~0.8s each. `/event-scribe` cost ~3s end to end for a calendar that does not change hour to hour.

The capture itself still uses the REST API, not the `/events/feed/` RSS, which only carries a start date. `GET /wp-json/tribe/events/v1/events?start_date=YYYY-MM-DD&per_page=50&page=N` returns `utc_start_date`/`utc_end_date`, local `start_date`/`end_date`, `tags`, `categories`, `title`, `slug`. Paginate via `total_pages`; requesting a page past the end returns **404**, so loop on `total_pages`, never on an empty-page sentinel. `snapshot_scribe` appends `_cb=YYYYMMDDHHMMSS` because the CDN keys on the full query string and otherwise serves stale dates for the canonical URL — a `Cache-Control` header does not reach origin, a unique param does.

`load_events` logs a warning when the calendar runs out within `STALE_HORIZON` (14 days), since a skipped refresh would otherwise decay into an empty schedule with nothing saying why.

## The tag taxonomy (the key asset for the next task)

Everything downstream keys off tags, not titles. Observed slugs on **arena** events:

- **Scope**: `arena` (client-playable; tabletop events lack it), `limited` (vs Arena Constructed).
- **Draft families**: `premier-draft`, `traditional-draft`, `quick-draft`, `pick-2-draft`, `remix-draft`, `contender-draft`. (`premier-draft` is broad — also on Cube/Remix/Contender.)
- **Sealed**: `sealed`, `traditional-sealed`.
- **Arena Direct**: `arena-direct` + a booster slug (`play-boosters` / `collector-booster` / `set-boosters`) + sometimes `japanese-language-box`.
- **Midweek**: `midweek-magic` + the real format tag (`quick-draft`, `phantom`+`sealed`, `cascade`+`draft`, `brawl`, `momir`, `pauper`, …). Many Midweeks are Constructed (no `limited`).
- **Competitive**: `play-in`, `qualifier`, `arena-championship`, `arena-limited-championship-qualifier`, `arena-open`. Most ACQ Play-Ins are Constructed (Standard/Pioneer/Historic) and get dropped by the Limited scope; the Sealed ones survive. Limited competitive is usually Sealed but not always — an Arena Open and the Limited ACQ are `draft`, so `mtgscribe._limited_format` reads Sealed-vs-Draft off the tags for the reminder.
- **Casual side queues**: `jump-in`, `welcome-decks`. Both carry `limited`, so they land in scope; a title with no `"<format>: "` prefix (Welcome Deck Duels) contributes no format and merges silently into the set's main window.
- **`flashback`** — marks old-set rerun drafts (Strixhaven, Bloomburrow, Aetherdrift, War of the Spark…). **Directly answers "announce Flashback rotations."** 9 such events were present over a 90-day window.
- **Set tag**: the slugified set name (`secrets-of-strixhaven`, `marvel-super-heroes`). Maps back to `bot/sets.py` via `_slugify(seed.name)`.

### Upstream is inconsistent — key off the title format, not only the tag

Scribe's tags are hand-entered, so a whole season can publish mistagged or untagged. Observed: three separate Quick Draft queues carrying `premier-draft` or a `quck-draft` typo instead of `quick-draft`; a `strixhave-school-of-mages` typo. This is why the Quick and Premier filters test `format_label` (parsed from the title) while the broader families test tags — the title is the more reliable of the two.

The `flashback` tag arrives **late**: when a set's calendar first appears, only the next one or two reruns are tagged and the rest publish bare, so they render as their own set headers instead of folding into the 🪦 Flashback roster, and the flashback announce does not fire for them. Nothing to fix in the bot — but since the calendar is a committed snapshot, a backfill only reaches players on the next `snapshot_scribe` run and deploy. Worth one mid-season.

Set names also collide by substring — `_seed_for_label` takes the **longest** matching seed name so "Dominaria United" resolves to DMU and not to the 2018 Dominaria whose name it contains.

Format labels drift between rotations ("Pick 2 Draft" → "Pick-Two Draft", "Bo1 Sealed" → "Sealed", "Arena Championship Qualifier Weekend" → "ACQ Weekend"). `scribe_formats.FORMAT_SHORT_NAMES`, `DRAFT_FORMATS` and `ARENA_CHAMP_EXPANSIONS` hold every spelling seen so far rather than only the latest, because Scribe reverts — both qualifier spellings appeared within one season. Keeping a retired spelling costs a dict entry; dropping one silently degrades a render.

`ARENA_CHAMP_EXPANSIONS` maps each spelling to the words the `:arenachamp:` emoji does **not** cover, so both forms decorate identically: the emoji stands for "Arena Championship", which means the "ACQ" abbreviation has to give "Qualifier" back or the heading reads a bare "Weekend".

## Pipeline (event_scribe.process_events — the one place both command and test route through)

`load_events` (arena scope only) → `normalize_event` → filter (`_in_scope` + `_passes_format` + `_passes_set`) → `group_events` (day-based key) → `partition_by_now` → horizon trim (unfiltered only).

- **`normalize_event`** repairs labels that the generic `"<format>: <set>"` title split gets wrong:
  - *Arena Direct* (`Arena Direct: <set> <product>`) → set from tags, format `Arena Direct Play`/`Collector`.
  - *Midweek* → set-bearing groups under the set with the real trailing format; set-less/crossover (a `+` in the label) groups under a generic `Midweek Magic` header, shown verbatim.
  - *Competitive* → keeps the `Bo1`/`Bo3` differentiator parsed from the title.
  - All others → `_clean_set_label` collapses a set name buried in qualifier words (`Sealed Marvel Super Heroes Bo3` → `Marvel Super Heroes`).
- **`group_events`** keys on `(set, start_date, end_date)` — **calendar dates, not timestamps** — so queues opening an hour apart still merge into one line.
- **`partition_by_now`** sorts in-progress by latest end first, upcoming by soonest start.
- **Horizon**: the unfiltered view drops upcoming past `UPCOMING_HORIZON` (45 days); any explicit filter shows everything it matches. No hard line cap.

## Rendering conventions (so announcements match the command's voice)

- Markdown header `###` for the title and each section; sets are `**bold**` with their `:code:` emoji prefix; queues are `└`/`├` tree lines (NBSP-padded: ` ├  `).
- Emoji resolve **by name** at runtime from `bot.fetch_application_emojis()` — no hardcoded IDs. Names: `mtga` (title), `scribe` (link button), `cube`/`<setcode>` (set), `8000gems` (collector), `arenachamp` (replaces the literal "Arena Championship"); `📦` is the unicode package for Play boosters.
- Date range: same month `June 2–8`, cross-month `May 26–June 1`. Relative countdowns use Discord `<t:…:R>`.
- `>3` merged formats → `Premier, Trad Draft and others` (priority via `FORMAT_PRIORITY`).
- **Rosters** collapse formats that rotate one-set-per-window so they don't scatter a header per set: `🪦 Flashback` (any section, from the `flashback` tag) and `🤖 Quick Draft` (Coming Up only — the in-progress Quick Draft stays under its set). Each roster lists its sets as tree lines with the set logo, date range, and countdown. See `_section_blocks` / `_roster_block`.
- **Set-name fit** (`_fit_set_name`): a roster line that would wrap shortens the set name — full name → name minus colon-subtitle and leading article → set code — taking the first that fits the estimated width (`ROSTER_LINE_MAX_WIDTH`, with the custom emoji and `<t::R>` countdown approximated since they render shorter than their source). "Duskmourn: House of Horror" → "Duskmourn"; "The Lost Caverns of Ixalan" (cross-month) → "LCI".
- **Midweek is always called out**: set-bearing Midweeks keep a `Midweek` prefix on the format under their set header (`Midweek Phantom Sealed`), so a Midweek never reads as a regular queue.
- **Cube logo by tag**: any event with a `cube`/`*-cube` tag resolves the `cube` emoji regardless of its name, so oddly-named cubes ("Some Kind of new Cube") still get the logo.

## Deploy / ops

- **Refresh the calendar and deploy** — `.venv/bin/python -m bot.scripts.snapshot_scribe` from a residential IP, then commit `scribe_calendar.json`. Nothing reaches players until that deploy. Worth a run each rotation (Scribe publishes the incoming set's whole calendar weeks ahead), on a corrected window, and once Scribe backfills the `flashback` tags it omits at publish. The script prints how far forward the capture reaches; sanity-check that before committing.
- **`!sync` required** — `/event-scribe` has a `format` choice list and a `set` autocomplete option.
- **Upload application emojis** by exact name: `mtga`, `scribe`, `cube`, `8000gems`, `arenachamp` (set symbols optional; lines render without them).
- Source symbols for emoji live in `frontend/public/set-symbols/<code>.png`.

## Known gaps (not blockers)

- `/event-scribe` is not listed in `/help`.
- No unit tests; `normalize_event`, the filters, day-grouping, the roster fit (`_fit_set_name`), and the "and others" wording are pure functions and good table-driven candidates. `!test scribe` fixtures exercise the roster/midweek/cube/shortening paths end to end.
- Set-bearing Midweeks still group under their set header (now `Midweek`-prefixed) rather than all under one "Midweek Magic" block, consistent with global set-grouping.

---

## Next: Format Schedule integration

**Goal**: the bot proactively announces rotations from Scribe's calendar — Flashback & Quick Draft rotations in the flashback channel, plus Cube, Qualifiers, etc. (Todoist describes "read the once-per-set WotC article"; Scribe already structures that data, so consume Scribe rather than parsing WotC prose.)

**Reuse, don't rebuild**: `mtgscribe.load_events` + the tag taxonomy + `normalize_event` labels + `render`-style formatting. The announcement copy should share builders with `/event-scribe` so they can't drift (same lesson as `testscribe`).

**To build**:
- A scheduled tick (model on `bot/tasks/pod_schedule_post.py` + `bot/services/pod_schedule.py`, which already own the weekly-post + `SCHEDULE_TZ` pattern) that detects events **starting** on a given day and posts an announcement.
- Selection: filter by tag — `flashback`, `quick-draft`, cube (`powered-cube`/`arena-cube`), `competitive` tags — to decide *what* to announce and *which channel*.
- Channel routing: a config map (tag/category → channel id), e.g. a flashback channel. Add to `bot/config.py` (Discord fields are optional there).
- Dedup: track what's been announced (a small table keyed on `seventeenlands_event_id`-equivalent — here the Scribe event `id` or `slug`) so a restart or daily tick doesn't repost. `leaderboard_messages` is the precedent for "track what we posted."

**Open questions for the owner**:
- Which channels for which event types (flashback vs quick-draft vs cube vs qualifier)?
- Announce on the day each event *starts*, or a digest at set rotation?
- Include in-client Constructed rotations (Standard/Alchemy) or Limited-only?
