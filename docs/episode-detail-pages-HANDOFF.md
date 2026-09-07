# Episode detail pages — handoff

Clicking an episode card (thumbnail or title) opens a large autoplaying player in the Episodes content area, at its own URL. The Library sidebar and the top search bar stay in place; only the grid region swaps to the player. Navigation between the grid and a detail URL does not remount, so there is no flicker.

## What ships now

- All three episode routes (`/episodes`, `/episodes/:categorySlug`, `/episodes/:categorySlug/:episodeSlug`) render `EpisodesPage`. React reconciles the same component across the navigation, so state and the loaded feed survive — no remount, no flicker.
- `EpisodesPage` resolves `openEpisode` from the URL. When set, the content region renders `EpisodeDetail` (autoplay `EpisodeEmbed` + title + tag + date/EP) instead of the grid.
- Both the card thumbnail and the title link to the detail. `PlayableThumbnail` gained a `linkTo` mode; the old expand-in-place player was removed.
- `EpisodeCard` links to `${detailBase}/${slug}`, where `detailBase` is the current category/set path, so opening from within a category keeps that context in the URL and the sidebar highlight.
- Slugs are clean and deterministic: `episodeSlug(episode)` is a pure function of the title (`data/episodes.ts`), so every feed and the crawler middleware derive the identical slug (e.g. `/episodes/the-lord-of-the-rings-flashback-draft-guide`). Applied in both `useMediaFeed` and `useRecentEpisodes`. Two of 785 episodes collide on a duplicate or 80-char-truncated title and open the first match.
- Real episode title in the tab and unfurl: `DocumentTitle` resolves the title from the cached `db-episodes` feed; `functions/_middleware.ts` (`episodeSlugMeta`) fetches the episode list (edge-cached 10 min) and matches by the recomputed base slug, serving the real og:title plus the YouTube `hqdefault` thumbnail.
- The detail fills the viewport (`min-h-[calc(100vh-9rem)]`) so the footer stays below the fold.
- Going back to the grid is via the sidebar, the browser back button, or the top nav — there is no in-page back link by design.

## Deliberately omitted (do not reintroduce as-is)

The prominent "Watch on YouTube" / "Listen & watch" panel is gone on purpose. The embed already is the video, so a big watch CTA is redundant and pulls attention off the episode. If listen-on-other-platforms links come back, they must be a quiet secondary affordance, never a hero button.

## Deferred

### Transcript (decided, not built)
- **Placement:** full-width below the video, with seekable timestamps. The transcript never goes in the narrow rail (a real episode is ~12k words). Agreed design mock: `docs/episode-detail-transcript-mock.html` (embeds the real auto-transcript for LLU #258 so the true length is visible). The mock's rail still draws a Watch CTA + Chapters; drop the Watch CTA per the omitted-panel decision above, keep Chapters (and any listen links) quiet.
- **Source:** bot-generated into the DB. The bot pulls YouTube captions with `yt-dlp` (proven: `yt-dlp --write-auto-sub --sub-lang en --sub-format vtt --skip-download` on the episode's `youtube_id`), cleans the rolling-caption overlap into timestamped segments, and stores them in a new episodes column/table served through a `public_` view. 700+ back-catalog is a one-time batch. Not started — needs the DB shape agreed first.
- **Scope (which episodes get a transcript):** transcribe only talk content, not gameplay. Skip `Draft` and `Sealed` by default, keep Set Review, Metagame, Evergreen, Guest, Coaching, Rankings. Use the site's refined category (`categoryFor(title, rawCategory)`), not the raw RSS `category` column, so a talk episode mislabeled Draft (e.g. a "Draft Guide") is still included. Sealed is not uniformly gameplay: keep Sealed episodes whose title signals talk content — `Prerelease`, `Guide`, `Tips`, `Breakdown` and similar — and skip the pure playthroughs. All-in this is ~22 MB on disk; talk-only is ~15-16 MB. Transcripts live in their own table so the include-list can widen or narrow later without a migration.

### Home page deep-linking (optional)
`useRecentEpisodes` now carries deterministic slugs, but the home page renders its own `HeroEpisodeCard`, which still links externally via `episodeTitleHref`. To make home cards open the in-app detail, switch `HeroEpisodeCard` to an internal `Link` to `/episodes/${slug}`. Cross-feed slug consistency is no longer a blocker — the slug is deterministic.
