// The shared Episode shape plus the title-based category inference, used by the public_episodes
// adapter and by the YouTube overlay. Libsyn carries no per-episode taxonomy, so the bot's sync
// owns categorization and this side only infers for an item it has not classified yet.

export const EPISODE_CATEGORIES = [
  "Set Review",
  "Metagame",
  "Draft",
  "Sealed",
  "Rankings",
  "Coaching",
  "Guest",
  "Evergreen",
] as const;

export type EpisodeCategory = (typeof EPISODE_CATEGORIES)[number];

export function categorySlug(category: EpisodeCategory): string {
  return category.toLowerCase().replace(/\s+/g, "-");
}

const SLUG_TO_CATEGORY: ReadonlyMap<string, EpisodeCategory> = new Map(
  EPISODE_CATEGORIES.map((category) => [categorySlug(category), category]),
);

export function categoryFromSlug(slug: string): EpisodeCategory | null {
  return SLUG_TO_CATEGORY.get(slug.toLowerCase()) ?? null;
}

export type MediaKind = "episode" | "video";


// YouTube Shorts are vertical, ≤3min. This channel's cluster at ≤90s; longer ones (up to 3min)
// are Shorts only when the title carries the hashtag run ("#draft #mtg") that long-form lacks.
const SHORT_MAX_SECONDS = 90;
const SHORT_HASHTAG_MAX_SECONDS = 180;
const SHORT_HASHTAG = /#\w/;

export function isShortMedia(kind: MediaKind, durationSeconds: number, title: string): boolean {
  if (kind !== "video" || durationSeconds <= 0) {
    return false;
  }
  if (durationSeconds <= SHORT_MAX_SECONDS) {
    return true;
  }
  return durationSeconds <= SHORT_HASHTAG_MAX_SECONDS && SHORT_HASHTAG.test(title);
}

export interface Episode {
  id: string;
  kind: MediaKind;
  number: number | null;
  title: string;
  link: string;
  audioUrl: string;
  pubDate: string;
  publishedLabel: string;
  durationLabel: string;
  durationSeconds: number;
  image: string;
  category: EpisodeCategory;
  youtubeId?: string;
  videoUrl?: string;
  setCode?: string | null;
  setName?: string | null;
  setReleasedAt?: string | null;
  isShort: boolean;
}

const COACHING = /coach/i;
const GUEST = /\bconversation with\b|\bjoins (?:me|us)\b|\bft\.?\b|featuring|sits down with|\binterview\b/i;
const RANKINGS = /top \d|top ten|tier ?list|\brank(?:ing|ed)\b|best and worst|props and slops|ranked every|best of \d|worst of/i;
const SET_REVIEW = /set review|set overview|card evaluation|archetype deep dive|commons|uncommons|\brares\b|mythics|signpost|the list/i;
const SEALED = /sealed|pre-?release/i;
const METAGAME = /state of the format|format (?:address|update|breakdown|send|recap)|metagame|\bmeta\b|what we got wrong|win ?rate|tournament report|pro tour/i;
const LEVEL_UP = /level-?up|gameplay mistake|deckbuilding|deck building|mulligan|manabase|mana ?base|fundamentals|\bhabits\b|intuition|mental game|\bsignals\b|card advantage|navigation/i;
const DRAFT = /draft|drafting|\bdeck\b|archetype/i;

// Fallback only — episodes in the LLM-labeled map use that; this covers live/future titles.
export function inferCategory(title: string): EpisodeCategory {
  if (COACHING.test(title)) {
    return "Coaching";
  }
  if (GUEST.test(title)) {
    return "Guest";
  }
  if (RANKINGS.test(title)) {
    return "Rankings";
  }
  if (SET_REVIEW.test(title)) {
    return "Set Review";
  }
  if (SEALED.test(title)) {
    return "Sealed";
  }
  if (METAGAME.test(title)) {
    return "Metagame";
  }
  if (LEVEL_UP.test(title)) {
    return "Evergreen";
  }
  if (DRAFT.test(title)) {
    return "Draft";
  }
  return "Evergreen";
}

const VALID_CATEGORIES: ReadonlySet<string> = new Set(EPISODE_CATEGORIES);

export function categoryFor(title: string, rawCategory: string | null): EpisodeCategory {
  if (rawCategory && VALID_CATEGORIES.has(rawCategory)) {
    return rawCategory as EpisodeCategory;
  }
  return inferCategory(title);
}

export function parseEpisodeNumber(title: string): number | null {
  const match = title.match(/#\s*(\d+)/);
  return match ? Number(match[1]) : null;
}

export function cleanTitle(title: string): string {
  return title.replace(/^(?:llu|limited level-?ups)\s*#?\s*\d+\s*[:\-–]\s*/i, "").trim() || title;
}

export function formatDuration(seconds: number): string {
  if (!seconds) {
    return "";
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function formatDurationShort(seconds: number): string {
  if (!seconds) {
    return "";
  }
  const totalMinutes = Math.round(seconds / 60);
  if (totalMinutes < 60) {
    return `${totalMinutes}m`;
  }
  const halfHours = Math.round(totalMinutes / 30) / 2;
  return `${halfHours}h`;
}

export function formatPublished(pubDate: string): string {
  const date = new Date(pubDate);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export interface DbEpisodeRow {
  guid: string;
  kind: MediaKind;
  number: number | null;
  title: string;
  link: string;
  image: string | null;
  published_at: string;
  duration_seconds: number;
  audio_url: string | null;
  youtube_id: string | null;
  category: string;
  set_code: string | null;
  set_name: string | null;
  set_released_at: string | null;
}

// Authoritative episode rows from the public_episodes view, already categorized and
// set-tagged by the bot's playlist sync. Keyed on guid so the live RSS/YouTube overlay
// can dedupe against them by the same id.
export function adaptDbEpisode(row: DbEpisodeRow): Episode {
  return {
    id: row.guid,
    kind: row.kind,
    number: row.number,
    title: row.title,
    link: row.link,
    audioUrl: row.audio_url ?? "",
    pubDate: row.published_at,
    publishedLabel: formatPublished(row.published_at),
    durationLabel: formatDuration(row.duration_seconds),
    durationSeconds: row.duration_seconds,
    image: row.image ?? "",
    category: categoryFor(row.title, row.category),
    youtubeId: row.youtube_id ?? undefined,
    videoUrl: row.youtube_id ? `https://www.youtube.com/watch?v=${row.youtube_id}` : undefined,
    setCode: row.set_code,
    setName: row.set_name,
    setReleasedAt: row.set_released_at,
    isShort: isShortMedia(row.kind, row.duration_seconds, row.title),
  };
}
