import {
  PUBLIC_SUPABASE_URL,
  PUBLIC_SUPABASE_PUBLISHABLE_KEY,
} from "../../frontend/src/data/public-supabase-config";
import type { SetSummary } from "../../frontend/src/types/leaderboard";

export type SetRow = { code: string; name: string; start_date: string; end_date: string | null; is_active: boolean };

export const SET_ROWS_QUERY = "public_sets?select=code,name,start_date,end_date,is_active&order=code";

export const restGet = async (query: string, cacheTtl: number): Promise<Response> => {
  const url = `${PUBLIC_SUPABASE_URL}/rest/v1/${query}`;
  const cacheKey = new Request(url);
  const hit = await caches.default.match(cacheKey);
  if (hit) {
    return hit;
  }

  const upstream = await fetch(url, {
    headers: {
      apikey: PUBLIC_SUPABASE_PUBLISHABLE_KEY,
      authorization: `Bearer ${PUBLIC_SUPABASE_PUBLISHABLE_KEY}`,
    },
  });
  if (!upstream.ok) {
    return upstream;
  }
  const response = new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": "application/json", "cache-control": `public, max-age=${cacheTtl}` },
  });
  await caches.default.put(cacheKey, response.clone());
  return response;
};

export const restRows = async <T>(query: string, cacheTtl: number): Promise<T[] | null> => {
  try {
    const resp = await restGet(query, cacheTtl);
    if (!resp.ok) {
      return null;
    }
    return (await resp.json()) as T[];
  } catch {
    return null;
  }
};

export const restPassthrough = async (query: string, cacheTtl: number): Promise<Response> => {
  const upstream = await restGet(query, cacheTtl);
  if (!upstream.ok) {
    return new Response("Upstream error", { status: 502 });
  }
  return new Response(upstream.body, {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": `public, max-age=${cacheTtl}` },
  });
};

export const toSetSummary = (set: SetRow): SetSummary => ({
  code: set.code,
  name: set.name,
  startDate: set.start_date,
  endDate: set.end_date ?? "",
  isActive: set.is_active,
});
