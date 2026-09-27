import { CARD_STATS_SETS } from "../../../frontend/src/data/constants";
import { type CardStatsFile, fetchCardStatsFile } from "../../../frontend/src/data/cardStats";
import { serveStaleWhileRefreshing } from "../../_shared/stale-cache";

interface Env {
  ASSETS: Fetcher;
  CARD_STATS?: KVNamespace;
}

const ONE_HOUR = 60 * 60;

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
  const localFreshSeconds = shared ? 15 * 60 : ONE_HOUR;
  return serveStaleWhileRefreshing(context, `/api/card-stats/${setCode}`, localFreshSeconds, async (previous) => {
    if (!shared) {
      const previousFile = previous ? ((await previous.json()) as CardStatsFile) : null;
      return JSON.stringify(await fetchCardStatsFile(setCode, previousFile));
    }
    return sharedCardStats(shared, setCode);
  });
};

const sharedCardStats = async (shared: KVNamespace, setCode: string): Promise<string> => {
  const stored = await shared.getWithMetadata<{ fetchedAt: number }>(setCode);
  const fetchedAt = stored.metadata?.fetchedAt ?? 0;
  if (stored.value !== null && Date.now() - fetchedAt < ONE_HOUR * 1000) {
    return stored.value;
  }

  const previousFile = stored.value === null ? null : (JSON.parse(stored.value) as CardStatsFile);
  const body = JSON.stringify(await fetchCardStatsFile(setCode, previousFile));
  await shared.put(setCode, body, { metadata: { fetchedAt: Date.now() } });
  return body;
};
