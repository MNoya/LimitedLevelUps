// Real-Supabase fetchers. Mirror of mockApi.ts function signatures — the hook
// layer picks one or the other via api.ts based on `useSupabase` (VITE_DATA_MODE).
//
// Each function reads from a curated public_* view (frontend-spec.md → Data
// contract). The adapter converts snake_case rows to camelCase. The anon key
// only has SELECT on these views; base tables stay locked under RLS.

import { supabase } from "./supabase";
import {
  adaptDraftEvent,
  adaptFormatBreakdown,
  adaptLeaderboardRow,
  adaptSelfReportedEvent,
  adaptSet,
} from "./adapter";
import { adaptDbEpisode, type DbEpisodeRow, type Episode } from "./episodes";
import {
  aggregate,
  boxesForEvent,
  computeScore,
  lcqDraft2Earnings,
  podPoints,
  scoreFromGroups,
  type GroupTotals,
  type ScoringStatRow,
} from "./scoring";
import { mergeSelfReportedTrophies, type SelfReportedTrophyTally } from "./selfReported";
import { baseSetCode, colorsOf, CUBE_BASE, isCubeCode, isCubeSeasonCode, isSoup } from "./utils";
import { formatsForBucket } from "./format-buckets";
import { IDENTITY_VIEWS } from "./constants";
import { FORMAT_LABEL_GROUPS, FORMAT_RAW_GROUPS, MULTI, OTHER } from "./filters";
import type {
  ColorsLeaderboardRow,
  ColorsSummary,
  CubeSeason,
  LeaderboardRow,
  PlayerDraftEvent,
  PlayerFormatBreakdown,
  PlayerIdentity,
  PlayerProfile,
  PodDraftArtifact,
  PodEventMatchRow,
  PodEventParticipantRow,
  PodEventReplayRow,
  PodEventSummary,
  PodLeaderboardRow,
  PodSetCode,
  RecentTrophy,
  SetSummary,
  TrophyLeaderboardRow,
} from "../types/leaderboard";

function client() {
  if (!supabase) throw new Error("Supabase client is not configured");
  return supabase;
}

const ARENA_DIRECT_FORMAT = "ArenaDirect_Sealed";
const LCQ_DRAFT_2_FORMATS = formatsForBucket("LCQ Draft 2");

// A CUBE season (set_code "CUBE-SOS") is windowed cube data exposed through
// dedicated views that mirror the lifetime ones row-for-row. The per-event view
// carries the same columns plus the player's display name/avatar, so the color
// and trophy boards work off set_code alone.
const eventsViewFor = (setCode: string): string =>
  isCubeSeasonCode(setCode) ? "public_cube_season_events" : "public_player_draft_events";

export async function fetchDbEpisodes(): Promise<Episode[]> {
  const { data, error } = await client()
    .from("public_episodes")
    .select(DB_EPISODE_COLUMNS)
    .order("published_at", { ascending: false });
  if (error) throw error;
  return (data ?? []).map((r) => adaptDbEpisode(r as unknown as DbEpisodeRow));
}

export async function fetchRecentDbEpisodes(limit = 8): Promise<Episode[]> {
  const { data, error } = await client()
    .from("public_episodes")
    .select(DB_EPISODE_COLUMNS)
    .order("published_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return (data ?? []).map((r) => adaptDbEpisode(r as unknown as DbEpisodeRow));
}

const DB_EPISODE_COLUMNS =
  "guid, kind, number, title, link, image, published_at, duration_seconds, audio_url, youtube_id, category, set_code, set_name, set_released_at";

export async function fetchCubeSeasons(): Promise<CubeSeason[]> {
  const { data, error } = await client()
    .from("public_cube_seasons")
    .select("*")
    .order("start_date", { ascending: false });
  if (error) throw error;
  return (data ?? []).map((raw) => {
    const r = raw as Record<string, unknown>;
    return {
      setCode: r.set_code as string,
      kind: r.kind as "season" | "variant",
      label: r.label as string,
      name: (r.name as string | null) ?? null,
      startDate: r.start_date as string,
      firstEvent: r.first_event as string,
      lastEvent: r.last_event as string,
      events: (r.events as number) ?? 0,
      players: (r.players as number) ?? 0,
    };
  });
}

// ─── public_sets ───────────────────────────────────────────────────────────

export async function fetchSets(): Promise<SetSummary[]> {
  const { data, error } = await client()
    .from("public_sets")
    .select("*")
    .order("start_date", { ascending: false });
  if (error) throw error;
  return (data ?? []).map((r) => adaptSet(r as Record<string, unknown>));
}

export async function fetchFormatColorsLeaderboard(
  setCode: string,
  format: string,
  archetypes: string | string[],
): Promise<ColorsLeaderboardRow[]> {
  if (format === "Pod") {
    const arch = Array.isArray(archetypes) ? archetypes[0] : archetypes;
    return fetchPodColorsLeaderboard(setCode, arch, null);
  }
  const archs = Array.isArray(archetypes) ? archetypes : [archetypes];
  if (archs.length === 0) return [];
  const bucketLabel = archs.length === 1 ? archs[0] : archs.join(",");
  return aggregateColorsFromEvents(setCode, bucketLabel, bucketOf(archs), format);
}

export async function fetchAvailableFormats(setCode: string): Promise<string[]> {
  if (isCubeSeasonCode(setCode)) {
    const { data, error } = await client()
      .from("public_cube_season_breakdown")
      .select("format_label")
      .eq("set_code", setCode);
    if (error) throw error;
    return Array.from(new Set((data ?? []).map((r) => (r as { format_label: string }).format_label)));
  }
  const [breakdown, pod, direct] = await Promise.all([
    client()
      .from("public_player_format_breakdown")
      .select("format_label")
      .eq("set_code", setCode),
    client()
      .from("public_player_pod_stats")
      .select("set_code", { count: "exact", head: true })
      .eq("set_code", setCode),
    client()
      .from("public_player_draft_events")
      .select("set_code", { count: "exact", head: true })
      .eq("set_code", setCode)
      .eq("format", ARENA_DIRECT_FORMAT),
  ]);
  if (breakdown.error) throw breakdown.error;
  if (pod.error) throw pod.error;
  if (direct.error) throw direct.error;
  const labels = new Set(
    (breakdown.data ?? []).map((r) => (r as { format_label: string }).format_label),
  );
  if ((pod.count ?? 0) > 0) labels.add("Pod");
  // Arena Direct buckets under the Sealed format_label, so surface it as its own
  // option only when the set actually has Direct events.
  if ((direct.count ?? 0) > 0) labels.add("Direct");
  return Array.from(labels);
}

// ─── public_leaderboard ────────────────────────────────────────────────────

export async function fetchLeaderboard(setCode: string): Promise<LeaderboardRow[]> {
  if (isCubeSeasonCode(setCode)) return fetchCubeSeasonLeaderboard(setCode);
  const [leaderboard, breakdown, pod, selfReported] = await Promise.all([
    client()
      .from("public_leaderboard")
      .select("slug, display_name, avatar_url, trophies, events, wins, losses, last_calculated_at")
      .eq("set_code", setCode),
    client()
      .from("public_player_format_breakdown")
      .select("slug, format_label, events, wins, losses, trophies")
      .eq("set_code", setCode),
    client()
      .from("public_pod_scoring")
      .select("slug, display_name, avatar_url, trophies, wins_2_1, leaderboard_opt_in")
      .eq("set_code", setCode),
    client()
      .from("public_self_reported_events")
      .select("slug, display_name, avatar_url, is_trophy")
      .eq("set_code", setCode),
  ]);
  if (leaderboard.error) throw leaderboard.error;
  if (breakdown.error) throw breakdown.error;
  if (pod.error) throw pod.error;
  if (selfReported.error) throw selfReported.error;

  // 17lands score: group every breakdown row per slug, then aggregate (confidence is aggregate)
  const groupsBySlug = new Map<string, GroupTotals[]>();
  for (const raw of breakdown.data ?? []) {
    const r = raw as Record<string, unknown>;
    const slug = r.slug as string;
    const list = groupsBySlug.get(slug) ?? [];
    list.push({
      label: r.format_label as string,
      events: (r.events as number) ?? 0,
      wins: (r.wins as number) ?? 0,
      losses: (r.losses as number) ?? 0,
      trophies: (r.trophies as number) ?? 0,
    });
    groupsBySlug.set(slug, list);
  }

  const bySlug = new Map<string, LeaderboardRow>();
  for (const raw of leaderboard.data ?? []) {
    const r = raw as Record<string, unknown>;
    const slug = r.slug as string;
    bySlug.set(slug, {
      setCode,
      slug,
      displayName: r.display_name as string,
      avatarUrl: (r.avatar_url ?? null) as string | null,
      rank: 0,
      score: scoreFromGroups(groupsBySlug.get(slug) ?? []),
      trophies: (r.trophies as number) ?? 0,
      events: (r.events as number) ?? 0,
      wins: (r.wins as number) ?? 0,
      losses: (r.losses as number) ?? 0,
      lastCalculatedAt: (r.last_calculated_at as string) ?? new Date(0).toISOString(),
    });
  }

  // Pod points: add to existing rows, or admit pod-only players as entrants. Opted-out
  // players stay in the pod standings but never rejoin the overall board on pod points.
  for (const raw of pod.data ?? []) {
    const r = raw as Record<string, unknown>;
    if (r.leaderboard_opt_in === false) continue;
    const podTrophies = (r.trophies as number) ?? 0;
    const bonus = podPoints(podTrophies, (r.wins_2_1 as number) ?? 0);
    if (bonus === 0) continue;
    const slug = r.slug as string;
    const existing = bySlug.get(slug);
    if (existing) {
      existing.score = Math.round((existing.score + bonus) * 100) / 100;
      existing.trophies += podTrophies;
    } else {
      bySlug.set(slug, {
        setCode,
        slug,
        displayName: (r.display_name as string) ?? slug,
        avatarUrl: (r.avatar_url ?? null) as string | null,
        rank: 0,
        score: bonus,
        trophies: podTrophies,
        events: 0,
        wins: 0,
        losses: 0,
        lastCalculatedAt: new Date(0).toISOString(),
      });
    }
  }

  // Self-reported trophies (paper/MTGO runs logged via /trophy). Zero score: they lift the trophy
  // count only, and a self-report-only player enters the board the way pod-only players do.
  const tallyBySlug = new Map<string, SelfReportedTrophyTally>();
  for (const raw of selfReported.data ?? []) {
    const r = raw as Record<string, unknown>;
    if (r.is_trophy !== true) continue;
    const slug = r.slug as string;
    const existing = tallyBySlug.get(slug);
    if (existing) {
      existing.trophies += 1;
    } else {
      tallyBySlug.set(slug, {
        slug,
        displayName: (r.display_name as string) ?? slug,
        avatarUrl: (r.avatar_url ?? null) as string | null,
        trophies: 1,
      });
    }
  }

  return mergeSelfReportedTrophies([...bySlug.values()], [...tallyBySlug.values()], setCode);
}

// MTGO flashback board: self-reported results aggregated per player. These sets have no scored
// data, so the standing is the trophy tally; non-trophy decks are carried but don't lift the rank.
export async function fetchTrophyLeaderboard(setCode: string): Promise<TrophyLeaderboardRow[]> {
  const { data, error } = await client()
    .from("public_self_reported_events")
    .select("*")
    .eq("set_code", setCode)
    .order("reported_at", { ascending: false });
  if (error) throw error;

  const bySlug = new Map<string, TrophyLeaderboardRow>();
  for (const raw of data ?? []) {
    const r = raw as Record<string, unknown>;
    const slug = r.slug as string;
    const deck = adaptSelfReportedEvent(r);
    const existing = bySlug.get(slug);
    if (existing) {
      existing.trophies += deck.isTrophy ? 1 : 0;
      existing.deckCount += 1;
      existing.decks.push(deck);
    } else {
      bySlug.set(slug, {
        setCode,
        slug,
        displayName: (r.display_name as string) ?? slug,
        avatarUrl: (r.avatar_url ?? null) as string | null,
        rank: 0,
        trophies: deck.isTrophy ? 1 : 0,
        deckCount: 1,
        decks: [deck],
      });
    }
  }

  return [...bySlug.values()]
    .sort(
      (a, b) =>
        b.trophies - a.trophies ||
        b.deckCount - a.deckCount ||
        b.decks[0].reportedAt.localeCompare(a.decks[0].reportedAt),
    )
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

// Stats refresh globally, so a cube board's "Last updated" is the CUBE set's own
// timestamp (the cube views carry no per-row calculation time).
async function cubeUpdatedAt(): Promise<string> {
  const { data, error } = await client()
    .from("public_leaderboard")
    .select("last_calculated_at")
    .eq("set_code", CUBE_BASE)
    .limit(1);
  if (error) throw error;
  return (data?.[0] as { last_calculated_at?: string } | undefined)?.last_calculated_at ?? new Date(0).toISOString();
}

// A cube season scores like the lifetime board — group every breakdown row per
// slug, aggregate (confidence is aggregate) — but reads the windowed season view
// and carries no pod points (seasons are 17lands-cube only).
async function fetchCubeSeasonLeaderboard(setCode: string): Promise<LeaderboardRow[]> {
  const [breakdown, lastCalculatedAt] = await Promise.all([
    client().from("public_cube_season_breakdown").select("*").eq("set_code", setCode),
    cubeUpdatedAt(),
  ]);
  if (breakdown.error) throw breakdown.error;

  interface Agg { displayName: string; avatarUrl: string | null; groups: GroupTotals[]; trophies: number; events: number; wins: number; losses: number }
  const bySlug = new Map<string, Agg>();
  for (const raw of breakdown.data ?? []) {
    const r = raw as Record<string, unknown>;
    const slug = r.slug as string;
    let agg = bySlug.get(slug);
    if (!agg) {
      agg = { displayName: (r.display_name as string) ?? slug, avatarUrl: (r.avatar_url ?? null) as string | null, groups: [], trophies: 0, events: 0, wins: 0, losses: 0 };
      bySlug.set(slug, agg);
    }
    const events = (r.events as number) ?? 0;
    const wins = (r.wins as number) ?? 0;
    const losses = (r.losses as number) ?? 0;
    const trophies = (r.trophies as number) ?? 0;
    agg.groups.push({ label: r.format_label as string, events, wins, losses, trophies });
    agg.events += events;
    agg.wins += wins;
    agg.losses += losses;
    agg.trophies += trophies;
  }

  return [...bySlug.entries()]
    .map(([slug, agg]) => ({
      setCode,
      slug,
      displayName: agg.displayName,
      avatarUrl: agg.avatarUrl,
      rank: 0,
      score: scoreFromGroups(agg.groups),
      trophies: agg.trophies,
      events: agg.events,
      wins: agg.wins,
      losses: agg.losses,
      lastCalculatedAt,
    }))
    .sort((a, b) => (b.score !== a.score ? b.score - a.score : a.displayName.localeCompare(b.displayName)))
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

// ─── per-format leaderboard ────────────────────────────────────────────────
// No dedicated view yet — we client-side join public_player_format_breakdown
// (filtered to format_label, sorted by score_contribution) with the leaderboard
// rows for displayName / avatarUrl / lastCalculatedAt. Players without any
// events in this format simply don't appear.

export async function fetchFormatLeaderboard(
  setCode: string,
  format: string,
): Promise<LeaderboardRow[]> {
  if (format === "Pod") {
    const { data, error } = await client()
      .from("public_pod_scoring")
      .select("*")
      .eq("set_code", setCode);
    if (error) throw error;
    return (data ?? [])
      .map((raw) => {
        const r = raw as Record<string, unknown>;
        const trophies = (r.trophies as number) ?? 0;
        const wins21 = (r.wins_2_1 as number) ?? 0;
        return {
          setCode,
          slug: r.slug as string,
          displayName: (r.display_name as string) ?? (r.slug as string),
          avatarUrl: (r.avatar_url ?? null) as string | null,
          rank: 0,
          score: podPoints(trophies, wins21),
          trophies,
          events: (r.events as number) ?? 0,
          wins: (r.wins as number) ?? 0,
          losses: (r.losses as number) ?? 0,
          lastCalculatedAt: new Date(0).toISOString(),
        } as LeaderboardRow;
      })
      .sort((a, b) =>
        b.score !== a.score ? b.score - a.score : a.displayName.localeCompare(b.displayName),
      )
      .map((r, i) => ({ ...r, rank: i + 1 }));
  }
  if (format === "Direct") return fetchDirectLeaderboard(setCode);
  if (isCubeSeasonCode(setCode)) return fetchCubeSeasonFormatLeaderboard(setCode, format);
  const labels = FORMAT_LABEL_GROUPS[format] ?? [format];
  const labelSet = new Set(labels);
  // Fetch the whole breakdown (not just the filtered labels): a format's points must carry the
  // player-wide confidence factor over all their trophies, matching the profile and the overall
  // board. Scoring only the filtered groups would shrink confidence to that format alone.
  const [breakdown, leaderboard] = await Promise.all([
    client()
      .from("public_player_format_breakdown")
      .select("*")
      .eq("set_code", setCode),
    client()
      .from("public_leaderboard")
      .select("slug, display_name, avatar_url, last_calculated_at")
      .eq("set_code", setCode),
  ]);
  if (breakdown.error) throw breakdown.error;
  if (leaderboard.error) throw leaderboard.error;

  const info = new Map(
    (leaderboard.data ?? []).map((r) => [
      (r as Record<string, unknown>).slug as string,
      r as Record<string, unknown>,
    ]),
  );

  const groupsBySlug = new Map<string, GroupTotals[]>();
  const totalsBySlug = new Map<string, { trophies: number; events: number; wins: number; losses: number }>();
  for (const raw of breakdown.data ?? []) {
    const r = raw as Record<string, unknown>;
    const slug = r.slug as string;
    const events = (r.events as number) ?? 0;
    if (events <= 0 || !info.has(slug)) continue;
    const label = r.format_label as string;
    const wins = (r.wins as number) ?? 0;
    const losses = (r.losses as number) ?? 0;
    const trophies = (r.trophies as number) ?? 0;

    const list = groupsBySlug.get(slug) ?? [];
    list.push({ label, events, wins, losses, trophies });
    groupsBySlug.set(slug, list);

    if (!labelSet.has(label)) continue;
    const t = totalsBySlug.get(slug) ?? { trophies: 0, events: 0, wins: 0, losses: 0 };
    t.trophies += trophies;
    t.events += events;
    t.wins += wins;
    t.losses += losses;
    totalsBySlug.set(slug, t);
  }

  const rows: LeaderboardRow[] = [];
  for (const [slug, t] of totalsBySlug) {
    const inf = info.get(slug)!;
    const contributions = aggregate(groupsBySlug.get(slug) ?? []).contributionByLabel;
    let score = 0;
    for (const label of labels) {
      score += contributions.get(label) ?? 0;
    }
    rows.push({
      setCode,
      slug,
      displayName: inf.display_name as string,
      avatarUrl: (inf.avatar_url ?? null) as string | null,
      rank: 0,
      score: Math.round(score * 100) / 100,
      trophies: t.trophies,
      events: t.events,
      wins: t.wins,
      losses: t.losses,
      lastCalculatedAt: inf.last_calculated_at as string,
    });
  }

  if (format === "LCQ") {
    const earningsBySlug = await fetchLcqEarningsBySlug(setCode);
    for (const row of rows) {
      row.earnings = earningsBySlug.get(row.slug) ?? 0;
    }
  }

  return rows
    .sort((a, b) => b.score - a.score)
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

// Cube-season format board: same windowed breakdown view, filtered to the
// requested label group and scored per slug.
async function fetchCubeSeasonFormatLeaderboard(
  setCode: string,
  format: string,
): Promise<LeaderboardRow[]> {
  const labels = FORMAT_LABEL_GROUPS[format] ?? [format];
  const [resp, lastCalculatedAt] = await Promise.all([
    client().from("public_cube_season_breakdown").select("*").eq("set_code", setCode).in("format_label", labels),
    cubeUpdatedAt(),
  ]);
  if (resp.error) throw resp.error;
  const data = resp.data;

  interface Agg { displayName: string; avatarUrl: string | null; groups: GroupTotals[]; trophies: number; events: number; wins: number; losses: number }
  const bySlug = new Map<string, Agg>();
  for (const raw of data ?? []) {
    const r = raw as Record<string, unknown>;
    const events = (r.events as number) ?? 0;
    if (events <= 0) continue;
    const slug = r.slug as string;
    let agg = bySlug.get(slug);
    if (!agg) {
      agg = { displayName: (r.display_name as string) ?? slug, avatarUrl: (r.avatar_url ?? null) as string | null, groups: [], trophies: 0, events: 0, wins: 0, losses: 0 };
      bySlug.set(slug, agg);
    }
    const wins = (r.wins as number) ?? 0;
    const losses = (r.losses as number) ?? 0;
    const trophies = (r.trophies as number) ?? 0;
    agg.groups.push({ label: r.format_label as string, events, wins, losses, trophies });
    agg.events += events;
    agg.wins += wins;
    agg.losses += losses;
    agg.trophies += trophies;
  }

  return [...bySlug.entries()]
    .map(([slug, agg]) => ({
      setCode,
      slug,
      displayName: agg.displayName,
      avatarUrl: agg.avatarUrl,
      rank: 0,
      score: scoreFromGroups(agg.groups),
      trophies: agg.trophies,
      events: agg.events,
      wins: agg.wins,
      losses: agg.losses,
      lastCalculatedAt,
    }))
    .sort((a, b) => b.score - a.score)
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

// LCQ Draft 2 cash needs per-event win counts (a 5-win and a 6-win event pay
// differently), which the aggregated breakdown view can't distinguish.
async function fetchLcqEarningsBySlug(setCode: string): Promise<Map<string, number>> {
  const { data, error } = await client()
    .from("public_player_draft_events")
    .select("slug, wins")
    .eq("set_code", setCode)
    .in("format", LCQ_DRAFT_2_FORMATS);
  if (error) throw error;
  const bySlug = new Map<string, number>();
  for (const raw of (data ?? []) as Array<{ slug: string; wins: number | null }>) {
    const payout = lcqDraft2Earnings(raw.wins ?? 0);
    if (payout > 0) bySlug.set(raw.slug, (bySlug.get(raw.slug) ?? 0) + payout);
  }
  return bySlug;
}

// Arena Direct board: boxes won per the era rules in scoring.boxesForEvent,
// aggregated from the raw event log and ranked boxes-first like the bot's board.
async function fetchDirectLeaderboard(setCode: string): Promise<LeaderboardRow[]> {
  const events: Array<Record<string, unknown>> = [];
  const pageSize = 1000;
  for (let from = 0; ; from += pageSize) {
    const { data, error } = await client()
      .from("public_player_draft_events")
      .select("slug, wins, losses, is_trophy, finished_at")
      .eq("set_code", setCode)
      .eq("format", ARENA_DIRECT_FORMAT)
      .range(from, from + pageSize - 1);
    if (error) throw error;
    const batch = (data ?? []) as Array<Record<string, unknown>>;
    events.push(...batch);
    if (batch.length < pageSize) break;
  }

  const meta = await client()
    .from("public_leaderboard")
    .select("slug, display_name, avatar_url, last_calculated_at")
    .eq("set_code", setCode);
  if (meta.error) throw meta.error;
  const metaBySlug = new Map<string, Record<string, unknown>>();
  for (const m of (meta.data ?? []) as Array<Record<string, unknown>>) {
    metaBySlug.set(m.slug as string, m);
  }

  interface Agg { boxes: number; trophies: number; events: number; wins: number; losses: number; lastFinishedAt: string }
  const perSlug = new Map<string, Agg>();
  for (const raw of events) {
    const slug = raw.slug as string;
    let agg = perSlug.get(slug);
    if (!agg) {
      agg = { boxes: 0, trophies: 0, events: 0, wins: 0, losses: 0, lastFinishedAt: "" };
      perSlug.set(slug, agg);
    }
    const wins = (raw.wins as number) ?? 0;
    const finishedAt = (raw.finished_at as string) ?? "";
    agg.events += 1;
    agg.wins += wins;
    agg.losses += (raw.losses as number) ?? 0;
    if (raw.is_trophy) agg.trophies += 1;
    agg.boxes += boxesForEvent(setCode, wins, finishedAt || null, Boolean(raw.is_trophy));
    if (finishedAt > agg.lastFinishedAt) agg.lastFinishedAt = finishedAt;
  }

  const rows: LeaderboardRow[] = [];
  for (const [slug, agg] of perSlug) {
    if (agg.events === 0) continue;
    const m = metaBySlug.get(slug);
    rows.push({
      setCode,
      slug,
      displayName: (m?.display_name as string) ?? slug,
      avatarUrl: (m?.avatar_url as string | null) ?? null,
      rank: 0,
      score: 0,
      boxes: agg.boxes,
      trophies: agg.trophies,
      events: agg.events,
      wins: agg.wins,
      losses: agg.losses,
      lastCalculatedAt:
        agg.lastFinishedAt || ((m?.last_calculated_at as string | undefined) ?? new Date(0).toISOString()),
    });
  }

  return rows
    .sort((a, b) => {
      if (b.boxes !== a.boxes) return (b.boxes ?? 0) - (a.boxes ?? 0);
      if (b.trophies !== a.trophies) return b.trophies - a.trophies;
      const wpA = a.wins / Math.max(1, a.wins + a.losses);
      const wpB = b.wins / Math.max(1, b.wins + b.losses);
      if (wpB !== wpA) return wpB - wpA;
      return a.slug.localeCompare(b.slug);
    })
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

// Per-color archetype tallies come pre-aggregated from public_colors_summary
// (~20 rows), not from a client-side pass over every draft event. The view owns
// the overlapping tally — each deck counts toward its main-color archetype and,
// when it qualifies as Soup, toward MULTI — and the cube vs non-cube Soup rule.
export async function fetchColorsSummary(setCode: string): Promise<ColorsSummary[]> {
  const { data, error } = await client()
    .from("public_colors_summary")
    .select("colors, trophies, events, players")
    .eq("set_code", setCode);
  if (error) throw error;
  return (data ?? [])
    .map((raw) => {
      const r = raw as Record<string, unknown>;
      return {
        setCode,
        colors: r.colors as string,
        trophies: (r.trophies as number) ?? 0,
        events: (r.events as number) ?? 0,
        players: (r.players as number) ?? 0,
      };
    })
    .sort((a, b) => b.trophies - a.trophies);
}

export async function fetchColorsLeaderboard(
  setCode: string,
  colors: string,
): Promise<ColorsLeaderboardRow[]> {
  return aggregateColorsFromEvents(setCode, colors, bucketOf([colors]), null);
}

export async function fetchOtherColorsLeaderboard(
  setCode: string,
  otherCombos: string[],
  formatFilter?: string,
): Promise<ColorsLeaderboardRow[]> {
  if (otherCombos.length === 0) return [];
  if (formatFilter === "Pod") {
    return fetchPodColorsLeaderboard(setCode, OTHER, otherCombos);
  }
  return aggregateColorsFromEvents(setCode, OTHER, bucketOf(otherCombos), formatFilter);
}

// A chip is one colour bucket: named main-colour combos, and Soup (MULTI) by the colour-count rule.
// public_color_events derives both, so the board reads its own slice instead of the whole set.
interface ColorBucket {
  combos: string[];
  includeMulti: boolean;
}

function bucketOf(chips: string[]): ColorBucket {
  return { combos: chips.filter((c) => c !== MULTI), includeMulti: chips.includes(MULTI) };
}

function inBucket(row: Record<string, unknown>, bucket: ColorBucket): boolean {
  if (bucket.includeMulti && row.is_multi === true) {
    return true;
  }
  return bucket.combos.includes((row.main_colors as string) ?? "");
}

async function aggregateColorsFromEvents(
  setCode: string,
  bucketLabel: string,
  bucket: ColorBucket,
  formatFilter: string | null | undefined,
): Promise<ColorsLeaderboardRow[]> {
  if (formatFilter === "Pod") {
    return fetchPodColorsLeaderboard(setCode, bucketLabel, null);
  }
  const formatGroup = formatFilter
    ? (FORMAT_RAW_GROUPS[formatFilter] ?? [formatFilter])
    : null;
  const formatAllowed = formatGroup ? new Set(formatGroup) : null;

  const season = isCubeSeasonCode(setCode);
  let query = client()
    .from("public_color_events")
    .select("slug, format, wins, losses, is_trophy, finished_at, display_name, avatar_url, main_colors, is_multi")
    .eq("set_code", setCode);
  // One bucket narrows server-side; a mixed request falls back to the whole board and inBucket.
  if (bucket.includeMulti && bucket.combos.length === 0) {
    query = query.eq("is_multi", true);
  } else if (!bucket.includeMulti && bucket.combos.length > 0) {
    query = query.in("main_colors", bucket.combos);
  }
  const { data, error } = await query;
  if (error) throw error;
  const allEvents = (data ?? []) as unknown as Array<Record<string, unknown>>;

  // Season views carry the player's name/avatar per row; lifetime boards join
  // the leaderboard view for that meta (it has no CUBE-<season> rows).
  const metaBySlug = new Map<string, Record<string, unknown>>();
  if (season) {
    for (const e of allEvents) {
      const slug = e.slug as string;
      if (!metaBySlug.has(slug)) {
        metaBySlug.set(slug, { slug, display_name: e.display_name, avatar_url: e.avatar_url });
      }
    }
  } else {
    const metaResp = await client()
      .from("public_leaderboard")
      .select("slug, display_name, avatar_url, last_calculated_at")
      .eq("set_code", setCode);
    if (metaResp.error) throw metaResp.error;
    for (const m of (metaResp.data ?? []) as Array<Record<string, unknown>>) {
      metaBySlug.set(m.slug as string, m);
    }
  }

  interface PlayerAgg {
    formatRows: ScoringStatRow[];
    events: number;
    trophies: number;
    wins: number;
    losses: number;
    boxes: number;
    earnings: number;
    lastFinishedAt: string;
  }
  const perSlug = new Map<string, PlayerAgg>();

  for (const raw of allEvents) {
    if (!inBucket(raw, bucket)) continue;

    const slug = raw.slug as string;
    const fmt = (raw.format as string) ?? "";
    if (formatAllowed && !formatAllowed.has(fmt)) continue;
    const wins = (raw.wins as number) ?? 0;
    const losses = (raw.losses as number) ?? 0;
    const isTrophy = Boolean(raw.is_trophy);
    const finishedAt = (raw.finished_at as string) ?? "";

    let agg = perSlug.get(slug);
    if (!agg) {
      agg = { formatRows: [], events: 0, trophies: 0, wins: 0, losses: 0, boxes: 0, earnings: 0, lastFinishedAt: "" };
      perSlug.set(slug, agg);
    }
    agg.events += 1;
    agg.wins += wins;
    agg.losses += losses;
    if (isTrophy) agg.trophies += 1;
    if (fmt === ARENA_DIRECT_FORMAT) agg.boxes += boxesForEvent(setCode, wins, finishedAt || null, isTrophy);
    if (LCQ_DRAFT_2_FORMATS.includes(fmt)) agg.earnings += lcqDraft2Earnings(wins);
    agg.formatRows.push({ format: fmt, wins, losses, trophies: isTrophy ? 1 : 0, events: 1 });
    if (finishedAt > agg.lastFinishedAt) agg.lastFinishedAt = finishedAt;
  }

  const rows: ColorsLeaderboardRow[] = [];
  for (const [slug, agg] of perSlug) {
    if (agg.events === 0) continue;
    const meta = metaBySlug.get(slug);
    rows.push({
      setCode,
      colors: bucketLabel,
      slug,
      displayName: (meta?.display_name as string) ?? slug,
      avatarUrl: (meta?.avatar_url as string | null) ?? null,
      rank: 0,
      score: computeScore(agg.formatRows),
      trophies: agg.trophies,
      events: agg.events,
      wins: agg.wins,
      losses: agg.losses,
      boxes: agg.boxes,
      earnings: agg.earnings,
      lastCalculatedAt:
        agg.lastFinishedAt ||
        ((meta?.last_calculated_at as string | undefined) ?? new Date(0).toISOString()),
    });
  }

  return rows
    .sort((a, b) => {
      if (formatFilter === "Direct" && a.boxes !== b.boxes) return (b.boxes ?? 0) - (a.boxes ?? 0);
      if (b.score !== a.score) return b.score - a.score;
      const wpA = a.wins / Math.max(1, a.wins + a.losses);
      const wpB = b.wins / Math.max(1, b.wins + b.losses);
      if (wpB !== wpA) return wpB - wpA;
      return a.slug.localeCompare(b.slug);
    })
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

// ─── public_player_format_breakdown + public_player composite ──────────────

export async function fetchPlayerProfile(
  slug: string,
  setCode: string,
): Promise<PlayerProfile | null> {
  setCode = baseSetCode(setCode); // cube seasons share the lifetime profile
  const [headlineResp, breakdownResp, podResp, trophiesResp] = await Promise.all([
    client()
      .from("public_player")
      .select("*")
      .eq("set_code", setCode)
      .eq("slug", slug)
      .maybeSingle(),
    client()
      .from("public_player_format_breakdown")
      .select("*")
      .eq("set_code", setCode)
      .eq("slug", slug),
    client()
      .from("public_pod_scoring")
      .select("*")
      .eq("set_code", setCode)
      .eq("slug", slug)
      .maybeSingle(),
    client()
      .from("public_self_reported_events")
      .select("*")
      .eq("set_code", setCode)
      .eq("slug", slug)
      .order("reported_at", { ascending: false }),
  ]);
  if (headlineResp.error) throw headlineResp.error;
  if (breakdownResp.error) throw breakdownResp.error;
  if (podResp.error) throw podResp.error;
  if (trophiesResp.error) throw trophiesResp.error;
  const trophyRows = (trophiesResp.data ?? []) as Record<string, unknown>[];
  if (!headlineResp.data && !podResp.data && trophyRows.length === 0) return null;

  let headline: LeaderboardRow;
  if (headlineResp.data) {
    headline = adaptLeaderboardRow(headlineResp.data as Record<string, unknown>);
  } else if (podResp.data) {
    headline = podOnlyHeadline(slug, setCode, podResp.data as Record<string, unknown>);
  } else {
    headline = trophyOnlyHeadline(slug, setCode, trophyRows[0]);
  }
  const breakdown = (breakdownResp.data ?? []).map((r) =>
    adaptFormatBreakdown(r as Record<string, unknown>),
  );
  // scoreContribution is aggregate-dependent (one confidence over total trophies), so it
  // can't be computed per row — derive each row's share from the full breakdown here.
  const agg = aggregate(
    breakdown.map((b) => ({
      label: b.formatLabel,
      events: b.events,
      wins: b.wins,
      losses: b.losses,
      trophies: b.trophies,
    })),
  );
  for (const b of breakdown) {
    b.scoreContribution = Math.round((agg.contributionByLabel.get(b.formatLabel) ?? 0) * 100) / 100;
  }
  // Pods score flat (no weight/rate/confidence) — append as its own breakdown row
  let podTrophies = 0;
  if (podResp.data) {
    const p = podResp.data as Record<string, unknown>;
    podTrophies = (p.trophies as number) ?? 0;
    const wins21 = (p.wins_2_1 as number) ?? 0;
    const pts = podPoints(podTrophies, wins21);
    if (pts > 0) {
      breakdown.push({
        setCode,
        slug,
        formatLabel: "Pod",
        events: (p.events as number) ?? 0,
        wins: (p.wins as number) ?? 0,
        losses: (p.losses as number) ?? 0,
        trophies: podTrophies,
        wins21,
        scoreContribution: pts,
      });
    }
  }
  const board = await fetchLeaderboard(setCode);
  const inBoard = board.find((r) => r.slug === slug);
  return {
    slug: headline.slug,
    displayName: headline.displayName,
    avatarUrl: headline.avatarUrl,
    setCode: headline.setCode,
    rank: inBoard?.rank ?? 0,
    score: inBoard?.score ?? 0,
    trophies: headline.trophies + podTrophies,
    events: headline.events,
    wins: headline.wins,
    losses: headline.losses,
    linked17lands: Boolean(headlineResp.data),
    lastCalculatedAt: headline.lastCalculatedAt || undefined,
    formatBreakdown: breakdown,
    selfReportedEvents: trophyRows.map((r) => adaptSelfReportedEvent(r)),
  };
}

function podOnlyHeadline(slug: string, setCode: string, pod: Record<string, unknown>): LeaderboardRow {
  return {
    setCode,
    slug,
    displayName: (pod.display_name as string | null) ?? slug,
    avatarUrl: (pod.avatar_url as string | null) ?? null,
    rank: 0,
    score: 0,
    trophies: 0,
    events: (pod.events as number) ?? 0,
    wins: (pod.wins as number) ?? 0,
    losses: (pod.losses as number) ?? 0,
    lastCalculatedAt: "",
  };
}

// A player whose only footprint is self-reported trophies — no 17lands stats, no pods. Their
// profile still renders so the trophy-case band has a home.
function trophyOnlyHeadline(slug: string, setCode: string, trophy: Record<string, unknown>): LeaderboardRow {
  return {
    setCode,
    slug,
    displayName: (trophy.display_name as string | null) ?? slug,
    avatarUrl: (trophy.avatar_url as string | null) ?? null,
    rank: 0,
    score: 0,
    trophies: 0,
    events: 0,
    wins: 0,
    losses: 0,
    lastCalculatedAt: "",
  };
}

// ─── public_player (identity, set-independent) ─────────────────────────────

// The logged-in user carries only their Discord id; the player slug lives in the DB.
// discord_id is already embedded in the public avatar_url, so match on it to recover
// the slug. Players on a default Discord avatar have a null avatar_url and won't resolve.
export async function fetchPlayerSlugByDiscordId(discordId: string): Promise<string | null> {
  const { data, error } = await client()
    .from("public_player")
    .select("slug")
    .ilike("avatar_url", `%/avatars/${discordId}/%`)
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return (data as { slug?: string } | null)?.slug ?? null;
}

export async function fetchPlayerIdentity(slug: string): Promise<PlayerIdentity | null> {
  for (const view of IDENTITY_VIEWS) {
    const { data, error } = await client()
      .from(view)
      .select("slug, display_name, avatar_url")
      .eq("slug", slug)
      .limit(1)
      .maybeSingle();
    if (error) throw error;
    if (data) {
      const row = data as Record<string, unknown>;
      return {
        slug: row.slug as string,
        displayName: row.display_name as string,
        avatarUrl: (row.avatar_url as string | null) ?? null,
      };
    }
  }
  return null;
}

// ─── public_player_draft_events ────────────────────────────────────────────

const DRAFT_EVENT_COLUMNS =
  "slug, set_code, event_id, format, expansion, wins, losses, is_trophy, colors, started_at, finished_at, seventeenlands_event_id, external_url, event_name, pod_event_slug, end_rank";

export async function fetchPlayerDraftEvents(
  slug: string,
  setCode: string,
): Promise<PlayerDraftEvent[]> {
  setCode = baseSetCode(setCode); // cube seasons share the lifetime profile
  const { data, error } = await client()
    .from("public_player_draft_events")
    .select(DRAFT_EVENT_COLUMNS)
    .eq("slug", slug)
    .eq("set_code", setCode)
    .order("finished_at", { ascending: false, nullsFirst: false });
  if (error) throw error;
  return (data ?? []).map((r) => adaptDraftEvent(r as unknown as Record<string, unknown>));
}

// ─── public_recent_trophies ────────────────────────────────────────────────

// Both public_recent_trophies and public_cube_season_events carry these; selecting
// them by name keeps the wider season-events row from shipping unused columns.
const RECENT_TROPHY_COLUMNS =
  "set_code, slug, display_name, avatar_url, format, colors, wins, losses, finished_at, seventeenlands_event_id, end_rank";

export async function fetchRecentTrophies(
  setCode: string,
  limit = 8,
): Promise<RecentTrophy[]> {
  // public_recent_trophies is already is_trophy-only; the season events view is
  // the full event log, so it needs the explicit trophy filter.
  let query = client()
    .from(isCubeSeasonCode(setCode) ? "public_cube_season_events" : "public_recent_trophies")
    .select(RECENT_TROPHY_COLUMNS)
    .eq("set_code", setCode);
  if (isCubeSeasonCode(setCode)) query = query.eq("is_trophy", true);
  const { data, error } = await query
    .order("finished_at", { ascending: false, nullsFirst: false })
    .limit(limit);
  if (error) throw error;
  return (data ?? []).map((r) => adaptRecentTrophy(r as Record<string, unknown>));
}

// Server-side format filter so the sidebar can rebuild Top Colors and Recent
// Trophies from a single dataset when the user picks a format. LCQ has compound
// raw labels; other formats substring-match (mirrors matchesFormatFilter).
export async function fetchFormatRecentTrophies(
  setCode: string,
  format: string,
): Promise<RecentTrophy[]> {
  if (format === "Pod") return fetchPodRecentTrophies(setCode);
  if (format === "LCQ") return fetchLcqRecentTrophiesAndWins(setCode);
  return fetchTrophyPool(setCode, format);
}

// Full trophy pool of a set, so the sidebar can rebuild Top Colors and Recent
// Trophies client-side when the rank filter is active.
export async function fetchAllRecentTrophies(setCode: string): Promise<RecentTrophy[]> {
  return fetchTrophyPool(setCode);
}

async function fetchTrophyPool(setCode: string, format?: string): Promise<RecentTrophy[]> {
  const group = format ? FORMAT_RAW_GROUPS[format] : null;
  const season = isCubeSeasonCode(setCode);
  const view = season ? "public_cube_season_events" : "public_recent_trophies";

  const all: RecentTrophy[] = [];
  const pageSize = 1000;
  for (let from = 0; ; from += pageSize) {
    let q = client()
      .from(view)
      .select(RECENT_TROPHY_COLUMNS)
      .eq("set_code", setCode)
      .order("finished_at", { ascending: false, nullsFirst: false })
      .range(from, from + pageSize - 1);
    if (season) q = q.eq("is_trophy", true);
    if (format) q = group ? q.in("format", group) : q.ilike("format", `%${format}%`);
    const { data, error } = await q;
    if (error) throw error;
    const batch = (data ?? []) as Array<Record<string, unknown>>;
    for (const row of batch) all.push(adaptRecentTrophy(row));
    if (batch.length < pageSize) break;
  }
  return all;
}

function adaptRecentTrophy(row: Record<string, unknown>): RecentTrophy {
  return {
    setCode: row.set_code as string,
    slug: row.slug as string,
    displayName: row.display_name as string,
    avatarUrl: (row.avatar_url ?? null) as string | null,
    seventeenlandsEventId: (row.seventeenlands_event_id ?? null) as string | null,
    format: row.format as string,
    colors: row.colors as string,
    wins: row.wins as number,
    losses: row.losses as number,
    finishedAt: row.finished_at as string,
    isTrophy: true,
    endRank: (row.end_rank ?? null) as string | null,
  };
}

// Day 1 trophies plus finished Day 2 runs — Day 2 pays cash without
// necessarily minting a trophy, and in-progress runs stay hidden.
async function fetchLcqRecentTrophiesAndWins(setCode: string): Promise<RecentTrophy[]> {
  const group = FORMAT_RAW_GROUPS.LCQ;
  const [trophiesResp, d2Resp, metaResp] = await Promise.all([
    client()
      .from("public_recent_trophies")
      .select("*")
      .eq("set_code", setCode)
      .in("format", group),
    client()
      .from("public_player_draft_events")
      .select("slug, seventeenlands_event_id, format, colors, wins, losses, finished_at, is_trophy")
      .eq("set_code", setCode)
      .in("format", LCQ_DRAFT_2_FORMATS),
    client()
      .from("public_leaderboard")
      .select("slug, display_name, avatar_url")
      .eq("set_code", setCode),
  ]);
  if (trophiesResp.error) throw trophiesResp.error;
  if (d2Resp.error) throw d2Resp.error;
  if (metaResp.error) throw metaResp.error;

  const metaBySlug = new Map<string, Record<string, unknown>>();
  for (const m of (metaResp.data ?? []) as Array<Record<string, unknown>>) {
    metaBySlug.set(m.slug as string, m);
  }

  const rows = ((trophiesResp.data ?? []) as Array<Record<string, unknown>>).map(adaptRecentTrophy);
  const seen = new Set(rows.map((r) => r.seventeenlandsEventId).filter(Boolean));
  for (const raw of (d2Resp.data ?? []) as Array<Record<string, unknown>>) {
    const eventId = (raw.seventeenlands_event_id ?? null) as string | null;
    if (eventId && seen.has(eventId)) continue;
    const isTrophy = Boolean(raw.is_trophy);
    const losses = (raw.losses as number) ?? 0;
    if (!isTrophy && losses < 2) continue;
    const slug = raw.slug as string;
    const m = metaBySlug.get(slug);
    rows.push({
      setCode,
      slug,
      displayName: (m?.display_name as string) ?? slug,
      avatarUrl: (m?.avatar_url as string | null) ?? null,
      seventeenlandsEventId: eventId,
      format: raw.format as string,
      colors: (raw.colors as string) ?? "",
      wins: (raw.wins as number) ?? 0,
      losses,
      finishedAt: (raw.finished_at as string) ?? "",
      isTrophy,
    });
  }
  return rows.sort((a, b) => (a.finishedAt < b.finishedAt ? 1 : a.finishedAt > b.finishedAt ? -1 : 0));
}

export async function fetchPodEvents(setCode: string): Promise<PodEventSummary[]> {
  const { data, error } = await client()
    .from("public_pod_draft_events")
    .select("*")
    .eq("set_code", setCode)
    .order("event_time", { ascending: false });
  if (error) throw error;
  return (data ?? []).map((r) => adaptPodEvent(r as Record<string, unknown>));
}

export async function fetchPodEventParticipants(
  eventId: string,
): Promise<PodEventParticipantRow[]> {
  const { data, error } = await client()
    .from("public_pod_draft_event_participants")
    .select("*")
    .eq("event_id", eventId);
  if (error) throw error;
  return (data ?? []).map((r) => adaptPodEventParticipant(r as Record<string, unknown>));
}

export async function fetchPodDraftArtifact(eventId: string): Promise<PodDraftArtifact | null> {
  const { data, error } = await client()
    .from("public_pod_draft_log")
    .select("draft_log")
    .eq("event_id", eventId)
    .limit(1);
  if (error) throw error;
  return (data?.[0]?.draft_log ?? null) as PodDraftArtifact | null;
}

export async function fetchPodEventBySlug(slug: string): Promise<PodEventSummary | null> {
  const { data, error } = await client()
    .from("public_pod_draft_events")
    .select("*")
    .eq("slug", slug)
    .maybeSingle();
  if (error) throw error;
  if (!data) return null;
  return adaptPodEvent(data as Record<string, unknown>);
}

export async function fetchPodEventMatches(eventId: string): Promise<PodEventMatchRow[]> {
  const { data, error } = await client()
    .from("public_pod_draft_event_matches")
    .select("*")
    .eq("event_id", eventId)
    .order("round", { ascending: true });
  if (error) throw error;
  return (data ?? []).map((r) => adaptPodEventMatch(r as Record<string, unknown>));
}

export async function fetchPodEventReplays(eventId: string): Promise<PodEventReplayRow[]> {
  const { data, error } = await client()
    .from("public_pod_draft_replays")
    .select("*")
    .eq("event_id", eventId)
    .order("game_time", { ascending: true });
  if (error) throw error;
  return (data ?? []).map((r) => adaptPodEventReplay(r as Record<string, unknown>));
}

interface PodParticipantParsed {
  eventId: string;
  finishedAt: string;
  slug: string | null;
  displayName: string;
  avatarUrl: string | null;
  deckColors: string | null;
  placement: number | null;
  wins: number;
  losses: number;
}

function parseRecord(record: string | null | undefined): { wins: number; losses: number } {
  const [w, l] = (record ?? "").split("-");
  return { wins: parseInt(w || "0", 10) || 0, losses: parseInt(l || "0", 10) || 0 };
}

async function fetchPodParticipantsForSet(setCode: string): Promise<PodParticipantParsed[]> {
  const eventsResp = await client()
    .from("public_pod_draft_events")
    .select("event_id, event_time")
    .eq("set_code", setCode);
  if (eventsResp.error) throw eventsResp.error;
  const eventTimeById = new Map<string, string>(
    ((eventsResp.data ?? []) as Array<{ event_id: string; event_time: string }>)
      .map((e) => [e.event_id, e.event_time]),
  );
  if (eventTimeById.size === 0) return [];

  const partsResp = await client()
    .from("public_pod_draft_event_participants")
    .select("event_id, player_slug, player_display_name, avatar_url, deck_colors, record, placement")
    .in("event_id", Array.from(eventTimeById.keys()));
  if (partsResp.error) throw partsResp.error;

  return (partsResp.data ?? []).map((raw) => {
    const r = raw as Record<string, unknown>;
    const slug = (r.player_slug as string | null) ?? null;
    return {
      eventId: r.event_id as string,
      finishedAt: eventTimeById.get(r.event_id as string) ?? "",
      slug,
      displayName: (r.player_display_name as string | null) ?? slug ?? "",
      avatarUrl: (r.avatar_url as string | null) ?? null,
      deckColors: (r.deck_colors as string | null) ?? null,
      placement: (r.placement as number | null) ?? null,
      ...parseRecord(r.record as string | null),
    };
  });
}

async function fetchPodRecentTrophies(setCode: string): Promise<RecentTrophy[]> {
  const parts = await fetchPodParticipantsForSet(setCode);
  return parts
    .filter((p) => p.placement === 1 && p.slug)
    .map((p) => ({
      setCode,
      slug: p.slug!,
      displayName: p.displayName,
      avatarUrl: p.avatarUrl,
      seventeenlandsEventId: null,
      format: "PodDraft",
      colors: p.deckColors ?? "",
      wins: p.wins,
      losses: p.losses,
      finishedAt: p.finishedAt,
    }))
    .sort((a, b) => (a.finishedAt < b.finishedAt ? 1 : a.finishedAt > b.finishedAt ? -1 : 0));
}

async function fetchPodColorsLeaderboard(
  setCode: string,
  colorsFilter: string,
  otherCombos: string[] | null,
): Promise<ColorsLeaderboardRow[]> {
  const parts = await fetchPodParticipantsForSet(setCode);
  const cube = isCubeCode(setCode);
  const otherSet = otherCombos ? new Set(otherCombos) : null;
  const colorMatches = (deckColors: string | null): boolean => {
    if (!deckColors) return false;
    if (colorsFilter === MULTI) return isSoup(deckColors, cube);
    if (colorsFilter === OTHER) {
      if (isSoup(deckColors, cube)) return false;
      return otherSet ? otherSet.has(colorsOf(deckColors)) : false;
    }
    return colorsOf(deckColors) === colorsFilter;
  };

  interface Agg {
    displayName: string;
    avatarUrl: string | null;
    events: number;
    wins: number;
    losses: number;
    trophies: number;
    lastFinishedAt: string;
  }
  const perSlug = new Map<string, Agg>();
  for (const p of parts) {
    if (p.placement === null || !p.slug || !colorMatches(p.deckColors)) continue;
    let agg = perSlug.get(p.slug);
    if (!agg) {
      agg = { displayName: p.displayName, avatarUrl: p.avatarUrl, events: 0, wins: 0, losses: 0, trophies: 0, lastFinishedAt: "" };
      perSlug.set(p.slug, agg);
    }
    agg.events += 1;
    agg.wins += p.wins;
    agg.losses += p.losses;
    if (p.placement === 1) agg.trophies += 1;
    if (p.finishedAt > agg.lastFinishedAt) agg.lastFinishedAt = p.finishedAt;
  }

  return Array.from(perSlug.entries())
    .map(([slug, a]) => ({
      setCode,
      colors: colorsFilter,
      slug,
      displayName: a.displayName,
      avatarUrl: a.avatarUrl,
      rank: 0,
      score: 0,
      trophies: a.trophies,
      events: a.events,
      wins: a.wins,
      losses: a.losses,
      lastCalculatedAt: a.lastFinishedAt || new Date(0).toISOString(),
    }))
    .sort((a, b) => {
      if (b.trophies !== a.trophies) return b.trophies - a.trophies;
      if (b.wins !== a.wins) return b.wins - a.wins;
      return a.slug.localeCompare(b.slug);
    })
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

export async function fetchPodLeaderboard(setCode: string): Promise<PodLeaderboardRow[]> {
  const { data, error } = await client()
    .from("public_player_pod_stats")
    .select("*")
    .eq("set_code", setCode);
  if (error) throw error;
  return (data ?? [])
    .map((r) => adaptPodLeaderboardRow(r as Record<string, unknown>))
    .sort((a, b) => {
      if (b.trophies !== a.trophies) return b.trophies - a.trophies;
      if (b.wins !== a.wins) return b.wins - a.wins;
      return a.events - b.events;
    })
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

export async function fetchPodSetCodes(): Promise<PodSetCode[]> {
  const { data, error } = await client()
    .from("public_pod_draft_events")
    .select("set_code, format_label");
  if (error) throw error;
  const byCode = new Map<string, string | null>();
  for (const r of data ?? []) {
    const row = r as { set_code: string; format_label: string | null };
    if (!byCode.has(row.set_code) || byCode.get(row.set_code) == null) {
      byCode.set(row.set_code, row.format_label ?? null);
    }
  }
  return Array.from(byCode, ([code, label]) => ({ code, label }));
}

function adaptPodEvent(row: Record<string, unknown>): PodEventSummary {
  return {
    eventId: row.event_id as string,
    slug: row.slug as string,
    name: row.name as string,
    setCode: row.set_code as string,
    kind: row.kind === "mock" ? "mock" : "tournament",
    eventDate: row.event_date as string,
    eventTime: row.event_time as string,
    formatLabel: (row.format_label ?? null) as string | null,
    totalRounds: (row.total_rounds ?? 0) as number,
    championPlayerSlug: (row.champion_player_slug ?? null) as string | null,
    championDisplayName: (row.champion_display_name ?? null) as string | null,
    championAvatarUrl: (row.champion_avatar_url ?? null) as string | null,
    championDeckColors: (row.champion_deck_colors ?? null) as string | null,
    championRecord: (row.champion_record ?? null) as string | null,
    participantCount: (row.participant_count ?? 0) as number,
    isFinalized: (row.is_finalized ?? false) as boolean,
    ordinal: (row.ordinal ?? null) as number | null,
    tableIndex: (row.table_index ?? 1) as number,
    isTeamDraft: (row.is_team_draft ?? false) as boolean,
    closedDecklist: (row.closed_decklist ?? false) as boolean,
  };
}

function adaptPodEventParticipant(row: Record<string, unknown>): PodEventParticipantRow {
  return {
    eventId: row.event_id as string,
    displayName: row.display_name as string,
    draftmancerName: (row.draftmancer_name ?? null) as string | null,
    seatIndex: (row.seat_index ?? null) as number | null,
    placement: (row.placement ?? null) as number | null,
    record: (row.record ?? null) as string | null,
    deckColors: (row.deck_colors ?? null) as string | null,
    deckScreenshotUrl: (row.deck_screenshot_url ?? null) as string | null,
    deckScreenshotCaption: (row.deck_screenshot_caption ?? null) as string | null,
    playerSlug: (row.player_slug ?? null) as string | null,
    playerDisplayName: (row.player_display_name ?? null) as string | null,
    avatarUrl: (row.avatar_url ?? null) as string | null,
  };
}

function adaptPodEventMatch(row: Record<string, unknown>): PodEventMatchRow {
  return {
    eventId: row.event_id as string,
    eventName: row.event_name as string,
    round: row.round as number,
    playerAName: row.player_a_name as string,
    playerBName: row.player_b_name as string,
    winnerName: (row.winner_name ?? null) as string | null,
    score: (row.score ?? null) as string | null,
    reportedAt: (row.reported_at ?? null) as string | null,
  };
}

function adaptPodEventReplay(row: Record<string, unknown>): PodEventReplayRow {
  return {
    eventId: row.event_id as string,
    eventName: row.event_name as string,
    eventDate: row.event_date as string,
    setCode: row.set_code as string,
    playerId: row.player_id as string,
    playerSlug: row.player_slug as string,
    playerDisplayName: row.player_display_name as string,
    gameId: row.game_id as string,
    link: row.link as string,
    gameTime: row.game_time as string,
    won: row.won as boolean,
    turns: (row.turns ?? null) as number | null,
    onPlay: (row.on_play ?? null) as boolean | null,
    inferredRound: (row.inferred_round ?? null) as number | null,
  };
}

function adaptPodLeaderboardRow(row: Record<string, unknown>): PodLeaderboardRow {
  return {
    setCode: row.set_code as string,
    rank: 0,
    slug: row.slug as string,
    displayName: row.display_name as string,
    avatarUrl: (row.avatar_url ?? null) as string | null,
    events: (row.events ?? 0) as number,
    wins: (row.wins ?? 0) as number,
    losses: (row.losses ?? 0) as number,
    trophies: (row.trophies ?? 0) as number,
    lastFinishedAt: (row.last_finished_at ?? null) as string | null,
  };
}

// --- P0P1 contest ---

import type { Card, P0P1BallotRow, P0P1Pick, P0P1PickStat, SlotKey } from "../types/p0p1";
import type { RatingsSnapshot } from "./p0p1Results";

const cardLoaders = import.meta.glob<Card[]>(
  "./fixtures/cards-*.ts",
  { import: "default" },
);
const ratingLoaders = import.meta.glob<RatingsSnapshot>(
  "./fixtures/p0p1-ratings-*.ts",
  { import: "default" },
);

export async function fetchP0P1Cards(setCode: string): Promise<Card[]> {
  const key = `./fixtures/cards-${setCode.toLowerCase()}.ts`;
  const loader = cardLoaders[key];
  if (!loader) throw new Error(`No card fixture for set ${setCode}`);
  return loader();
}

export async function fetchP0P1Ratings(setCode: string): Promise<RatingsSnapshot | null> {
  const key = `./fixtures/p0p1-ratings-${setCode.toLowerCase()}.ts`;
  const loader = ratingLoaders[key];
  if (!loader) return null;
  return loader();
}

export async function fetchP0P1Picks(setCode: string): Promise<P0P1Pick[]> {
  const { data, error } = await client()
    .from("p0p1_entries")
    .select("slot, card_name, updated_at")
    .eq("set_code", setCode);
  if (error) throw error;
  return (data ?? []).map((r) => ({
    slot: r.slot as SlotKey,
    cardName: r.card_name,
    lastUpdated: r.updated_at,
  }));
}

export async function upsertP0P1Pick(
  setCode: string,
  slot: SlotKey,
  cardName: string,
): Promise<void> {
  const { data: { user } } = await client().auth.getUser();
  if (!user) throw new Error("Not authenticated");
  const { error } = await client()
    .from("p0p1_entries")
    .upsert(
      { user_id: user.id, set_code: setCode, slot, card_name: cardName, updated_at: new Date().toISOString() },
      { onConflict: "user_id,set_code,slot" },
    );
  if (error) throw error;
}


export async function deleteAllP0P1Picks(setCode: string): Promise<void> {
  const { error } = await client()
    .from("p0p1_entries")
    .delete()
    .eq("set_code", setCode);
  if (error) throw error;
}

export async function fetchP0P1Ballots(setCode: string): Promise<P0P1BallotRow[]> {
  const { data, error } = await client()
    .from("public_p0p1_ballots")
    .select("*")
    .eq("set_code", setCode);
  if (error) throw error;
  return (data ?? []).map((r) => ({
    setCode: r.set_code as string,
    ballotId: r.ballot_id as number,
    name: r.name as string,
    avatarUrl: r.avatar_url as string | null,
    slot: r.slot as SlotKey,
    cardName: r.card_name as string,
  }));
}

export async function fetchP0P1PickStats(setCode: string): Promise<P0P1PickStat[]> {
  const { data, error } = await client()
    .from("public_p0p1_pick_stats")
    .select("*")
    .eq("set_code", setCode);
  if (error) throw error;
  return (data ?? []).map((r) => ({
    setCode: r.set_code as string,
    slot: r.slot as SlotKey,
    cardName: r.card_name as string,
    pickCount: r.pick_count as number,
    pickPct: Number(r.pick_pct),
  }));
}

export const initialAuthUser = null;
