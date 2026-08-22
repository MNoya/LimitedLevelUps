import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { entryGemsFor, payoutFor } from "./prizes";
import { fetchTrackerDrafts } from "./trackerApi";
import type { PlayerDraftEvent } from "../types/leaderboard";

/** 17lands names the account from games played, so a drafted deck with no match yet has none */
export function arenaDrafts(events: PlayerDraftEvent[] | undefined, accountId: number | null) {
  const arena = (events ?? []).filter((e) => e.format !== "PodDraft");
  if (accountId == null) {
    return arena;
  }
  return arena.filter((e) => e.accountId === accountId || e.accountId == null);
}

/** Card and economy totals the profile header shows, excluding anything its stat strip already has */
export function useTrackerTotals(slug: string | undefined, setCode: string, accountId: number | null) {
  const { data: events } = useQuery({
    queryKey: ["tracker-drafts", slug, setCode],
    queryFn: () => fetchTrackerDrafts(slug!, setCode),
    enabled: !!slug,
  });
  return useMemo(() => {
    const rows = arenaDrafts(events, accountId);
    const t = rows.reduce(
      (acc, e) => {
        const p = payoutFor(e.format, e.wins);
        acc.rares += e.poolRares ?? 0;
        acc.mythics += e.poolMythics ?? 0;
        acc.gems += p?.gems ?? 0;
        acc.spent += entryGemsFor(e.format) ?? 0;
        acc.packs += p?.packs ?? 0;
        return acc;
      },
      { rares: 0, mythics: 0, gems: 0, spent: 0, packs: 0 },
    );
    const n = Math.max(rows.length, 1);
    return {
      drafts: rows.length,
      rares: t.rares,
      avgRares: t.rares / n,
      avgMythics: t.mythics / n,
      gems: t.gems,
      spent: t.spent,
      packs: t.packs,
    };
  }, [events, accountId]);
}

/** Per-draft rates the rare-complete projection needs, over the same drafts the log lists */
export function useDraftRates(slug: string | undefined, setCode: string, accountId: number | null) {
  const { data: events } = useQuery({
    queryKey: ["tracker-drafts", slug, setCode],
    queryFn: () => fetchTrackerDrafts(slug!, setCode),
    enabled: !!slug,
  });
  return useMemo(() => {
    const rows = arenaDrafts(events, accountId);
    if (!rows.length) {
      return { avgRares: null, avgPacksWon: null };
    }

    let rares = 0;
    let packs = 0;
    for (const e of rows) {
      rares += e.poolRares ?? 0;
      packs += payoutFor(e.format, e.wins)?.packs ?? 0;
    }
    return { avgRares: rares / rows.length, avgPacksWon: packs / rows.length };
  }, [events, accountId]);
}
