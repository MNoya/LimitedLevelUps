// Closed Decklist gating (visual-only). A closed pod hides its decklists and pick-by-pick draft log
// on the site until it finishes (is finalized). While closed, an organizer sees every seat, and a
// logged-in player sees only their own seat, matched by the Discord id embedded in the seat avatar.

import { useMemo } from "react";

import { useAuth } from "../auth/useAuth";
import { isPodOrganizer } from "./podOrganizers";
import type { PodEventSummary } from "../types/leaderboard";

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
}): PodDecklistAccess {
  const locked = !!args.closedDecklist && !args.isFinalized;
  const canViewAll = !locked || args.isOrganizer;
  const canViewSeat = (seatAvatarUrl: string | null | undefined) =>
    canViewAll || seatBelongsToViewer(seatAvatarUrl, args.viewerDiscordId);
  return { locked, canViewAll, canViewSeat };
}

/** Identity is stable across renders, so callers may use it as a useMemo/useEffect dependency */
export function usePodDecklistAccess(event: PodEventSummary | null | undefined): PodDecklistAccess {
  const { user } = useAuth();
  const discordId = user?.discordId ?? null;
  const closedDecklist = event?.closedDecklist;
  const isFinalized = event?.isFinalized ?? false;
  return useMemo(
    () => computePodDecklistAccess({
      closedDecklist,
      isFinalized,
      isOrganizer: isPodOrganizer(discordId),
      viewerDiscordId: discordId,
    }),
    [closedDecklist, isFinalized, discordId],
  );
}
