// YouTube uploads pulled through the /api/youtube proxy (Cloudflare Function in
// prod, a vite dev plugin locally) since the Data API key can't ride in the
// browser. The proxy hands back already-normalized items; here we map them to
// the shared Episode shape and overlay the ones the bot's sync has not yet
// matched to a podcast row, so they surface as "video" cards in the same grid.

import {
  cleanTitle,
  formatDuration,
  formatPublished,
  inferCategory,
  isShortMedia,
  parseEpisodeNumber,
  type Episode,
} from "./episodes";

export const YOUTUBE_API_URL = "/api/youtube";

export interface YouTubeVideo {
  id: string;
  title: string;
  publishedAt: string;
  thumbnail: string;
  duration?: string;
}

export async function fetchYouTubeVideos(recent = false): Promise<YouTubeVideo[]> {
  const res = await fetch(recent ? `${YOUTUBE_API_URL}?recent` : YOUTUBE_API_URL);
  if (!res.ok) {
    throw new Error(`YouTube proxy responded ${res.status}`);
  }
  const json = (await res.json()) as { videos?: YouTubeVideo[] };
  return json.videos ?? [];
}

// DB rows are authoritative (categorized, set-tagged, thumbnails matched). A video the bot has not
// synced yet overlays on top so a just-dropped upload shows up before the next sync, deduped against
// the DB by guid and by matched youtube id, and stamped with the latest release set as a best guess
// until the bot resolves the real one.
export function overlayLiveMedia(db: Episode[], live: Episode[]): Episode[] {
  const dbIds = new Set(db.map((e) => e.id));
  const dbYoutubeIds = new Set(db.map((e) => e.youtubeId).filter(Boolean));
  const assumedSet = latestReleaseSet(db);
  const fresh = live
    .filter((e) => !dbIds.has(e.id) && !(e.youtubeId && dbYoutubeIds.has(e.youtubeId)))
    .map((e) => withAssumedSet(e, assumedSet));
  return [...db, ...fresh].sort((a, b) => new Date(b.pubDate).getTime() - new Date(a.pubDate).getTime());
}

// The set the newest set-tagged episode belongs to — what the bot's resolve_set would give a
// brand-new same-era drop. Tracks the previewing set, not the leaderboard's active set, which
// keeps running the prior set through a release window. Set-agnostic content has a null set_code.
function latestReleaseSet(db: Episode[]): Episode | undefined {
  let latest: Episode | undefined;
  for (const episode of db) {
    if (!episode.setCode) {
      continue;
    }
    if (!latest || new Date(episode.pubDate).getTime() > new Date(latest.pubDate).getTime()) {
      latest = episode;
    }
  }
  return latest;
}

function withAssumedSet(episode: Episode, source: Episode | undefined): Episode {
  if (!source || episode.setCode || episode.category === "Evergreen") {
    return episode;
  }
  return {
    ...episode,
    setCode: source.setCode,
    setName: source.setName,
    setReleasedAt: source.setReleasedAt,
  };
}

export function toVideoEpisode(video: YouTubeVideo): Episode {
  const durationSeconds = parseIsoDuration(video.duration);
  return {
    id: `yt:${video.id}`,
    kind: "video",
    number: parseEpisodeNumber(video.title),
    title: cleanTitle(video.title),
    link: watchUrl(video.id),
    audioUrl: "",
    pubDate: video.publishedAt,
    publishedLabel: formatPublished(video.publishedAt),
    durationLabel: formatDuration(durationSeconds),
    durationSeconds,
    image: video.thumbnail,
    category: inferCategory(video.title),
    youtubeId: video.id,
    videoUrl: watchUrl(video.id),
    isShort: isShortMedia("video", durationSeconds, video.title),
  };
}

function parseIsoDuration(iso: string | undefined): number {
  if (!iso) {
    return 0;
  }
  const match = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!match) {
    return 0;
  }
  const [, hours, minutes, seconds] = match;
  return Number(hours ?? 0) * 3600 + Number(minutes ?? 0) * 60 + Number(seconds ?? 0);
}

function watchUrl(id: string): string {
  return `https://www.youtube.com/watch?v=${id}`;
}

