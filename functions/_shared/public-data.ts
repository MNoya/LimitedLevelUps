import {
  PUBLIC_SUPABASE_URL,
  PUBLIC_SUPABASE_PUBLISHABLE_KEY,
} from "../../frontend/src/data/public-supabase-config";
import type { SetSummary } from "../../frontend/src/types/leaderboard";

export type SetRow = { code: string; name: string; start_date: string; end_date: string | null; is_active: boolean };

export const SET_ROWS_QUERY = "public_sets?select=code,name,start_date,end_date,is_active&order=code";

export const restGet = (query: string, cacheTtl: number): Promise<Response> =>
  fetch(`${PUBLIC_SUPABASE_URL}/rest/v1/${query}`, {
    headers: {
      apikey: PUBLIC_SUPABASE_PUBLISHABLE_KEY,
      authorization: `Bearer ${PUBLIC_SUPABASE_PUBLISHABLE_KEY}`,
    },
    cf: { cacheTtl, cacheEverything: true },
  });

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

export const toSetSummary = (set: SetRow): SetSummary => ({
  code: set.code,
  name: set.name,
  startDate: set.start_date,
  endDate: set.end_date ?? "",
  isActive: set.is_active,
});
