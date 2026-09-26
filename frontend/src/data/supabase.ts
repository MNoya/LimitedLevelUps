import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import {
  LOCAL_SUPABASE_PUBLISHABLE_KEY,
  LOCAL_SUPABASE_URL,
  PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  PUBLIC_SUPABASE_URL,
} from "./public-supabase-config";

// One explicit switch picks the data source — no commenting credentials in/out:
//   VITE_DATA_MODE=prod   prod Supabase, read-only public_* views (default; deployed builds)
//   VITE_DATA_MODE=local  bot.scripts.local_supabase_proxy on :3001
//   VITE_DATA_MODE=mock   fixtures via mockApi, no network (supabase is null)
// An explicit VITE_SUPABASE_URL + VITE_SUPABASE_PUBLISHABLE_KEY pair overrides prod/local
// for ad-hoc staging; mock always wins. The publishable key is anon, SELECT-only on the
// public_* views, and safe to embed in the client bundle.

const mode = (import.meta.env.VITE_DATA_MODE ?? "prod").toLowerCase();

function resolveConfig(): { url: string; key: string } | null {
  if (mode === "mock") return null;
  const overrideUrl = import.meta.env.VITE_SUPABASE_URL;
  const overrideKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
  if (overrideUrl && overrideKey) return { url: overrideUrl, key: overrideKey };
  if (mode === "local") return { url: LOCAL_SUPABASE_URL, key: LOCAL_SUPABASE_PUBLISHABLE_KEY };
  return { url: PUBLIC_SUPABASE_URL, key: PUBLIC_SUPABASE_PUBLISHABLE_KEY };
}

const config = resolveConfig();

export const supabase: SupabaseClient | null = config
  ? createClient(config.url, config.key, {
      auth: { persistSession: true, flowType: "pkce" },
    })
  : null;

export const useSupabase = supabase !== null;

export const servesEdgeCachedReads = import.meta.env.PROD && config?.url === PUBLIC_SUPABASE_URL;
