import { useQuery } from "@tanstack/react-query";

import { isDiscordCdnUrl, isDiscordUrlFresh, refreshDeckUrl } from "../../../data/refresh-deck-url";
import type { TrophyMageDeck } from "../../../data/trophyMage";
import { cachedImageUrl } from "../../../lib/dev-image-cache";

export function useDeckImage(deck: TrophyMageDeck, eventId: string): { url: string | null; resolving: boolean } {
  const stored = deck.deckScreenshotUrl;
  const needsRefresh = isDiscordCdnUrl(stored) && !isDiscordUrlFresh(stored);
  const { data, isPending } = useQuery({
    queryKey: ["trophy-deck-image", eventId, deck.participantDisplayName],
    queryFn: async () =>
      needsRefresh ? ((await refreshDeckUrl(eventId, deck.participantDisplayName)) ?? stored) : stored,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return { url: data ? cachedImageUrl(data) : null, resolving: isPending };
}
