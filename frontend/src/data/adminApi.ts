// Admin-only writes to the bot's HTTP API. Local dev hits the no-auth proxy; prod sends the
// signed-in admin's Supabase access token, which the bot validates against its admin allowlist.

import { DEV_AUTH_USER } from "./devAuth";
import { supabase } from "./supabase";
import type { TranscriptSegment } from "./transcript";
import { LOCAL_SUPABASE_URL, PUBLIC_BOT_API_URL } from "./public-supabase-config";

async function postAdmin(path: string, body: unknown): Promise<unknown> {
  const mode = (import.meta.env?.VITE_DATA_MODE ?? "prod").toLowerCase();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  let base: string;
  // A dev identity has no real Supabase session, so it writes through the no-auth proxy
  if (mode === "local" || DEV_AUTH_USER) {
    base = LOCAL_SUPABASE_URL.replace(/\/$/, "");
  } else {
    base = PUBLIC_BOT_API_URL.replace(/\/$/, "");
    if (!supabase) throw new Error("Not authenticated");
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) throw new Error("Not authenticated");
    headers.Authorization = `Bearer ${token}`;
  }
  const resp = await fetch(`${base}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  if (!resp.ok) {
    let message = `Save failed (${resp.status})`;
    try {
      const parsed = await resp.json();
      if (parsed?.error) {
        message = parsed.error;
      }
    } catch {
      // response had no JSON body
    }
    throw new Error(message);
  }
  return resp.json();
}

export async function saveTranscript(key: string, segments: TranscriptSegment[]): Promise<TranscriptSegment[]> {
  const result = (await postAdmin(`/episodes/${encodeURIComponent(key)}/transcript`, segments)) as {
    segments?: TranscriptSegment[];
  };
  return result.segments ?? segments;
}
