import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../auth/useAuth";
import {
  useP0P1Ballots,
  useP0P1Cards,
  useP0P1FeaturedContest,
  useP0P1PickStats,
  useP0P1Picks,
  useP0P1Ratings,
  useUpsertP0P1Pick,
  useDeleteAllP0P1Picks,
} from "./hooks";
import { SLOTS, buildSlots, P0P1_CONTESTS } from "./p0p1Slots";
import type { FeaturedContest } from "./p0p1Slots";
import { useLocalP0P1Picks, setLocalPick, clearLocalPicks, getLocalPicks } from "./localPicks";
import { p0p1DevEnabled, p0p1Now, useP0P1DevPreset, type P0P1DevPreset } from "./p0p1DevState";
import { syntheticBallotsFromStats } from "./p0p1DevBallots";
import type { AuthUser } from "../auth/AuthContext";
import type { Card, P0P1BallotRow, P0P1PickStat, SlotKey } from "../types/p0p1";
import type { P0P1Phase, RatingsSnapshot } from "./p0p1Results";

const ADVANCE_BEAT_MS = 260;

export function useP0P1Ballot(overrideSetCode?: string) {
  const { user: authUser, loading: authLoading, signIn } = useAuth();
  const devPreset = useP0P1DevPreset();
  const devActive = p0p1DevEnabled && devPreset !== "live";
  const useServerPicks = Boolean(authUser);

  const featured = useP0P1FeaturedContest(overrideSetCode);
  const setCode = featured?.code;
  const scoringDate = featured?.scoringDate;

  const { data: cards, isLoading: cardsLoading } = useP0P1Cards(setCode);
  const { data: serverPicks, isFetched: serverPicksFetched } = useP0P1Picks(useServerPicks ? setCode : undefined);
  const localPicks = useLocalP0P1Picks(setCode ?? "");
  const upsertPick = useUpsertP0P1Pick(setCode ?? "");
  const clearAll = useDeleteAllP0P1Picks(setCode ?? "");
  const [editingSlotKey, setEditingSlotKey] = useState<SlotKey | null>(null);

  const syncDone = useRef(false);
  useEffect(() => {
    if (!useServerPicks || !serverPicks || !setCode || syncDone.current) return;
    syncDone.current = true;
    const local = getLocalPicks(setCode);
    if (local.length === 0) return;
    const serverSlots = new Set(serverPicks.map((p) => p.slot));
    const toSync = local.filter((p) => !serverSlots.has(p.slot));
    for (const p of toSync) {
      upsertPick.mutate({ slot: p.slot, cardName: p.cardName });
    }
    clearLocalPicks(setCode);
  }, [authUser, serverPicks, upsertPick, setCode]);

  const settledServerPicks = serverPicks ?? (serverPicksFetched ? [] : undefined);
  const activePicks = authLoading ? undefined : useServerPicks ? settledServerPicks : localPicks;
  const dataReady = Boolean(featured && cards) && activePicks !== undefined;

  const persistPick = useCallback(
    (slot: SlotKey, cardName: string) => {
      if (!setCode) return;
      if (useServerPicks) {
        upsertPick.mutate({ slot, cardName });
      } else {
        setLocalPick(setCode, slot, cardName);
      }
    },
    [useServerPicks, upsertPick, setCode],
  );

  const handleClearAll = useCallback(() => {
    if (!setCode) return;
    if (useServerPicks) {
      clearAll.mutate();
    } else {
      clearLocalPicks(setCode);
    }
  }, [useServerPicks, clearAll, setCode]);

  const contestSlots = useMemo(
    () => (setCode ? buildSlots(P0P1_CONTESTS[setCode]) : SLOTS),
    [setCode],
  );

  const cardsByName = useMemo(() => {
    if (!cards) return new Map<string, Card>();
    return new Map(cards.map((c) => [c.name, c]));
  }, [cards]);

  const picksBySlot = useMemo(() => {
    if (!activePicks) return new Map<string, string>();
    return new Map(activePicks.map((v) => [v.slot, v.cardName]));
  }, [activePicks]);

  const pickedCards = useMemo(() => new Set(picksBySlot.values()), [picksBySlot]);

  const pickedSlotLabels = useMemo(() => {
    const labels = new Map<string, string>();
    for (const slot of SLOTS) {
      const name = picksBySlot.get(slot.key);
      if (name) labels.set(name, slot.label);
    }
    return labels;
  }, [picksBySlot]);

  const pickedExcept = useCallback(
    (slotKey: SlotKey) => {
      const own = picksBySlot.get(slotKey);
      if (!own) return pickedCards;
      const rest = new Set(pickedCards);
      rest.delete(own);
      return rest;
    },
    [pickedCards, picksBySlot],
  );

  const now = p0p1Now(scoringDate);
  const isPastDeadline = featured ? now > featured.votingDeadline.getTime() : false;
  const isPastScoringDate = featured ? now >= featured.scoringDate.getTime() : false;
  const { data: pickStats, isLoading: pickStatsLoading } = useP0P1PickStats(setCode, isPastDeadline);
  const { data: ratingsSnapshot, error: ratingsError, isLoading: ratingsLoading } = useP0P1Ratings(setCode ?? "");

  useEffect(() => {
    if (ratingsError) console.warn("P0P1 ratings fetch failed", ratingsError);
  }, [ratingsError]);

  const devViewPreset = devActive ? devPreset : "live";
  const user = applyDevUser(authUser, devViewPreset);
  const effectivePicksBySlot = applyDevPicks(picksBySlot, pickStats, devViewPreset);
  const resultsDataReady = Boolean(ratingsSnapshot && cards && pickStats);
  const resultsPending = ratingsLoading || cardsLoading || pickStatsLoading;
  const phase = deriveP0P1Phase(isPastDeadline, isPastScoringDate, ratingsSnapshot ?? undefined, resultsDataReady, resultsPending, devViewPreset);

  const devFinal = devActive && phase === "final";
  const { data: fetchedBallots, error: ballotsError } = useP0P1Ballots(setCode, phase === "final" && !devFinal);
  const ballots = useMemo<P0P1BallotRow[] | undefined>(() => {
    if (!devFinal) return fetchedBallots;
    return pickStats && setCode ? syntheticBallotsFromStats(pickStats, setCode) : undefined;
  }, [devFinal, fetchedBallots, pickStats, setCode]);

  const effectiveBallots = useMemo<P0P1BallotRow[] | undefined>(() => {
    if (!devActive || phase !== "final" || !ballots || effectivePicksBySlot.size === 0 || !setCode) {
      return ballots;
    }
    const youRows: P0P1BallotRow[] = [];
    for (const [slot, cardName] of effectivePicksBySlot) {
      youRows.push({
        setCode,
        ballotId: 0,
        name: user?.username ?? "You",
        avatarUrl: user?.avatarUrl ?? null,
        slot: slot as SlotKey,
        cardName,
      });
    }
    return [...ballots, ...youRows];
  }, [devActive, phase, ballots, effectivePicksBySlot, user, setCode]);

  const ballotReady =
    activePicks !== undefined &&
    (!isPastDeadline ||
      (phase !== "loading" &&
        (phase !== "final" || effectiveBallots !== undefined || Boolean(ballotsError))));

  const scoringFilled = SLOTS.filter((s) => effectivePicksBySlot.has(s.key)).length;
  const isComplete = scoringFilled === SLOTS.length;
  const hasParticipated = isPastDeadline && Boolean(user) && scoringFilled > 0;

  const defaultSlotKey = useMemo(
    () => SLOTS.find((s) => !picksBySlot.has(s.key))?.key ?? SLOTS[0].key,
    [picksBySlot],
  );
  const activeSlotKey = editingSlotKey ?? defaultSlotKey;
  const activeSlot = contestSlots.find((s) => s.key === activeSlotKey)!;

  const nextUnfilledSlot = useCallback(
    (afterKey: SlotKey) => {
      const idx = SLOTS.findIndex((s) => s.key === afterKey);
      if (idx === -1) return afterKey;
      for (let i = 1; i < SLOTS.length; i++) {
        const candidate = SLOTS[(idx + i) % SLOTS.length];
        if (!picksBySlot.has(candidate.key)) return candidate.key;
      }
      return afterKey;
    },
    [picksBySlot],
  );

  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => clearTimeout(advanceTimer.current ?? undefined), []);

  const selectAdvance = useCallback(
    (slot: SlotKey, cardName: string) => {
      persistPick(slot, cardName);
      clearTimeout(advanceTimer.current ?? undefined);
      advanceTimer.current = setTimeout(() => setEditingSlotKey(nextUnfilledSlot(slot)), ADVANCE_BEAT_MS);
    },
    [persistPick, nextUnfilledSlot],
  );

  return {
    featured,
    cards,
    cardsByName,
    dataReady,
    resultsDataReady,
    ballotReady,
    user,
    authLoading,
    signIn,
    picksBySlot: effectivePicksBySlot,
    pickedExcept,
    pickedSlotLabels,
    scoringFilled,
    isComplete,
    isPastDeadline,
    hasParticipated,
    pickStats,
    ratingsSnapshot: ratingsSnapshot ?? undefined,
    phase,
    ballots: effectiveBallots,
    persistPick,
    handleClearAll,
    clearPending: useServerPicks ? clearAll.isPending : false,
    editingSlotKey,
    setEditingSlotKey,
    activeSlotKey,
    activeSlot,
    contestSlots,
    selectAdvance,
  };
}

const FAKE_DEV_USER: AuthUser = {
  id: "dev-preview-user",
  discordId: "0",
  username: "DevPreview",
  avatarUrl: null,
};

function applyDevUser(authUser: AuthUser | null, preset: P0P1DevPreset): AuthUser | null {
  if (preset === "closedLoggedOut" || preset === "finalLoggedOut") return null;
  if (
    preset === "closedComplete" ||
    preset === "closedDidNotVote" ||
    preset === "midwayScoring" ||
    preset === "midwayDidNotVote" ||
    preset === "finalScoring"
  ) return authUser ?? FAKE_DEV_USER;
  return authUser;
}

function applyDevPicks(
  picksBySlot: Map<string, string>,
  pickStats: P0P1PickStat[] | undefined,
  preset: P0P1DevPreset,
): Map<string, string> {
  if (
    preset === "closedLoggedOut" ||
    preset === "closedDidNotVote" ||
    preset === "midwayDidNotVote" ||
    preset === "finalLoggedOut"
  ) {
    return new Map();
  }
  if (
    preset === "closedComplete" ||
    preset === "midwayScoring" ||
    preset === "finalScoring"
  ) {
    return picksBySlot.size > 0 ? picksBySlot : topPickPerSlot(pickStats);
  }
  return picksBySlot;
}

function topPickPerSlot(pickStats: P0P1PickStat[] | undefined): Map<string, string> {
  const topBySlot = new Map<string, P0P1PickStat>();
  for (const stat of pickStats ?? []) {
    const current = topBySlot.get(stat.slot);
    if (!current || stat.pickCount > current.pickCount) topBySlot.set(stat.slot, stat);
  }
  const picks = new Map<string, string>();
  for (const [slot, stat] of topBySlot) picks.set(slot, stat.cardName);
  return picks;
}

export function deriveP0P1Phase(
  isPastDeadline: boolean,
  isPastScoringDate: boolean,
  snapshot: RatingsSnapshot | undefined,
  dataPresent: boolean,
  resultsPending: boolean,
  devPreset: P0P1DevPreset,
): P0P1Phase {
  if (devPreset === "midwayScoring" || devPreset === "midwayDidNotVote") return "midway";
  if (devPreset === "finalScoring" || devPreset === "finalLoggedOut") return "final";
  if (
    devPreset === "closedLoggedOut" ||
    devPreset === "closedComplete" ||
    devPreset === "closedDidNotVote"
  ) return "postVoting";

  if (!isPastDeadline) return "voting";

  if (resultsPending) return "loading";

  if (!isPastScoringDate) {
    if (snapshot?.phase && snapshot.phase !== "final" && dataPresent) return snapshot.phase;
    return "postVoting";
  }

  if (snapshot?.phase === "final" && dataPresent) return "final";
  return "midway";
}
