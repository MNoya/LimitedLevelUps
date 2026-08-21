// Mirrors of the curated public_* Postgres views.
// Adapter (data/adapter.ts) converts snake_case rows into these camelCase types.
// Components only ever see this shape; fixtures match it directly.

export interface SetSummary {
  code: string;
  name: string;
  startDate: string; // ISO date
  endDate: string;
  isActive: boolean;
  early?: boolean; // shown before release_date when early-access data already exists
  custom?: boolean;
  // Short display code where the full one is too long for a switcher chip; falls back to `code`
  shortCode?: string;
  // Overrides the symbol derived from `code`, for a board that should read as its family
  glyphCode?: string;
  lastRefreshedAt?: string | null; // when the full active-player refresh last completed for this set
}

export interface PodSetCode {
  code: string;
  label: string | null; // format_label — non-null only for custom cube formats
  // Pods played under this code, so a format tried once does not earn a board
  events: number;
}

export interface CubeSeason {
  setCode: string; // virtual code, e.g. "CUBE-SOS" or "CUBE-PLANAR"
  kind: "season" | "variant"; // a set window of the seasoned cube, or a whole cube
  label: string; // the season's set code ("SOS") or the variant's slug ("PLANAR")
  name: string | null; // the season's set name; null on a variant row
  startDate: string; // the set's release date, or the variant's first event
  firstEvent: string; // first cube event of the season's burst (cube opens after release)
  lastEvent: string; // latest cube event on the board
  events: number;
  players: number;
}

export interface LeaderboardRow {
  setCode: string;
  slug: string;
  displayName: string;
  avatarUrl: string | null;
  rank: number;
  score: number;
  trophies: number;
  events: number;
  wins: number;
  losses: number;
  lastCalculatedAt: string;
  // Populated only on format-scoped boards: boxes for Direct, $ for LCQ
  boxes?: number;
  earnings?: number;
}

export interface PlayerFormatBreakdown {
  setCode: string;
  slug: string;
  formatLabel: string;
  events: number;
  wins: number;
  losses: number;
  trophies: number;
  // Trophies counted by end-of-event rank; equal to trophies outside rank-weighted groups
  weightedTrophies?: number;
  scoreContribution: number;
  twoWins?: number;
  oneWins?: number;
}

export interface PlayerDraftEvent {
  slug: string;
  setCode: string;
  eventId: string;
  seventeenlandsEventId?: string | null;
  format: string;
  expansion: string;
  wins: number;
  losses: number;
  isTrophy: boolean;
  colors: string; // 17lands convention: uppercase = main, lowercase = splash
  startedAt: string | null;
  finishedAt: string | null;
  // 17lands deck URL for 17L events, Draftmancer draft log for pod drafts, null if no link
  externalUrl?: string | null;
  // Pod draft event name (e.g. "Pod Draft #3"). Null for 17lands rows
  eventName?: string | null;
  // Pod draft event slug for /pods/<slug>. Null for 17lands rows
  podEventSlug?: string | null;
  // Arena rank when the event finished ("Gold-3", "Mythic-1"). Null for pod rows
  endRank?: string | null;
  // Opaque player_accounts id, so one Arena account's drafts separate from another's.
  // Null for pod rows, and absent unless the caller selected it
  accountId?: number | null;
  // Fetched once from 17lands and stored beside the event; absent unless selected
  poolRares?: number | null;
  poolMythics?: number | null;
  deckCards?: { maindeck?: TrackedCard[]; sideboard?: TrackedCard[] } | null;
  matchResults?: TrackedMatch[] | null;
}

export interface TrackedCard {
  name: string;
  rarity: string;
}

export interface TrackedMatch {
  match_number: number;
  won: boolean | null;
  opponent_colors: string | null;
  games: Array<{ on_play: boolean | null; won: boolean | null }>;
}

export interface ColorsLeaderboardRow {
  setCode: string;
  colors: string; // 'WR', 'WUBR', 'MULTI', '' for colorless
  slug: string;
  displayName: string;
  avatarUrl: string | null;
  rank: number;
  score: number;
  trophies: number;
  events: number;
  wins: number;
  losses: number;
  lastCalculatedAt: string;
  boxes?: number;
  earnings?: number;
}

export interface ColorsSummary {
  setCode: string;
  colors: string;
  trophies: number;
  events: number;
  players: number;
  // LCQ Day 2 cash summed per combo; only set on the LCQ-scoped sidebar
  earnings?: number;
}

// Recent trophy event, enriched with the player's display name. In production
// this comes from a `public_recent_trophies` view that joins draft_events
// (where is_trophy = true) with players, ordered by finished_at DESC.
export interface RecentTrophy {
  setCode: string;
  slug: string;
  displayName: string;
  avatarUrl: string | null;
  seventeenlandsEventId?: string | null;
  format: string;
  colors: string;
  wins: number;
  losses: number;
  finishedAt: string;
  // false only for LCQ Day 2 runs merged into the LCQ-scoped list
  isTrophy?: boolean;
  // Arena rank when the trophy run finished ("Gold-3", "Mythic-1")
  endRank?: string | null;
}

export type PodEventKind = "tournament" | "mock";

export interface PodEventSummary {
  eventId: string;
  slug: string;
  name: string;
  setCode: string;
  kind: PodEventKind;
  eventDate: string;
  eventTime: string;
  formatLabel: string | null;
  totalRounds: number;
  championPlayerSlug: string | null;
  championDisplayName: string | null;
  championAvatarUrl: string | null;
  championDeckColors: string | null;
  championRecord: string | null;
  participantCount: number;
  isFinalized: boolean;
  // Execution-ordered milestone number, null until the pod has run; tables share it and split on tableIndex
  ordinal?: number | null;
  tableIndex?: number;
  isTeamDraft?: boolean;
  // Hides decklists + pick-by-pick draft log on the site until the pod finishes
  closedDecklist?: boolean;
}

export interface MainboardCard {
  name: string;
  cn: string | null;
  set?: string; // present only when the card's set differs from the deck-level set
  colors?: string[]; // omitted when colorless
  cmc: number | null;
  type: string | null;
  count?: number; // omitted when 1
}

// A built deck resolved for rendering: nonbasic spells grouped by name with counts, sorted by mana
// value. Derived client-side from a draft artifact; basics are absent (they are never drafted).
export interface Mainboard {
  set: string | null; // deck-level default set; cards inherit it unless they carry their own
  cards: MainboardCard[];
  sideboard: MainboardCard[];
}

// One entry of the artifact card table, addressed by its position in `cards`.
export interface ArtifactCard {
  n: string | null; // name
  cn: string | null; // collector number
  s: string | null; // set
  r: string | null; // rarity
  c: string[] | null; // colors
  cmc: number | null;
  type: string | null;
}

// The canonical pod draft artifact from public_pod_draft_log. Everything references the card table
// by index. `decks` is null for events drafted before deck capture existed.
export interface PodDraftArtifact {
  t?: number;
  v: number;
  sid?: string;
  set: string | null;
  seats: string[]; // Draftmancer names; array index === participant seatIndex
  cards: ArtifactCard[];
  packs: number[][]; // boosters as card indices
  picks: number[][][]; // [seat][pack][pickOrder] -> card index
  pp?: number; // cards taken per turn; absent on artifacts written before Pick 2 existed
  decks: { main: number[]; side: number[] }[] | null;
}

export interface PodEventParticipantRow {
  eventId: string;
  displayName: string;
  draftmancerName: string | null;
  seatIndex: number | null;
  placement: number | null;
  record: string | null;
  deckColors: string | null;
  deckScreenshotUrl: string | null;
  deckScreenshotCaption: string | null;
  playerSlug: string | null;
  playerDisplayName: string | null;
  avatarUrl: string | null;
}

export interface PodEventMatchRow {
  eventId: string;
  eventName: string;
  round: number;
  playerAName: string;
  playerBName: string;
  winnerName: string | null;
  score: string | null;
  reportedAt: string | null;
}

export interface PodSeat extends PodEventParticipantRow {
  seatIndex: number;
  discordName: string;
  hasDeckList?: boolean;
}

export interface PodEventReplayRow {
  eventId: string;
  eventName: string;
  eventDate: string;
  setCode: string;
  playerId: string;
  playerSlug: string;
  playerDisplayName: string;
  gameId: string;
  link: string;
  gameTime: string;
  won: boolean;
  turns: number | null;
  onPlay: boolean | null;
  inferredRound: number | null;
}

// One player's finish in one pod, carrying the pod's own format so a season can be sliced by it
export interface PodSeasonResultRow {
  eventId: string;
  setCode: string;
  eventTime: string;
  slug: string;
  displayName: string;
  avatarUrl: string | null;
  placement: number | null;
  wins: number;
  losses: number;
}

export interface PodLeaderboardRow {
  setCode: string;
  rank: number;
  slug: string;
  displayName: string;
  avatarUrl: string | null;
  events: number;
  wins: number;
  losses: number;
  trophies: number;
  points?: number;
  lastFinishedAt: string | null;
}

// View-shape composite used by the player profile page.
export interface PlayerIdentity {
  slug: string;
  displayName: string;
  avatarUrl: string | null;
}

// Unverified draft result a player logged via /trophy from a trophy-hype post. Showcase only —
// never scored. isTrophy marks a trophy (a full run win) versus a non-trophy deck logged anyway.
// colors uses the 17lands convention (uppercase main, lowercase splash); '' for none.
export interface SelfReportedEvent {
  setCode: string;
  record: string;
  isTrophy: boolean;
  colors: string;
  platform: string;
  // Player-declared draft format; null on rows logged before the field existed
  format: string | null;
  // The player's original post text, kept as a keepsake shown with the deck
  caption: string | null;
  // Discord CDN URL; refreshed browser-side via the message ref when its signed expiry lapses
  screenshotUrl: string | null;
  sourceChannelId: string;
  sourceMessageId: string;
  sourceUrl: string;
  reportedAt: string;
}

// One player's standing on an MTGO-only trophy-count board, aggregated from self-reported results
// for a flashback set. Ranked by trophy count; decks holds every logged post (trophy or not),
// newest first, and deckCount is that full tally.
export interface TrophyLeaderboardRow {
  setCode: string;
  slug: string;
  displayName: string;
  avatarUrl: string | null;
  rank: number;
  trophies: number;
  deckCount: number;
  decks: SelfReportedEvent[];
}

export interface PlayerProfile {
  slug: string;
  displayName: string;
  avatarUrl: string | null;
  setCode: string;
  rank: number;
  score: number;
  trophies: number;
  events: number;
  wins: number;
  losses: number;
  linked17lands: boolean;
  lastCalculatedAt?: string | null; // when this player's data was last pulled from 17lands
  formatBreakdown: PlayerFormatBreakdown[];
  selfReportedEvents: SelfReportedEvent[];
}
