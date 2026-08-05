// Public Supabase configuration — these values ARE the client-side bundle's
// credentials and are designed to be visible in every browser that loads the
// site. They are NOT secrets. Checking them in matches their actual security
// posture and removes a deploy-time configuration step.
//
// Why this is safe:
//   1. The URL is the project's public REST endpoint.
//   2. The "publishable" key is Supabase's browser-facing anon credential.
//      Per https://supabase.com/docs/guides/api/api-keys it is designed to be
//      embedded in client bundles. The legacy name was "anon JWT".
//   3. All data access is gated by Row-Level Security on the underlying tables
//      and SELECT-only grants on the curated public_* views. The publishable
//      key cannot read base tables, write anything, or escalate to
//      service-role access.
//
// To rotate: replace the publishable key in Supabase dashboard → Settings →
// API → Publishable key, then update the constant below. The previous key
// continues working for ~5 minutes; the rotation is non-breaking.
//
// Pick the data source with VITE_DATA_MODE (prod | local | mock) — see supabase.ts.
// An explicit VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY pair still overrides
// these defaults for ad-hoc staging targets, so contributors don't edit this file.

export const PUBLIC_SUPABASE_URL = "https://yrecdosksgigpceholjl.supabase.co";

export const PUBLIC_SUPABASE_PUBLISHABLE_KEY =
  "sb_publishable_x-W4800MtS_hbFAnLmAk6Q_68P4Nxsf";

// Dev defaults for bot.scripts.local_supabase_proxy, so VITE_DATA_MODE=local needs no
// credentials. Never used by production builds. The proxy host tracks whatever host serves
// the page (localhost on this machine, the LAN IP from a phone), so local mode works from a
// phone with no config as long as the proxy is bound to 0.0.0.0. VITE_LOCAL_SUPABASE_URL still
// overrides for an off-box proxy.
const localProxyHost = typeof window !== "undefined" ? window.location.hostname : "localhost";
export const LOCAL_SUPABASE_URL =
  import.meta.env?.VITE_LOCAL_SUPABASE_URL ?? `http://${localProxyHost}:3001`;

export const LOCAL_SUPABASE_PUBLISHABLE_KEY = "dev-anon-key";
