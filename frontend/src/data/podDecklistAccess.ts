// Visual-only: a closed pod shows a player their own seat until finalized; championships open up after a loss

import { useMemo } from "react";

import { useAuth } from "../auth/useAuth";
import { recordParts } from "../components/pod/PodStandingRow";
import { isPodOrganizer } from "./podOrganizers";
import { isChampionshipEvent } from "./utils";
import type { PodEventParticipantRow, PodEventSummary } from "../types/leaderboard";

export interface PodDecklistAccess {
  locked: boolean;
  canViewAll: boolean;
  canViewSeat: (seatAvatarUrl: string | null | undefined) => boolean;
}

function seatBelongsToViewer(seatAvatarUrl: string | null | undefined, viewerDiscordId: string | null): boolean {
  if (!viewerDiscordId || !seatAvatarUrl) return false;
  return seatAvatarUrl.includes(`/avatars/${viewerDiscordId}/`);
}

export function computePodDecklistAccess(args: {
  closedDecklist: boolean | undefined;
  isFinalized: boolean;
  isOrganizer: boolean;
  viewerDiscordId: string | null;
  championshipSpectator?: boolean;
}): PodDecklistAccess {
  const locked = !!args.closedDecklist && !args.isFinalized;
  const canViewAll = !locked || args.isOrganizer || !!args.championshipSpectator;
  const canViewSeat = (seatAvatarUrl: string | null | undefined) =>
    canViewAll || seatBelongsToViewer(seatAvatarUrl, args.viewerDiscordId);
  return { locked, canViewAll, canViewSeat };
}

export function isChampionshipSpectator(
  viewerDiscordId: string | null,
  participants: Pick<PodEventParticipantRow, "avatarUrl" | "record">[],
): boolean {
  if (!viewerDiscordId) {
    return false;
  }
  const ownSeat = participants.find((participant) => seatBelongsToViewer(participant.avatarUrl, viewerDiscordId));
  return ownSeat === undefined || recordParts(ownSeat.record).losses > 0;
}

/** Identity is stable across renders, so callers may use it as a useMemo/useEffect dependency */
export function usePodDecklistAccess(
  event: PodEventSummary | null | undefined,
  participants?: PodEventParticipantRow[],
): PodDecklistAccess {
  const { user } = useAuth();
  const discordId = user?.discordId ?? null;
  const closedDecklist = event?.closedDecklist;
  const isFinalized = event?.isFinalized ?? false;
  const championship = event ? isChampionshipEvent(event.name) : false;
  const spectator = championship && participants !== undefined && isChampionshipSpectator(discordId, participants);
  return useMemo(
    () => computePodDecklistAccess({
      closedDecklist,
      isFinalized,
      isOrganizer: isPodOrganizer(discordId),
      viewerDiscordId: discordId,
      championshipSpectator: spectator,
    }),
    [closedDecklist, isFinalized, discordId, spectator],
  );
}
