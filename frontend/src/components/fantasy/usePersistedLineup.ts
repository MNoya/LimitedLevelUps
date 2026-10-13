import { useEffect, useMemo, useRef } from "react";
import { useFantasyLineup, useFantasyPickWriter } from "../../data/hooks";
import { SLOTS, type Lineup, type SlotKey, type useLineupPicker } from "./fantasyField";
import type { LiveEvent } from "./fantasyLive";
import type { FantasySavedPick } from "../../types/fantasy";
import { picksAtPreviewPhase } from "./fantasyDevState";
import { clearLocalLineup, readLocalLineup, writeLocalLineup, type LocalLineup } from "../../data/localFantasyLineup";

type Picker = ReturnType<typeof useLineupPicker>;

type StoredSlot = { dayOne?: number; replacement?: number };

export function usePersistedLineup(
  picker: Picker,
  live: LiveEvent,
  signedIn: boolean,
  writable: boolean,
  fieldLoading: boolean,
): { dayOneLineup: Lineup | null; restoring: boolean } {
  const { data: fetched, isFetching, isLoading } = useFantasyLineup(live.event.code, signedIn && !live.demo);
  const allSaved = live.demo ? live.demo.ownLineup : fetched;
  const saved = useMemo(
    () => (allSaved && live.readOnly ? picksAtPreviewPhase(allSaved, live.phase) : allSaved),
    [allSaved, live.readOnly, live.phase],
  );
  const loaded = signedIn || live.demo !== null;
  const stored = useRef<Map<SlotKey, StoredSlot> | null>(null);
  const localRestored = useRef(false);
  const writer = useFantasyPickWriter(live.event.code, () => {
    stored.current = null;
  });
  const replacementRound = live.cutRound + 1;
  const pickingDayOne = live.phase === "picking";

  const dayOneLineup = useMemo(() => {
    if (!saved) {
      return null;
    }
    const lineup: Lineup = {};
    for (const pick of saved) {
      const player = live.byId.get(pick.playerId);
      if (pick.fromRound === 1 && player) {
        lineup[pick.slot as SlotKey] = player;
      }
    }
    return lineup;
  }, [saved, live]);

  useEffect(() => {
    const eventCode = live.event.code;
    if (!loaded) {
      stored.current = null;
      if (!fieldLoading && pickingDayOne && !localRestored.current) {
        localRestored.current = true;
        showLineup(addLocalPicks({}, readLocalLineup(eventCode), live));
      }
      return;
    }
    if (!saved || isFetching || fieldLoading || stored.current) {
      return;
    }
    stored.current = storedSlots(saved, replacementRound);
    const lineup = lineupFromStored(stored.current, live);
    const local = readLocalLineup(eventCode);
    clearLocalLineup(eventCode);
    showLineup(writable && pickingDayOne ? addLocalPicks(lineup, local, live) : lineup);
  }, [loaded, saved, isFetching, fieldLoading, live, replacementRound, pickingDayOne, writable]);

  useEffect(() => {
    if (loaded || !localRestored.current || !pickingDayOne || live.readOnly) {
      return;
    }
    writeLocalLineup(live.event.code, localLineupOf(picker.lineup));
  }, [loaded, picker.lineup, pickingDayOne]);

  const showLineup = (lineup: Lineup) => {
    picker.setLineup(lineup);
    picker.setActiveSlot(pickingDayOne ? (SLOTS.find((slot) => !lineup[slot.key])?.key ?? null) : null);
  };

  useEffect(() => {
    const current = stored.current;
    if (!writable || !current) {
      return;
    }
    if (pickingDayOne && removedDayOnePicks(current, picker.lineup) > 1) {
      const savedLineup = lineupFromStored(current, live);
      if (removedDayOnePicks(current, savedLineup) === 0) {
        picker.setLineup(savedLineup);
      }
      return;
    }
    for (const slot of SLOTS) {
      const wanted = picker.lineup[slot.key]?.id;
      const picks = current.get(slot.key) ?? {};
      if (pickingDayOne) {
        persistDayOne(slot.key, wanted, picks);
      } else {
        persistReplacement(slot.key, wanted, picks);
      }
      current.set(slot.key, picks);
    }
  }, [writable, picker.lineup, pickingDayOne]);

  const persistDayOne = (slot: SlotKey, wanted: number | undefined, picks: StoredSlot) => {
    if (wanted === picks.dayOne) {
      return;
    }
    if (wanted === undefined) {
      writer.remove({ slot, fromRound: 1 });
    } else {
      writer.save({ slot, playerId: wanted, fromRound: 1 });
    }
    picks.dayOne = wanted;
  };

  const persistReplacement = (slot: SlotKey, wanted: number | undefined, picks: StoredSlot) => {
    if (wanted === undefined || wanted === (picks.replacement ?? picks.dayOne)) {
      return;
    }
    if (wanted === picks.dayOne) {
      writer.remove({ slot, fromRound: replacementRound });
      picks.replacement = undefined;
      return;
    }
    writer.save({ slot, playerId: wanted, fromRound: replacementRound });
    picks.replacement = wanted;
  };

  return { dayOneLineup, restoring: isLoading || fieldLoading };
}

function addLocalPicks(lineup: Lineup, local: LocalLineup, live: LiveEvent): Lineup {
  const merged: Lineup = { ...lineup };
  const taken = new Set(Object.values(merged).map((player) => player?.id));
  for (const slot of SLOTS) {
    const player = live.byId.get(local[slot.key] as number);
    if (!merged[slot.key] && player && !taken.has(player.id)) {
      merged[slot.key] = player;
      taken.add(player.id);
    }
  }
  return merged;
}

function localLineupOf(lineup: Lineup): LocalLineup {
  const local: LocalLineup = {};
  for (const slot of SLOTS) {
    const id = lineup[slot.key]?.id;
    if (id !== undefined) {
      local[slot.key] = id;
    }
  }
  return local;
}

function lineupFromStored(stored: Map<SlotKey, StoredSlot>, live: LiveEvent): Lineup {
  const lineup: Lineup = {};
  for (const [slot, picks] of stored) {
    const player = live.byId.get((picks.replacement ?? picks.dayOne) as number);
    if (player) {
      lineup[slot] = player;
    }
  }
  return lineup;
}

function removedDayOnePicks(stored: Map<SlotKey, StoredSlot>, lineup: Lineup): number {
  let removed = 0;
  for (const [slot, picks] of stored) {
    if (picks.dayOne !== undefined && !lineup[slot]) {
      removed += 1;
    }
  }
  return removed;
}

function storedSlots(saved: FantasySavedPick[], replacementRound: number): Map<SlotKey, StoredSlot> {
  const slots = new Map<SlotKey, StoredSlot>();
  for (const pick of saved) {
    const slot = pick.slot as SlotKey;
    const picks = slots.get(slot) ?? {};
    if (pick.fromRound === 1) {
      picks.dayOne = pick.playerId;
    } else if (pick.fromRound === replacementRound) {
      picks.replacement = pick.playerId;
    }
    slots.set(slot, picks);
  }
  return slots;
}
