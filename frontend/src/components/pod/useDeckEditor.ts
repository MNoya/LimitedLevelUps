import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { fetchDeckEditAccess, saveDeckSplit } from "../../data/adminApi";
import { deckPool, resolveDeckSplit } from "../../data/draft-artifact";
import type { DeckPool, DeckSplit, Mainboard, PodDraftArtifact } from "../../types/leaderboard";

export type DeckSaveStatus = "clean" | "dirty" | "saving" | "saved";

export interface DeckChanges {
  added: string[];
  removed: string[];
}

export interface DeckEditor {
  mainboard: Mainboard;
  pool: DeckPool;
  status: DeckSaveStatus;
  error: string | null;
  changes: DeckChanges;
  track: (mainPositions: number[]) => void;
  save: () => Promise<boolean>;
}

export function useDeckEditor(
  artifact: PodDraftArtifact | null | undefined,
  eventId: string,
  seat: number,
): DeckEditor | undefined {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { data: access } = useQuery({
    queryKey: ["deck-edit-access", eventId, user?.discordId],
    queryFn: () => fetchDeckEditAccess(eventId),
    enabled: !!user && !!eventId,
    staleTime: Infinity,
    retry: false,
  });
  const canEdit = !!access && (access.staff || access.seats.includes(seat));
  const [pending, setPending] = useState<DeckSplit | null>(null);
  const [status, setStatus] = useState<DeckSaveStatus>("clean");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPending(null);
    setStatus("clean");
    setError(null);
  }, [eventId, seat]);

  const stored = artifact?.decks?.[seat];
  const deck = useMemo(() => (artifact && stored ? deckPool(artifact, stored) : null), [artifact, stored]);
  const mainboard = useMemo(() => (artifact && stored ? resolveDeckSplit(artifact, stored) : null), [artifact, stored]);
  const changes = useMemo(
    () => (artifact && stored && pending ? mainChanges(artifact, stored.main, pending.main) : NO_CHANGES),
    [artifact, stored, pending],
  );
  if (!canEdit || !artifact || !stored || !deck || !mainboard) {
    return undefined;
  }

  const track = (mainPositions: number[]) => {
    const main = mainPositions.map((position) => deck.ids[position]);
    const inMain = new Set(main);
    const split = { main, side: deck.ids.filter((id) => !inMain.has(id)) };
    const diff = mainChanges(artifact, stored.main, split.main);
    if (diff.added.length === 0 && diff.removed.length === 0) {
      setPending(null);
      setStatus((current) => (current === "saved" ? "saved" : "clean"));
      return;
    }
    setPending(split);
    setStatus("dirty");
    setError(null);
  };

  const save = async () => {
    if (!pending) {
      return true;
    }
    setStatus("saving");
    try {
      const saved = await saveDeckSplit(eventId, seat, pending);
      queryClient.setQueryData<PodDraftArtifact>(["pod-draft-artifact", eventId], (prev) =>
        prev?.decks ? { ...prev, decks: prev.decks.map((deck, i) => (i === seat ? saved : deck)) } : prev,
      );
      queryClient.invalidateQueries({ queryKey: ["pod-card-stats"] });
      queryClient.invalidateQueries({ queryKey: ["pod-card-decks"] });
      setPending(null);
      setStatus("saved");
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("dirty");
      return false;
    }
  };

  return { mainboard, pool: deck.pool, status, error, changes, track, save };
}

const NO_CHANGES: DeckChanges = { added: [], removed: [] };

const mainChanges = (artifact: PodDraftArtifact, before: number[], after: number[]): DeckChanges => {
  const nameOf = (id: number) => artifact.cards[id]?.n ?? "";
  const was = new Set(before);
  const is = new Set(after);
  const added = after.filter((id) => !was.has(id)).map(nameOf);
  const removed = before.filter((id) => !is.has(id)).map(nameOf);
  return { added: added.sort(), removed: removed.sort() };
};
