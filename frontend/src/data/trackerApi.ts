// Private draft tracker reads and writes. Every row is scoped to the signed-in user by
// RLS on auth.uid(); the local proxy has no auth and forces its own dev user instead.

import { DEV_AUTH_USER } from "./devAuth";
import { supabase } from "./supabase";
import type { PlayerDraftEvent } from "../types/leaderboard";
import { LOCAL_SUPABASE_URL } from "./public-supabase-config";

export interface DraftNote {
  draftEventId: string;
  note: string;
  deckLabel: string;
  rares: number | null;
  mythics: number | null;
}

export interface TrackerAccount {
  accountId: number;
  accountName: string;
  events: number;
}

export interface MatchNote {
  draftEventId: string;
  matchNumber: number;
  result: "W" | "L" | null;
  opponentColors: string;
  note: string;
}

export interface SetEconomy {
  packsOwned: number;
  goldenPacks: number;
  masteryLevel: number;
  rankedSeasonPacks: number;
}

export const EMPTY_ECONOMY: SetEconomy = {
  packsOwned: 0, goldenPacks: 0, masteryLevel: 0, rankedSeasonPacks: 0,
};

export interface CollectionCount {
  cardName: string;
  owned: number;
}

function client() {
  if (!supabase) throw new Error("Tracker needs a Supabase client");
  return supabase;
}

async function userId(): Promise<string> {
  if (DEV_AUTH_USER) return DEV_AUTH_USER.id;
  const { data } = await client().auth.getUser();
  if (!data.user) throw new Error("Not authenticated");
  return data.user.id;
}

// The tracker reads the event view itself so it can select account_id, which the shared
// fetcher cannot: that one also serves cube boards, whose view has no account column.
const TRACKER_EVENT_COLUMNS =
  "slug, set_code, event_id, format, expansion, wins, losses, is_trophy, colors, " +
  "started_at, finished_at, seventeenlands_event_id, external_url, event_name, end_rank, account_id, " +
  "pool_rares, pool_mythics, deck_cards, match_results";

export async function fetchTrackerDrafts(slug: string, setCode: string): Promise<PlayerDraftEvent[]> {
  const { data, error } = await client()
    .from("public_player_draft_events")
    .select(TRACKER_EVENT_COLUMNS)
    .eq("slug", slug)
    .eq("set_code", setCode)
    .order("finished_at", { ascending: false, nullsFirst: false });
  if (error) throw error;
  return (data ?? []).map((r) => {
    const row = r as unknown as Record<string, unknown>;
    return {
      slug: row.slug as string,
      setCode: row.set_code as string,
      eventId: row.event_id as string,
      format: row.format as string,
      expansion: row.expansion as string,
      wins: (row.wins ?? 0) as number,
      losses: (row.losses ?? 0) as number,
      isTrophy: Boolean(row.is_trophy),
      colors: (row.colors ?? "") as string,
      startedAt: (row.started_at ?? null) as string | null,
      finishedAt: (row.finished_at ?? null) as string | null,
      seventeenlandsEventId: (row.seventeenlands_event_id ?? null) as string | null,
      externalUrl: (row.external_url ?? null) as string | null,
      eventName: (row.event_name ?? null) as string | null,
      endRank: (row.end_rank ?? null) as string | null,
      accountId: (row.account_id ?? null) as number | null,
      poolRares: (row.pool_rares ?? null) as number | null,
      poolMythics: (row.pool_mythics ?? null) as number | null,
      deckCards: (row.deck_cards ?? null) as PlayerDraftEvent["deckCards"],
      matchResults: (row.match_results ?? null) as PlayerDraftEvent["matchResults"],
    };
  });
}

/** Only ever the signed-in player's own Arena accounts; the view filters on the caller's JWT */
export async function fetchMyAccounts(): Promise<TrackerAccount[]> {
  const { data, error } = await client()
    .from("public_my_player_accounts")
    .select("account_id, account_name, events");
  if (error) throw error;
  return (data ?? [])
    .map((r) => ({
      accountId: r.account_id as number,
      accountName: r.account_name as string,
      events: (r.events ?? 0) as number,
    }))
    .sort((a, b) => b.events - a.events);
}

export async function fetchDraftNotes(): Promise<DraftNote[]> {
  const { data, error } = await client()
    .from("tracker_draft_notes")
    .select("draft_event_id, note, deck_label, rares, mythics");
  if (error) throw error;
  return (data ?? []).map((r) => ({
    draftEventId: r.draft_event_id as string,
    note: (r.note ?? "") as string,
    deckLabel: (r.deck_label ?? "") as string,
    rares: (r.rares ?? null) as number | null,
    mythics: (r.mythics ?? null) as number | null,
  }));
}

export async function saveDraftNote(draftEventId: string, patch: Partial<Omit<DraftNote, "draftEventId">>) {
  const { error } = await client()
    .from("tracker_draft_notes")
    .upsert(
      {
        user_id: await userId(),
        draft_event_id: draftEventId,
        ...(patch.note !== undefined ? { note: patch.note } : {}),
        ...(patch.deckLabel !== undefined ? { deck_label: patch.deckLabel } : {}),
        ...(patch.rares !== undefined ? { rares: patch.rares } : {}),
        ...(patch.mythics !== undefined ? { mythics: patch.mythics } : {}),
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id,draft_event_id" },
    );
  if (error) throw error;
}

export async function fetchMatchNotes(): Promise<MatchNote[]> {
  const { data, error } = await client()
    .from("tracker_match_notes")
    .select("draft_event_id, match_number, result, opponent_colors, note");
  if (error) throw error;
  return (data ?? []).map((r) => ({
    draftEventId: r.draft_event_id as string,
    matchNumber: r.match_number as number,
    result: (r.result ?? null) as "W" | "L" | null,
    opponentColors: (r.opponent_colors ?? "") as string,
    note: (r.note ?? "") as string,
  }));
}

export async function saveMatchNote(
  draftEventId: string,
  matchNumber: number,
  patch: Partial<Omit<MatchNote, "draftEventId" | "matchNumber">>,
) {
  const { error } = await client()
    .from("tracker_match_notes")
    .upsert(
      {
        user_id: await userId(),
        draft_event_id: draftEventId,
        match_number: matchNumber,
        ...(patch.note !== undefined ? { note: patch.note } : {}),
        ...(patch.result !== undefined ? { result: patch.result } : {}),
        ...(patch.opponentColors !== undefined ? { opponent_colors: patch.opponentColors } : {}),
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id,draft_event_id,match_number" },
    );
  if (error) throw error;
}

export async function fetchCollection(setCode: string): Promise<CollectionCount[]> {
  const { data, error } = await client()
    .from("tracker_collection")
    .select("card_name, owned")
    .eq("set_code", setCode);
  if (error) throw error;
  return (data ?? []).map((r) => ({ cardName: r.card_name as string, owned: r.owned as number }));
}

export async function saveCollectionCount(setCode: string, cardName: string, owned: number) {
  const { error } = await client()
    .from("tracker_collection")
    .upsert(
      {
        user_id: await userId(),
        set_code: setCode,
        card_name: cardName,
        owned,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id,set_code,card_name" },
    );
  if (error) throw error;
}

/** Server-side 17lands fetch: pulls new drafts into the event log, then fills deck and match detail */
export async function refreshDraftData(
  setCode: string,
  force = false,
): Promise<{ ingested: number; filled: number; missed: number }> {
  return trackerRefresh(`set_code=${encodeURIComponent(setCode)}${force ? "&force=1" : ""}`);
}

/** Refetches one draft's deck and match detail, skipping the event-log pull */
export async function refreshOneDraft(seventeenlandsEventId: string) {
  return trackerRefresh(`event_id=${encodeURIComponent(seventeenlandsEventId)}`);
}

async function trackerRefresh(query: string): Promise<{ ingested: number; filled: number; missed: number }> {
  const base = LOCAL_SUPABASE_URL.replace(/\/$/, "");
  const resp = await fetch(`${base}/tracker/refresh?${query}`, { method: "POST" });
  if (!resp.ok) throw new Error(`Refresh failed (${resp.status})`);
  return resp.json();
}

export async function fetchSetEconomy(setCode: string): Promise<SetEconomy> {
  const { data, error } = await client()
    .from("tracker_set_economy")
    .select("packs_owned, golden_packs, mastery_level, ranked_season_packs")
    .eq("set_code", setCode);
  if (error) throw error;
  const row = (data ?? [])[0];
  if (!row) return EMPTY_ECONOMY;
  return {
    packsOwned: (row.packs_owned ?? 0) as number,
    goldenPacks: (row.golden_packs ?? 0) as number,
    masteryLevel: (row.mastery_level ?? 0) as number,
    rankedSeasonPacks: (row.ranked_season_packs ?? 0) as number,
  };
}

export async function saveSetEconomy(setCode: string, patch: Partial<SetEconomy>) {
  const { error } = await client()
    .from("tracker_set_economy")
    .upsert(
      {
        user_id: await userId(),
        set_code: setCode,
        ...(patch.packsOwned !== undefined ? { packs_owned: patch.packsOwned } : {}),
        ...(patch.goldenPacks !== undefined ? { golden_packs: patch.goldenPacks } : {}),
        ...(patch.masteryLevel !== undefined ? { mastery_level: patch.masteryLevel } : {}),
        ...(patch.rankedSeasonPacks !== undefined ? { ranked_season_packs: patch.rankedSeasonPacks } : {}),
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id,set_code" },
    );
  if (error) throw error;
}
