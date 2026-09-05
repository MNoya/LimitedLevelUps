# Pod Guide — build notes

Reference for the `/pods/guide` page (`frontend/src/pages/PodGuidePage.tsx`, one self-contained file). Captures what shipped, the copy voice that got approved, and the process to repeat it. This is the living design doc; the two HTML mocks that used to sit here were throwaways and are gone.

## What shipped

A section guide with a left rail (desktop) and a sticky underline-tab bar (mobile), section-jump navigation, and per-section cards that mirror the real Discord/site surfaces:

- **How to play** — three numbered steps (Sign up on Discord, Draft on Draftmancer, Play on Arena). No section title on desktop or mobile; it's the intro.
- **Signing up** — `LauncherCard`, a mirror of the daily launcher embed. Live active set + viewer-local slot times.
- **Drafting** — `ReadyCheckCard`, the Ready Check embed mirror.
- **Round Pairings** (tab label "Pairings") — `RoundOneCard`, the pairings embed + report select.
- **Podium** — `RecapCard`: the latest finalized non-team-draft 8-player pod, top 4, rendered with the real `PodStandingRow`. Deck icon opens the real `DeckScreenshotModal`.
- **Seasons** — `SeasonBoardCard`: a compact pod-Leaderboard (rank / avatar+name / trophies / points), top 6, built from the same primitives as the Podium.

**Deferred to next session (with the Organizers work):** add a third Podium bullet. Current two cover the deck screenshot + colors and "all tracked"; the missing one is the pod-points fact. Leading option: "Match wins earn pod points on the Leaderboard" (ties the Podium to Seasons and lands the homeless 5/2/0.5 pod-points line). Alternatives floated: link to the player page, the result-card-posts line, the closed-decklist case.

**Not shipped yet: the Organizers section.** It was removed before commit (it was still the original Claude-drafted slop). Next session: rename it **"Organizers"** (drop "For"), rewrite in the voice below, then re-add the Block + `SECTIONS` entry. The removed content covered: drop/kick a player, disconnect handling, wrong-result fixes, >10 split, short-pod prompts, remake/cancel, `/draft` scheduling, settings. Ground each against `bot/` before rewriting. It was an accordion (`Acc`) with command chips (`Cmd`) — both components were deleted with it and would come back.

## The copy voice (what got approved)

- **Reader-value filter is the whole game.** Only include what the reader at that step actually wonders about, never a bot capability that is merely true.
- **One fact per bullet, one line.** A period mid-bullet means split or cut.
- **Imperative is the house style** across the guide.
- **Complement the card, never narrate it.** If the card beside the bullets already shows it, the bullet doesn't repeat it.
- **Plain declarative microcopy.** Name the real thing + the real action in the plainest accurate word. Literal verbs only, no phrasal verbs/idioms (non-native readers).
- Bold only literal button/menu/role labels. No trailing periods on bullets. "on Arena" not "in Arena".
- No emoji in bullets except deliberate role/title glyphs (👑 Set Champion, ⚜️ Pod Champion).
- No comma-appended time/list clauses ("every day, all season") — reads as an AI tell; fold into one phrase.

### Declined slop (do not reintroduce)
Editorial/marketing register ("the nicer way to keep"); contrastive X-not-Y / "rather than"; "so Y" reason clauses; stacked comma/appositive lists; phrasal verbs ("ready up", "locked in"); redundant roots one clause apart ("plays for Set Champion at the Set Championship" was caught); Read-more/expandable prose (deleted everywhere); jamming technically-true-but-irrelevant facts to fill space.

## Repeatable process

- **The user writes/approves the words.** State what a section must transmit as a plain fact list, propose 2-4 wording variants when unsure, apply on approval. Never bake in uncertain wording unilaterally.
- **Be genuinely critical on request** — analyze each line for the specific tell, don't skim.
- **Cards mirror real Discord surfaces.** Capture the real card with `!test <state>` on the local test server (user runs it, sends the screenshot), then replicate faithfully with the real accent color and real display names.
- Test roster (fictional, from `HALL_OF_FAME`): Nassif, Finkel, LSV, JED, Paolo, Shota, Reid, Chapin. Arena handles carry `#NNNNN`. `PlayerName` is the reader's stand-in on the pairing card.
- **Verify every product fact against `bot/` first.** `bot/pod-draft-guide.md` is the register model.
- Ship with a running dev server + LAN URL for review; the mobile-heavy tweaks want a real phone on the LAN.

## Implementation notes worth keeping

- **Reuse the real components, don't invent lookalikes.** Podium uses `PodStandingRow`; Seasons uses the same primitives (`SeatAvatar`, matching fonts). `PodStandingRow` gained additive, default-off props for the guide: `trophy`, `dense` (py-1.5 + 28px action button), `iconOnly` (deck icon only, right-aligned), `padX` (gutter override).
- **Points aren't in any DB view.** `public_pod_scoring` exposes trophies/events/wins/losses, not points or finish buckets. Seasons computes points client-side via `aggregatePodStandings(usePodSeasonResults(currentSeason))` — the exact query the `/pods` default board runs, so its react-query cache is reused (no re-query navigating `/pods` → `/pods/guide`). A server-side "top N by points" would need a `points` column on that view.
- **Mobile nav** is a sticky underline-tab bar matching the site's tab pattern, but with an `after:` pseudo underline (not `border-b-2 -mb-px`) because a sticky bar renders a 2px border thin at fractional scroll positions.
- **Section jump** mutes the IntersectionObserver during a programmatic scroll (a per-frame settle poll, not `scrollend`, which fires early on janky scrolls) so passing sections don't flicker the active tab. `scroll-mt` = the sticky bar height (~52px mobile, small on desktop where nothing sticky overlaps).
- `Block` props: `watermark` (opt-in background icon, only How to play), `maxWidthClass`, `titleOnDesktop`, `aside`. Titles: How to play hidden everywhere; on mobile the tab bar is the section label, so only How to play's title is dropped (the rest keep theirs).
- Guide capped at `max-w-[1500px]` for the How-to-play card, `1260px` for the aside blocks. Two-column aside kicks in at `min-[1180px]`, restores the roomy 580/600 layout at `min-[1520px]`.
- Deck screenshots were dropped from the guide by request.

## Kept elsewhere

`docs/guide/pod-coordination.md` is the plain-language player guide of live pod behavior (kept current per the repo CLAUDE.md); unrelated to this page's build.
