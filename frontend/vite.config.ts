import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    base: "/",
    plugins: [react(), youtubeDevApi(env.YOUTUBE_API_KEY), cardImagesDevApi()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
    server: {
      port: 5173,
      proxy: {
        "/api/tier-list": {
          target: "https://www.17lands.com",
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api\/tier-list/, "/data/tier_list"),
        },
      },
      allowedHosts: [".ngrok-free.dev", ".ngrok-free.app", ".trycloudflare.com"]
    },
  };
});

// Dev-only stand-in for functions/api/card-images.ts, which serves the same map in production (mirrors
// that logic, the same way the youtube dev/prod endpoints do).
const CHUNK = 75;
const COLLECTION_URL = "https://api.scryfall.com/cards/collection";

function cardImagesDevApi(): Plugin {
  return {
    name: "card-images-dev-api",
    configureServer(server) {
      server.middlewares.use("/api/card-images", async (req, res) => {
        res.setHeader("content-type", "application/json");
        if (req.method !== "POST") {
          res.statusCode = 405;
          res.end("{}");
          return;
        }
        try {
          const chunks: Buffer[] = [];
          for await (const chunk of req) {
            chunks.push(chunk as Buffer);
          }
          const body = JSON.parse(Buffer.concat(chunks).toString() || "{}");
          res.end(JSON.stringify(await resolveCardImages(body)));
        } catch {
          res.statusCode = 502;
          res.end("{}");
        }
      });
    },
  };
}

function frontFaceName(name: string): string {
  const separator = name.indexOf("//");
  return (separator === -1 ? name : name.slice(0, separator)).trim();
}

async function fetchChunkWithRetry(chunk: { name: string; set: string }[], attempt = 0): Promise<Response> {
  try {
    const res = await fetch(COLLECTION_URL, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json", "user-agent": "LimitedLevelUps/1.0" },
      body: JSON.stringify({ identifiers: chunk }),
    });
    if (res.status === 429 && attempt < 4) {
      await new Promise((resolve) => setTimeout(resolve, 500 * (attempt + 1)));
      return fetchChunkWithRetry(chunk, attempt + 1);
    }
    return res;
  } catch (error) {
    if (attempt < 4) {
      await new Promise((resolve) => setTimeout(resolve, 500 * (attempt + 1)));
      return fetchChunkWithRetry(chunk, attempt + 1);
    }
    throw error;
  }
}

async function resolveCardImages(body: { identifiers?: { name?: unknown; set?: unknown }[] }): Promise<Record<string, string>> {
  const byKey = new Map<string, { name: string; set: string }>();
  for (const item of Array.isArray(body?.identifiers) ? body.identifiers : []) {
    if (typeof item?.name !== "string" || typeof item?.set !== "string") {
      continue;
    }
    const name = frontFaceName(item.name);
    const set = item.set.toLowerCase();
    byKey.set(`${set}|${name.toLowerCase()}`, { name, set });
  }
  const identifiers = Array.from(byKey.values());
  const map: Record<string, string> = {};
  for (let i = 0; i < identifiers.length; i += CHUNK) {
    const res = await fetchChunkWithRetry(identifiers.slice(i, i + CHUNK));
    if (!res.ok) {
      continue;
    }
    const page = (await res.json()) as { data?: any[] };
    for (const card of page.data ?? []) {
      const image = card.image_uris?.normal ?? card.card_faces?.[0]?.image_uris?.normal ?? null;
      if (image) {
        map[`${card.set.toLowerCase()}|${frontFaceName(card.name).toLowerCase()}`] = image;
      }
    }
  }
  return map;
}

const CHANNEL_HANDLE = "limitedlevel-ups";
const YOUTUBE_API = "https://www.googleapis.com/youtube/v3";

function youtubeDevApi(key: string | undefined): Plugin {
  return {
    name: "youtube-dev-api",
    configureServer(server) {
      server.middlewares.use("/api/youtube", async (req, res) => {
        res.setHeader("content-type", "application/json");
        res.setHeader("cache-control", "public, max-age=3600");
        if (!key) {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: "Set YOUTUBE_API_KEY in frontend/.env to use /api/youtube in dev" }));
          return;
        }
        try {
          const recent = new URL(req.url ?? "", "http://localhost").searchParams.has("recent");
          const videos = await fetchUploads(key, recent ? 1 : 10);
          res.end(JSON.stringify({ videos }));
        } catch (error) {
          res.statusCode = 502;
          res.end(JSON.stringify({ error: String(error) }));
        }
      });
    },
  };
}

async function fetchUploads(key: string, maxPages: number) {
  const channelUrl = `${YOUTUBE_API}/channels?part=contentDetails&forHandle=${CHANNEL_HANDLE}&key=${key}`;
  const channelRes = await fetch(channelUrl);
  const channelJson = await channelRes.json();
  const uploads = channelJson?.items?.[0]?.contentDetails?.relatedPlaylists?.uploads;
  if (!uploads) {
    throw new Error("Could not resolve uploads playlist");
  }

  const videos: Array<Record<string, string>> = [];
  let pageToken = "";
  for (let page = 0; page < maxPages; page += 1) {
    const url =
      `${YOUTUBE_API}/playlistItems?part=snippet&maxResults=50&playlistId=${uploads}&key=${key}` +
      (pageToken ? `&pageToken=${pageToken}` : "");
    const res = await fetch(url);
    const json = await res.json();
    for (const item of json.items ?? []) {
      const snippet = item.snippet ?? {};
      const videoId = snippet.resourceId?.videoId;
      const title = snippet.title ?? "";
      if (!videoId || title === "Private video" || title === "Deleted video") {
        continue;
      }
      const thumbs = snippet.thumbnails ?? {};
      const best = thumbs.maxres ?? thumbs.standard ?? thumbs.high ?? thumbs.medium ?? thumbs.default;
      videos.push({
        id: videoId,
        title,
        publishedAt: snippet.publishedAt ?? "",
        description: snippet.description ?? "",
        thumbnail: best?.url ?? "",
        duration: "",
      });
    }
    if (!json.nextPageToken) {
      break;
    }
    pageToken = json.nextPageToken;
  }
  await attachDurations(videos, key);
  return videos;
}

async function attachDurations(videos: Array<Record<string, string>>, key: string) {
  for (let start = 0; start < videos.length; start += 50) {
    const chunk = videos.slice(start, start + 50);
    const ids = chunk.map((video) => video.id).join(",");
    const res = await fetch(`${YOUTUBE_API}/videos?part=contentDetails&id=${ids}&key=${key}`);
    const json = await res.json();
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
