// Pulls the channel's full uploads catalog from the YouTube Data API v3, which
// needs a key the browser can't carry. Resolves the handle to its uploads
// playlist, pages through it, and returns normalized items. Edge-cached so the
// quota cost stays near zero. In dev the same path is served by a vite plugin.
interface Env {
  YOUTUBE_API_KEY: string;
}

const CHANNEL_HANDLE = "limitedlevel-ups";
const MAX_PAGES = 10;
const API = "https://www.googleapis.com/youtube/v3";

export const onRequestGet: PagesFunction<Env> = async (context) => {
  // ?recent returns just the newest page for the homepage hero; the bare path returns the full archive
  const url = new URL(context.request.url);
  const recent = url.searchParams.has("recent");

  // Edge-cache the function's own response, not just upstream fetches, so visitors don't each re-run the crawl
  const cache = caches.default;
  const cacheKey = new Request(`${url.origin}/api/youtube${recent ? "?recent" : ""}`);
  const hit = await cache.match(cacheKey);
  if (hit) {
    return hit;
  }

  const key = context.env.YOUTUBE_API_KEY;
  if (!key) {
    return new Response("Missing YOUTUBE_API_KEY", { status: 500 });
  }

  const uploads = await resolveUploadsPlaylist(key);
  if (!uploads) {
    return new Response("Could not resolve uploads playlist", { status: 502 });
  }

  const videos = await fetchPlaylist(uploads, key, recent ? 1 : MAX_PAGES);
  await attachDurations(videos, key);
  const hasVideos = videos.length > 0;
  const response = new Response(JSON.stringify({ videos }), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": hasVideos ? "public, max-age=3600" : "no-store",
    },
  });
  if (hasVideos) {
    context.waitUntil(cache.put(cacheKey, response.clone()));
  }
  return response;
};

async function resolveUploadsPlaylist(key: string): Promise<string | null> {
  const url = `${API}/channels?part=contentDetails&forHandle=${CHANNEL_HANDLE}&key=${key}`;
  const res = await fetch(url, { cf: { cacheTtl: 86400, cacheEverything: true } });
  if (!res.ok) {
    return null;
  }
  const json = (await res.json()) as YouTubeChannelResponse;
  return json.items?.[0]?.contentDetails?.relatedPlaylists?.uploads ?? null;
}

async function fetchPlaylist(playlistId: string, key: string, maxPages: number): Promise<NormalizedVideo[]> {
  const videos: NormalizedVideo[] = [];
  let pageToken = "";
  for (let page = 0; page < maxPages; page += 1) {
    const url =
      `${API}/playlistItems?part=snippet&maxResults=50&playlistId=${playlistId}&key=${key}` +
      (pageToken ? `&pageToken=${pageToken}` : "");
    const res = await fetch(url, { cf: { cacheTtl: 3600, cacheEverything: true } });
    if (!res.ok) {
      break;
    }
    const json = (await res.json()) as YouTubePlaylistResponse;
    for (const item of json.items ?? []) {
      const video = normalize(item);
      if (video) {
        videos.push(video);
      }
    }
    if (!json.nextPageToken) {
      break;
    }
    pageToken = json.nextPageToken;
  }
  return videos;
}

function normalize(item: YouTubePlaylistItem): NormalizedVideo | null {
  const snippet = item.snippet;
  const videoId = snippet?.resourceId?.videoId;
  const title = snippet?.title ?? "";
  if (!videoId || title === "Private video" || title === "Deleted video") {
    return null;
  }
  const thumbs = snippet?.thumbnails ?? {};
  const best = thumbs.maxres ?? thumbs.standard ?? thumbs.high ?? thumbs.medium ?? thumbs.default;
  return {
    id: videoId,
    title,
    publishedAt: snippet?.publishedAt ?? "",
    description: snippet?.description ?? "",
    thumbnail: best?.url ?? "",
    duration: "",
  };
}

async function attachDurations(videos: NormalizedVideo[], key: string): Promise<void> {
  for (let start = 0; start < videos.length; start += 50) {
    const chunk = videos.slice(start, start + 50);
    const ids = chunk.map((video) => video.id).join(",");
    const url = `${API}/videos?part=contentDetails&id=${ids}&key=${key}`;
    const res = await fetch(url, { cf: { cacheTtl: 3600, cacheEverything: true } });
    if (!res.ok) {
      continue;
    }
    const json = (await res.json()) as YouTubeVideoDetailsResponse;
    const byId = new Map<string, string>();
    for (const item of json.items ?? []) {
      if (item.id) {
        byId.set(item.id, item.contentDetails?.duration ?? "");
      }
    }
    for (const video of chunk) {
      video.duration = byId.get(video.id) ?? "";
    }
  }
}

interface NormalizedVideo {
  id: string;
  title: string;
  publishedAt: string;
  description: string;
  thumbnail: string;
  duration: string;
}

interface YouTubeVideoDetailsResponse {
  items?: Array<{ id?: string; contentDetails?: { duration?: string } }>;
}

interface YouTubeChannelResponse {
  items?: Array<{ contentDetails?: { relatedPlaylists?: { uploads?: string } } }>;
}

interface YouTubePlaylistResponse {
  items?: YouTubePlaylistItem[];
  nextPageToken?: string;
}

interface YouTubePlaylistItem {
  snippet?: {
    title?: string;
    description?: string;
    publishedAt?: string;
    resourceId?: { videoId?: string };
    thumbnails?: Record<string, { url?: string } | undefined>;
  };
}
