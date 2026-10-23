import { useMemo } from "react";
import {
  useChampionshipRsvps,
  useChampionshipSeeds,
  useLeaderboard,
  usePodSeasonResults,
  useSets,
} from "../../data/hooks";
import { aggregatePodStandings, podSeasons } from "../../data/podSeasons";
import {
  CHAMPIONSHIP_INVITE_DEPTH,
  pickPodWildcard,
  projectChampionshipSeats,
  type ChampionshipEntrant,
} from "../../data/setChampionship";
import { stripDiscriminator } from "../../data/utils";
import type {
  LeaderboardRow,
  PodChampionshipRsvpRow,
  PodChampionshipSeedRow,
  PodLeaderboardRow,
} from "../../types/leaderboard";

export interface ChampionshipField {
  frozen: boolean;
  frozenAt: string | null;
  eventAt: string | null;
  loading: boolean;
  invited: ChampionshipEntrant[];
  seats: ChampionshipEntrant[];
}

export function useChampionshipField(setCode: string): ChampionshipField {
  const { data: seeds, isLoading: seedsLoading } = useChampionshipSeeds(setCode);
  const latestSeed = latestEventSeed(seeds ?? []);
  const eventId = latestSeed?.eventId ?? null;
  const frozen = eventId !== null;
  const { data: rsvps, isLoading: rsvpsLoading } = useChampionshipRsvps(eventId ?? undefined);
  const { data: board, isLoading: boardLoading } = useLeaderboard(frozen ? undefined : setCode);
  const { data: sets } = useSets();
  const season = frozen ? undefined : podSeasons(sets).find((entry) => entry.code === setCode);
  const { data: podResults, isLoading: podLoading } = usePodSeasonResults(season);

  const entrants = useMemo(() => {
    if (eventId !== null) {
      const eventSeeds = (seeds ?? []).filter((seed) => seed.eventId === eventId);
      return frozenEntrants(eventSeeds, rsvps ?? []);
    }
    return projectedEntrants(board ?? [], aggregatePodStandings(podResults) ?? []);
  }, [eventId, seeds, rsvps, board, podResults]);

  const seats = useMemo(() => projectChampionshipSeats(entrants), [entrants]);
  const invited = useMemo(
    () => entrants.filter((entrant) => entrant.rank <= CHAMPIONSHIP_INVITE_DEPTH || entrant.wildcard),
    [entrants],
  );
  const loading = seedsLoading || (frozen ? rsvpsLoading : boardLoading || podLoading);
  return {
    frozen,
    frozenAt: latestSeed?.frozenAt ?? null,
    eventAt: latestSeed?.eventTime ?? null,
    loading,
    invited,
    seats,
  };
}

function latestEventSeed(seeds: PodChampionshipSeedRow[]): PodChampionshipSeedRow | null {
  let latest: PodChampionshipSeedRow | null = null;
  for (const seed of seeds) {
    if (latest === null || seed.eventTime > latest.eventTime) {
      latest = seed;
    }
  }
  return latest;
}

function frozenEntrants(seeds: PodChampionshipSeedRow[], rsvps: PodChampionshipRsvpRow[]): ChampionshipEntrant[] {
  const answers = new Map<string, PodChampionshipRsvpRow>();
  for (const rsvp of rsvps) {
    answers.set(rsvp.playerSlug ?? rsvp.displayName, rsvp);
  }
  const entrants: ChampionshipEntrant[] = seeds.map((seed) => {
    const key = seed.playerSlug ?? seed.displayName;
    const answer = answers.get(key);
    answers.delete(key);
    return {
      rank: seed.rank,
      slug: seed.playerSlug,
      displayName: stripDiscriminator(seed.displayName),
      avatarUrl: seed.avatarUrl,
      score: seed.score,
      trophies: seed.trophies,
      wildcard: seed.wildcard,
      rsvp: answer?.rsvp ?? null,
    };
  });
  for (const unseeded of answers.values()) {
    entrants.push({
      rank: Number.MAX_SAFE_INTEGER,
      slug: unseeded.playerSlug,
      displayName: stripDiscriminator(unseeded.displayName),
      avatarUrl: unseeded.avatarUrl,
      score: 0,
      trophies: null,
      wildcard: false,
      rsvp: unseeded.rsvp,
    });
  }
  return entrants;
}

function projectedEntrants(fullBoard: LeaderboardRow[], podStandings: PodLeaderboardRow[]): ChampionshipEntrant[] {
  const board = fullBoard.filter((row) => row.rank > 0);
  const wildcardSlug = pickPodWildcard(board, podStandings);
  const entrants: ChampionshipEntrant[] = board.map((row) => ({
    rank: row.rank,
    slug: row.slug,
    displayName: stripDiscriminator(row.displayName),
    avatarUrl: row.avatarUrl,
    score: row.score,
    trophies: row.trophies,
    wildcard: row.slug === wildcardSlug,
    rsvp: null,
  }));
  const wildcardOffBoard = podStandings.find(
    (standing) => standing.slug === wildcardSlug && !board.some((row) => row.slug === wildcardSlug),
  );
  if (wildcardOffBoard) {
    entrants.push({
      rank: board.length + 1,
      slug: wildcardOffBoard.slug,
      displayName: stripDiscriminator(wildcardOffBoard.displayName),
      avatarUrl: wildcardOffBoard.avatarUrl,
      score: 0,
      trophies: wildcardOffBoard.trophies,
      wildcard: true,
      rsvp: null,
    });
  }
  return entrants;
}
