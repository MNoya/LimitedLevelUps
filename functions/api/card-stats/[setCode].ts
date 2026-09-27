import { CARD_STATS_SETS } from "../../../frontend/src/data/constants";
import { serveStaleWhileRefreshing } from "../../_shared/stale-cache";

interface Env {
  ASSETS: Fetcher;
  CARD_STATS?: KVNamespace;
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
  const setCode = String(context.params.setCode).toUpperCase();
  if (!CARD_STATS_SETS.includes(setCode)) {
    return new Response("No card stats for this set", { status: 404 });
  }

  const bakedUrl = new URL(`/card-stats/${setCode.toLowerCase()}.json`, context.request.url);
  const baked = await context.env.ASSETS.fetch(bakedUrl);
  if (baked.ok && baked.headers.get("content-type")?.includes("application/json")) {
    return new Response(baked.body, {
      headers: { "content-type": "application/json", "cache-control": "public, max-age=86400" },
    });
  }

  const shared = context.env.CARD_STATS;
  const fifteenMinutes = 15 * 60;
  return serveStaleWhileRefreshing(context, `/api/card-stats/${setCode}`, fifteenMinutes, async () => {
    const stored = shared ? await shared.get(setCode) : null;
    return stored ?? JSON.stringify({ set: setCode, updatedAt: new Date().toISOString(), cards: {} });
  });
};
