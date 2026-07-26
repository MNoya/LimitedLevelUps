// Hook layer (spec §3) — abstracts the data source from components.
//
// Components import `useLeaderboard`, `usePlayerProfile`, etc; they never see
// fetch logic, fixtures, or supabase. Wired through TanStack Query so caching
// keys, stale-time, and idle prefetch sit in one place.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import {
  fetchAllRecentTrophies,
  fetchAvailableFormats,
  fetchColorsLeaderboard,
  fetchColorsSummary,
  fetchCubeSeasons,
  fetchP0P1Cards,
  fetchP0P1Ballots,
  fetchP0P1PickStats,
  fetchP0P1Picks,
  fetchFormatColorsLeaderboard,
  fetchFormatLeaderboard,
  fetchFormatRecentTrophies,
  fetchLeaderboard,
  fetchTrophyLeaderboard,
  fetchOtherColorsLeaderboard,
  fetchPlayerDraftEvents,
  fetchPlayerIdentity,
  fetchPlayerSlugByDiscordId,
  fetchPlayerProfile,
  fetchPodDraftArtifact,
  fetchPodEventBySlug,
  fetchPodEventMatches,
  fetchPodEventParticipants,
  fetchPodEventReplays,
  fetchPodEvents,
  fetchPodLeaderboard,
  fetchPodSetCodes,
  fetchRecentTrophies,
  fetchSets,
  fetchDbEpisodes,
  fetchRecentDbEpisodes,
  upsertP0P1Pick,
  deleteAllP0P1Picks,
  fetchP0P1Ratings,
} from "./api";
import { fetchEpisodes } from "./episodes";
import { fetchDiscordStats } from "./discord";
import { fetchYouTubeVideos, mergeMedia, overlayLiveMedia, toVideoEpisode, type YouTubeVideo } from "./youtube";
import type { P0P1BallotRow, P0P1Pick, SlotKey } from "../types/p0p1";
import type { FeaturedContest } from "./p0p1Slots";
import { resolveContestByCode, resolveFeaturedContest } from "./p0p1Slots";
import { MULTI, OTHER } from "./filters";
const THIRTY_MINUTES = 30 * 60 * 1000;
const ONE_HOUR = 60 * 60 * 1000;

export function useEpisodes() {
  return useQuery({
    queryKey: ["episodes"],
    queryFn: fetchEpisodes,
    staleTime: ONE_HOUR,
  });
}

export function useYouTubeVideos(recent = false) {
  return useQuery({
    queryKey: ["youtube", recent ? "recent" : "full"],
    queryFn: () => fetchYouTubeVideos(recent),
    staleTime: ONE_HOUR,
  });
}

export function useDiscordStats() {
  return useQuery({
    queryKey: ["discord-stats"],
    queryFn: fetchDiscordStats,
    staleTime: ONE_HOUR,
  });
}

export function useDbEpisodes() {
  return useQuery({
    queryKey: ["db-episodes"],
    queryFn: fetchDbEpisodes,
    staleTime: ONE_HOUR,
  });
}

// DB rows are the authoritative, categorized base; the live RSS/YouTube feeds overlay any
// freshly published item the next bot sync hasn't picked up yet, so new drops appear at once.
// The recent-videos list is folded in alongside the full list: it is the same cache the home
// page warms, so a fresh drop's thumbnail resolves from cache instead of flashing the podcast
// cover while the full list refetches cold.
export function useMediaFeed() {
  const db = useDbEpisodes();
  const episodes = useEpisodes();
  const videos = useYouTubeVideos();
  const recentVideos = useYouTubeVideos(true);
  const mergedVideos = useMemo(
    () => mergeVideoLists(recentVideos.data, videos.data),
    [recentVideos.data, videos.data],
  );
  const data = useMemo(() => {
    const live = episodes.data ? mergeMedia(episodes.data, mergedVideos) : undefined;
    if (db.data) {
      return live ? overlayLiveMedia(db.data, live) : db.data;
    }
    if (db.isLoading) {
      return undefined;
    }
    return live;
  }, [db.data, db.isLoading, episodes.data, mergedVideos]);
  return {
    data,
    isLoading: db.isLoading && episodes.isLoading,
    isPending: db.isLoading || episodes.isLoading,
    isError: db.isError && episodes.isError,
    thumbnailsPending: videos.isLoading && recentVideos.isLoading && !db.data,
    setsReady: db.data !== undefined,
  };
}

function mergeVideoLists(recent: YouTubeVideo[] | undefined, full: YouTubeVideo[] | undefined): YouTubeVideo[] {
  const byId = new Map<string, YouTubeVideo>();
  for (const video of recent ?? []) {
    byId.set(video.id, video);
  }
  for (const video of full ?? []) {
    byId.set(video.id, video);
  }
  return [...byId.values()];
}

// DB top-N renders immediately; recent YouTube overlays new video drops in the background, podcasts ride the backend tick
export function useRecentEpisodes(limit = 8) {
  const db = useQuery({
    queryKey: ["recent-episodes", limit],
    queryFn: () => fetchRecentDbEpisodes(limit),
    staleTime: ONE_HOUR,
  });
  const videos = useYouTubeVideos(true);
  const data = useMemo(() => {
    if (!db.data) {
      return undefined;
    }
    return videos.data ? overlayLiveMedia(db.data, videos.data.map(toVideoEpisode)) : db.data;
  }, [db.data, videos.data]);
  return { data, isLoading: db.isLoading };
}

export function useSets() {
  return useQuery({
    queryKey: ["sets"],
    queryFn: fetchSets,
    staleTime: THIRTY_MINUTES,
  });
}

export function useCubeSeasons() {
  return useQuery({
    queryKey: ["cube-seasons"],
    queryFn: fetchCubeSeasons,
    staleTime: THIRTY_MINUTES,
  });
}

export function useAvailableFormats(setCode: string | undefined) {
  return useQuery({
    queryKey: ["available-formats", setCode],
    queryFn: () => fetchAvailableFormats(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

export function useLeaderboard(setCode: string | undefined) {
  return useQuery({
    queryKey: ["leaderboard", setCode],
    queryFn: () => fetchLeaderboard(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

export function useTrophyLeaderboard(setCode: string | undefined) {
  return useQuery({
    queryKey: ["trophy-leaderboard", setCode],
    queryFn: () => fetchTrophyLeaderboard(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

// Per-format leaderboard — switches data source from public_leaderboard to a
// join over public_player_format_breakdown when a format is selected. Returns
// the same row shape so the rendering table doesn't care which is live.
export function useFormatLeaderboard(
  setCode: string | undefined,
  format: string | undefined,
) {
  return useQuery({
    queryKey: ["format-leaderboard", setCode, format],
    queryFn: () => fetchFormatLeaderboard(setCode!, format!),
    enabled: !!setCode && !!format,
    staleTime: THIRTY_MINUTES,
  });
}

export function useColorsLeaderboard(
  setCode: string | undefined,
  colors: string | undefined
) {
  return useQuery({
    queryKey: ["colors-leaderboard", setCode, colors],
    queryFn: () => fetchColorsLeaderboard(setCode!, colors!),
    enabled: !!setCode && !!colors,
    staleTime: THIRTY_MINUTES,
  });
}

export function useFormatColorsLeaderboard(
  setCode: string | undefined,
  format: string | undefined,
  archetypes: string | string[] | undefined,
) {
  const key = Array.isArray(archetypes) ? [...archetypes].sort().join(",") : archetypes;
  const enabled = !!setCode && !!format && !!archetypes
    && (Array.isArray(archetypes) ? archetypes.length > 0 : true);
  return useQuery({
    queryKey: ["format-colors-leaderboard", setCode, format, key],
    queryFn: () => fetchFormatColorsLeaderboard(setCode!, format!, archetypes!),
    enabled,
    staleTime: THIRTY_MINUTES,
  });
}

export function useOtherColorsLeaderboard(
  setCode: string | undefined,
  otherCombos: string[] | undefined,
  formatFilter?: string,
) {
  const key = otherCombos ? [...otherCombos].sort().join(",") : null;
  return useQuery({
    queryKey: ["other-colors-leaderboard", setCode, key, formatFilter ?? null],
    queryFn: () => fetchOtherColorsLeaderboard(setCode!, otherCombos!, formatFilter),
    enabled: !!setCode && !!otherCombos && otherCombos.length > 0,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePlayerProfile(slug: string | undefined, setCode: string) {
  return useQuery({
    queryKey: ["player-profile", slug, setCode],
    queryFn: () => fetchPlayerProfile(slug!, setCode),
    enabled: !!slug,
    staleTime: THIRTY_MINUTES,
    placeholderData: keepPreviousData,
  });
}

export function usePlayerIdentity(slug: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["player-identity", slug],
    queryFn: () => fetchPlayerIdentity(slug!),
    enabled: !!slug && enabled,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePlayerSlugByDiscordId(discordId: string | undefined) {
  return useQuery({
    queryKey: ["player-slug-by-discord", discordId],
    queryFn: () => fetchPlayerSlugByDiscordId(discordId!),
    enabled: !!discordId,
    staleTime: THIRTY_MINUTES,
  });
}

export function useDraftEvents(slug: string | undefined, setCode: string) {
  return useQuery({
    queryKey: ["draft-events", slug, setCode],
    queryFn: () => fetchPlayerDraftEvents(slug!, setCode),
    enabled: !!slug,
    staleTime: THIRTY_MINUTES,
    placeholderData: keepPreviousData,
  });
}

export function useColorsSummary(setCode: string | undefined) {
  return useQuery({
    queryKey: ["colors-summary", setCode],
    queryFn: () => fetchColorsSummary(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

// Set-wide most-recent trophies, joined with player display names.
export function useRecentTrophies(setCode: string | undefined, limit = 8) {
  return useQuery({
    queryKey: ["recent-trophies", setCode, limit],
    queryFn: () => fetchRecentTrophies(setCode!, limit),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
    placeholderData: keepPreviousData,
  });
}

// All trophies for the set filtered to a specific format. Backs both Top Colors
// and Recent Trophies in the sidebar when the user picks a format.
export function useFormatScopedTrophies(
  setCode: string | undefined,
  format: string | undefined,
) {
  return useQuery({
    queryKey: ["format-trophies", setCode, format],
    queryFn: () => fetchFormatRecentTrophies(setCode!, format!),
    enabled: !!setCode && !!format,
    staleTime: THIRTY_MINUTES,
  });
}

// Full trophy pool of a set. Backs the sidebar while a rank filter is active.
export function useAllRecentTrophies(setCode: string | undefined) {
  return useQuery({
    queryKey: ["all-trophies", setCode],
    queryFn: () => fetchAllRecentTrophies(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

// On-demand prefetch (spec §6): warm a set board or a player's profile+events on
// intent (hover/focus) rather than eagerly for every set and player on load.
// prefetchQuery dedupes by key, so repeated hovers don't refetch fresh data.
export function usePrefetchers() {
  const qc = useQueryClient();

  const prefetchSet = useCallback(
    (code: string) => {
      qc.prefetchQuery({
        queryKey: ["leaderboard", code],
        queryFn: () => fetchLeaderboard(code),
        staleTime: THIRTY_MINUTES,
      });
    },
    [qc],
  );

  const prefetchPlayer = useCallback(
    (slug: string, setCode: string) => {
      qc.prefetchQuery({
        queryKey: ["player-profile", slug, setCode],
        queryFn: () => fetchPlayerProfile(slug, setCode),
        staleTime: THIRTY_MINUTES,
      });
      qc.prefetchQuery({
        queryKey: ["draft-events", slug, setCode],
        queryFn: () => fetchPlayerDraftEvents(slug, setCode),
        staleTime: THIRTY_MINUTES,
      });
    },
    [qc],
  );

  return { prefetchSet, prefetchPlayer };
}

// Builds the dynamic chip list for the colors filter: 2-color guilds + popular
// 3-color combos that pass the 1% threshold, then MULTI and OTHER catchalls.
// Returns the named chip list and the set of sub-threshold combos that get
// rolled into "OTHER".
export function useColorChips(setCode: string): { chips: string[]; otherCombos: string[]; loading: boolean } {
  const { data, isLoading } = useColorsSummary(setCode);
  return useMemo(() => {
    if (!data) return { chips: [], otherCombos: [], loading: isLoading };
    const total = data
      .filter((r) => r.colors !== MULTI && r.colors !== "")
      .reduce((s, r) => s + r.events, 0);
    if (total === 0) return { chips: [], otherCombos: [], loading: false };
    const threshold = total * 0.01;
    const named: string[] = [];
    const otherCombos: string[] = [];
    for (const r of data) {
      if (r.colors === "" || r.colors === MULTI) continue;
      if (r.colors.length >= 4) continue;
      if (r.events >= threshold) named.push(r.colors);
      else otherCombos.push(r.colors);
    }
    const groupRank = (s: string) => (s.length === 2 ? 0 : s.length === 1 ? 1 : 2);
    named.sort((a, b) => {
      const ra = groupRank(a);
      const rb = groupRank(b);
      if (ra !== rb) return ra - rb;
      const ea = data.find((r) => r.colors === a)?.events ?? 0;
      const eb = data.find((r) => r.colors === b)?.events ?? 0;
      return eb - ea;
    });
    const chips: string[] = [...named];
    const hasMulti = data.some((r) => r.colors === MULTI && r.events > 0);
    if (hasMulti) chips.push(MULTI);
    if (otherCombos.length > 0) chips.push(OTHER);
    return { chips, otherCombos, loading: false };
  }, [data, isLoading]);
}


export function usePodEvents(setCode: string | undefined) {
  return useQuery({
    queryKey: ["pod-events", setCode],
    queryFn: () => fetchPodEvents(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePodEventParticipants(eventId: string | undefined) {
  return useQuery({
    queryKey: ["pod-event-participants", eventId],
    queryFn: () => fetchPodEventParticipants(eventId!),
    enabled: !!eventId,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePodDraftArtifact(eventId: string | undefined) {
  return useQuery({
    queryKey: ["pod-draft-artifact", eventId],
    queryFn: () => fetchPodDraftArtifact(eventId!),
    enabled: !!eventId,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePodEventBySlug(slug: string | undefined) {
  return useQuery({
    queryKey: ["pod-event-by-slug", slug],
    queryFn: () => fetchPodEventBySlug(slug!),
    enabled: !!slug,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePodEventMatches(eventId: string | undefined) {
  return useQuery({
    queryKey: ["pod-event-matches", eventId],
    queryFn: () => fetchPodEventMatches(eventId!),
    enabled: !!eventId,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePodEventReplays(eventId: string | undefined) {
  return useQuery({
    queryKey: ["pod-event-replays", eventId],
    queryFn: () => fetchPodEventReplays(eventId!),
    enabled: !!eventId,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePodLeaderboard(setCode: string | undefined) {
  return useQuery({
    queryKey: ["pod-leaderboard", setCode],
    queryFn: () => fetchPodLeaderboard(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

export function usePodSetCodes() {
  return useQuery({
    queryKey: ["pod-set-codes"],
    queryFn: fetchPodSetCodes,
    staleTime: THIRTY_MINUTES,
  });
}

// --- P0P1 contest ---

export function useP0P1FeaturedContest(overrideCode?: string): FeaturedContest | undefined {
  const { data: sets } = useSets();
  return useMemo(
    () => {
      if (!sets) return undefined;
      if (overrideCode) return resolveContestByCode(sets, overrideCode, Date.now()) ?? undefined;
      return resolveFeaturedContest(sets, Date.now()) ?? undefined;
    },
    [sets, overrideCode],
  );
}

export function useP0P1Cards(setCode: string | undefined) {
  return useQuery({
    queryKey: ["p0p1-cards", setCode],
    queryFn: () => fetchP0P1Cards(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

export function useP0P1Picks(setCode: string | undefined) {
  return useQuery({
    queryKey: ["p0p1-picks", setCode],
    queryFn: () => fetchP0P1Picks(setCode!),
    enabled: !!setCode,
    staleTime: THIRTY_MINUTES,
  });
}

export function useUpsertP0P1Pick(setCode: string) {
  const qc = useQueryClient();
  const queryKey = ["p0p1-picks", setCode];
  return useMutation({
    mutationFn: ({ slot, cardName }: { slot: SlotKey; cardName: string }) =>
      upsertP0P1Pick(setCode, slot, cardName),
    onMutate: async ({ slot, cardName }) => {
      await qc.cancelQueries({ queryKey });
      const prev = qc.getQueryData<P0P1Pick[]>(queryKey);
      qc.setQueryData<P0P1Pick[]>(queryKey, (old = []) => {
        const next = old.filter((v) => v.slot !== slot);
        next.push({ slot, cardName, lastUpdated: new Date().toISOString() });
        return next;
      });
      return { prev };
    },
    // TODO: surface failure to the user (toast or inline banner)
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(queryKey, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey }),
  });
}

export function useP0P1PickStats(setCode: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["p0p1-pick-stats", setCode],
    queryFn: () => fetchP0P1PickStats(setCode!),
    enabled: !!setCode && enabled,
    staleTime: THIRTY_MINUTES,
  });
}

export function useP0P1Ballots(setCode: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["p0p1-ballots", setCode],
    queryFn: (): Promise<P0P1BallotRow[]> => fetchP0P1Ballots(setCode!),
    enabled: !!setCode && enabled,
    staleTime: THIRTY_MINUTES,
  });
}

export function useDeleteAllP0P1Picks(setCode: string) {
  const qc = useQueryClient();
  const queryKey = ["p0p1-picks", setCode];
  return useMutation({
    mutationFn: () => deleteAllP0P1Picks(setCode),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey });
      const prev = qc.getQueryData<P0P1Pick[]>(queryKey);
      qc.setQueryData<P0P1Pick[]>(queryKey, []);
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(queryKey, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey }),
  });
}

// Ratings snapshot is a static fixture — staleTime: Infinity so it never re-fetches.
// Returns null when no fixture exists (contest in voting/post-voting phase).
export function useP0P1Ratings(setCode: string) {
  return useQuery({
    queryKey: ["p0p1-ratings", setCode] as const,
    queryFn: () => fetchP0P1Ratings(setCode),
    staleTime: Infinity,
  });
}
