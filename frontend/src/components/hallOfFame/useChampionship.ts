import { useMemo } from "react";
import {
  useChampionshipEvents,
  useFormatBreakdowns,
  useLeaderboard,
  usePodEventMatches,
  usePlayersDraftEvents,
  usePodEventParticipants,
} from "../../data/hooks";
import {
  buildChampionshipBracket,
  buildSwissRounds,
  championOf,
  championshipPodNumber,
  participantByName,
  playerLabel,
} from "../../data/setChampionship";
import type {
  LeaderboardRow,
  PlayerDraftEvent,
  PlayerFormatBreakdown,
  PodEventSummary,
} from "../../types/leaderboard";

export interface ChampionshipIdentity {
  key: string;
  name: string;
  avatarUrl: string | null;
  slug: string | null;
  unconfirmed?: boolean;
}

export interface ChampionshipPlayer extends ChampionshipIdentity {
  board: LeaderboardRow | undefined;
  formats: PlayerFormatBreakdown[];
  events: PlayerDraftEvent[];
  isChampion: boolean;
}

export function useChampionshipEvent(setCode: string) {
  const { data: events, isLoading } = useChampionshipEvents();
  const forSet = (events ?? []).filter((entry) => entry.setCode === setCode);
  const event = forSet.find((entry) => championshipPodNumber(entry.name) === null);
  const pods = forSet
    .filter((entry) => championshipPodNumber(entry.name) !== null)
    .sort((a, b) => (championshipPodNumber(a.name) ?? 0) - (championshipPodNumber(b.name) ?? 0));
  return { event, pods, isLoading };
}

export function useChampionship(event: PodEventSummary | undefined, live = false) {
  const { data: matches } = usePodEventMatches(event?.eventId, live);
  const { data: participants } = usePodEventParticipants(event?.eventId, live);
  const rounds = useMemo(
    () => buildSwissRounds(matches ?? [], event?.totalRounds ?? 3),
    [matches, event?.totalRounds],
  );
  const bracket = useMemo(() => buildChampionshipBracket(rounds), [rounds]);
  const champion = championOf(rounds);
  const byName = useMemo(() => participantByName(participants ?? []), [participants]);
  const identities = useMemo(
    () =>
      (participants ?? []).map((participant) => ({
        key: participant.displayName,
        name: playerLabel(participant, participant.displayName),
        avatarUrl: participant.avatarUrl,
        slug: participant.playerSlug,
      })),
    [participants],
  );
  const { players: unsorted, statsLoading } = useChampionshipPlayers(event?.setCode, identities, champion);
  const players = useMemo(
    () =>
      [...unsorted].sort(
        (a, b) => (a.board?.rank ?? Number.MAX_SAFE_INTEGER) - (b.board?.rank ?? Number.MAX_SAFE_INTEGER),
      ),
    [unsorted],
  );
  return { statsLoading, bracket, champion, byName, players };
}

export function useChampionshipPlayers(
  setCode: string | undefined,
  identities: ChampionshipIdentity[],
  championKey: string | null = null,
) {
  const { data: board, isLoading: boardLoading } = useLeaderboard(setCode);
  const slugs = useMemo(
    () => identities.flatMap((identity) => (identity.slug ? [identity.slug] : [])),
    [identities],
  );
  const { data: formats, isLoading: formatsLoading } = useFormatBreakdowns(setCode, slugs);
  const { data: draftEvents, isLoading: eventsLoading } = usePlayersDraftEvents(setCode, slugs);
  const players = useMemo(
    () =>
      identities.map(
        (identity): ChampionshipPlayer => ({
          ...identity,
          board: board?.find((row) => row.slug === identity.slug),
          formats: (formats ?? []).filter((row) => row.slug === identity.slug),
          events: (draftEvents ?? []).filter((row) => row.slug === identity.slug),
          isChampion: identity.key === championKey,
        }),
      ),
    [identities, board, formats, draftEvents, championKey],
  );
  return { players, statsLoading: boardLoading || formatsLoading || eventsLoading };
}
