// Signed-in calls to the bot's HTTP API; local dev hits the no-auth proxy, prod sends the Supabase access token

import { DEV_AUTH_USER } from "./devAuth";
import { supabase } from "./supabase";
import type { TranscriptSegment } from "./transcript";
import type { DeckSplit } from "../types/leaderboard";
import { LOCAL_SUPABASE_URL, PUBLIC_BOT_API_URL } from "./public-supabase-config";

async function postAdmin(path: string, body: unknown): Promise<unknown> {
  return callBot(path, { method: "POST", body: JSON.stringify(body) });
}

async function callBot(path: string, init: RequestInit): Promise<unknown> {
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
  const resp = await fetch(`${base}${path}`, { ...init, headers });
  if (!resp.ok) {
    throw new Error(await errorMessage(resp));
  }
  return resp.json();
}

export async function saveTranscript(key: string, segments: TranscriptSegment[]): Promise<TranscriptSegment[]> {
  const result = (await postAdmin(`/episodes/${encodeURIComponent(key)}/transcript`, segments)) as {
    segments?: TranscriptSegment[];
  };
  return result.segments ?? segments;
}

export async function saveDeckSplit(eventId: string, seat: number, split: DeckSplit): Promise<DeckSplit> {
  const result = (await postAdmin(`/pods/${encodeURIComponent(eventId)}/decks/${seat}`, split)) as DeckSplit;
  return { main: result.main, side: result.side };
}

export interface DeckEditAccess {
  staff: boolean;
  seats: number[];
}

export async function fetchDeckEditAccess(eventId: string): Promise<DeckEditAccess> {
  const result = (await callBot(`/pods/${encodeURIComponent(eventId)}/decks/access`, { method: "GET" })) as
    Partial<DeckEditAccess> | undefined;
  return { staff: result?.staff === true, seats: result?.seats ?? [] };
}

async function errorMessage(resp: Response): Promise<string> {
  if (resp.status === 401 || resp.status === 403) {
    return "Not Authorized";
  }
  const parsed = await resp.json().catch(() => null);
  if (parsed?.error) {
    return parsed.error.charAt(0).toUpperCase() + parsed.error.slice(1);
  }
  return `Save Failed (${resp.status})`;
}
