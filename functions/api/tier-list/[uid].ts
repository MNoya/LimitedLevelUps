// Proxies 17lands' tier-list endpoint, which lacks CORS headers; in dev a vite proxy entry serves the same path
import { TIER_LIST_GRADERS } from "../../../frontend/src/data/constants";

const FETCHED_AT = "x-fetched-at";

export const onRequestGet: PagesFunction = async (context) => {
  const uid = context.params.uid;
  if (typeof uid !== "string" || !/^[0-9a-f]{32}$/.test(uid)) {
    return new Response("Bad uid", { status: 400 });
  }

  const graderUids = Object.values(TIER_LIST_GRADERS).flatMap((graders) => graders.map((g) => g.uid));
  const isGraderList = graderUids.includes(uid);
  const freshSeconds = isGraderList ? 30 * 24 * 60 * 60 : 10 * 60;
  const cacheKey = new Request(new URL(`/api/tier-list/${uid}`, context.request.url).toString());
  const refresh = () => fetchAndStore(uid, cacheKey);

  const hit = await caches.default.match(cacheKey);
  if (hit) {
    const ageSeconds = (Date.now() - Number(hit.headers.get(FETCHED_AT) ?? 0)) / 1000;
    if (ageSeconds > freshSeconds) {
      context.waitUntil(refresh());
    }
    return hit;
  }

  const fetched = await refresh();
  return fetched ?? new Response("Upstream error", { status: 502 });
};

const fetchAndStore = async (uid: string, cacheKey: Request): Promise<Response | null> => {
  const upstream = await fetch(`https://www.17lands.com/data/tier_list/${uid}`, {
    headers: { accept: "application/json" },
  });
  if (!upstream.ok) {
    return null;
  }

  const storedSeconds = 60 * 24 * 60 * 60;
  const response = new Response(await upstream.text(), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": `public, max-age=600, s-maxage=${storedSeconds}`,
      [FETCHED_AT]: String(Date.now()),
    },
  });
  await caches.default.put(cacheKey, response.clone());
  return response;
};
