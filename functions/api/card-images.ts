// Resolves a draft's exact cards to base-printing CDN image URLs server-side, so the browser renders
// card art straight from cards.scryfall.io without ever hitting Scryfall's rate-limited API. Uses
// Scryfall's collection batch (75 cards per request), so a cube spanning dozens of sets still resolves
// in a handful of requests. The response is edge-cached (Cache API) keyed by a hash of the card set, so
// the same draft/cube is resolved once and shared across viewers. No database.
// The dev equivalent lives in frontend/vite.config.ts (mirrors this, like the youtube endpoint).

const CACHE_SECONDS = 604800; // 7 days
const CHUNK = 75;
const COLLECTION_URL = "https://api.scryfall.com/cards/collection";

interface Identifier {
  name: string;
  set: string;
}

interface ScryfallCard {
  name: string;
  set: string;
  image_uris?: { grid?: string };
  card_faces?: { image_uris?: { grid?: string } }[];
}

function frontFaceName(name: string): string {
  const separator = name.indexOf("//");
  return (separator === -1 ? name : name.slice(0, separator)).trim();
}

function gridImage(card: ScryfallCard): string | null {
  return card.image_uris?.grid ?? card.card_faces?.[0]?.image_uris?.grid ?? null;
}

function normalize(raw: unknown): Identifier[] {
  const list = Array.isArray((raw as { identifiers?: unknown })?.identifiers)
    ? ((raw as { identifiers: unknown[] }).identifiers as { name?: unknown; set?: unknown }[])
    : [];
  const byKey = new Map<string, Identifier>();
  for (const item of list) {
    if (typeof item?.name !== "string" || typeof item?.set !== "string") {
      continue;
    }
    const name = frontFaceName(item.name);
    const set = item.set.toLowerCase();
    byKey.set(`${set}|${name.toLowerCase()}`, { name, set });
  }
  return [...byKey.values()].sort((a, b) => `${a.set}|${a.name}`.localeCompare(`${b.set}|${b.name}`));
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function fetchChunkWithRetry(chunk: Identifier[], attempt = 0): Promise<Response> {
  try {
    const res = await fetch(COLLECTION_URL, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json", "user-agent": "LimitedLevelUps/1.0" },
      body: JSON.stringify({ identifiers: chunk.map((id) => ({ name: id.name, set: id.set })) }),
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

export const onRequestPost: PagesFunction = async (context) => {
  const { request } = context;
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return new Response("Bad body", { status: 400 });
  }
  const identifiers = normalize(body);
  if (identifiers.length === 0) {
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  }

  const cache = caches.default;
  const hash = await sha256Hex(JSON.stringify(identifiers));
  const cacheKey = new Request(new URL(`/api/card-images/grid/${hash}`, request.url).toString());
  const cached = await cache.match(cacheKey);
  if (cached) {
    return cached;
  }

  const map: Record<string, string> = {};
  for (let i = 0; i < identifiers.length; i += CHUNK) {
    const res = await fetchChunkWithRetry(identifiers.slice(i, i + CHUNK));
    if (!res.ok) {
      continue;
    }
    const page = (await res.json()) as { data?: ScryfallCard[] };
    for (const card of page.data ?? []) {
      const image = gridImage(card);
      if (image) {
        map[`${card.set.toLowerCase()}|${frontFaceName(card.name).toLowerCase()}`] = image;
      }
    }
  }

  const response = new Response(JSON.stringify(map), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": `public, max-age=${CACHE_SECONDS}` },
  });
  context.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
};
