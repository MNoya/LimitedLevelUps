import { useEffect, useMemo, useRef } from "react";
import { useFantasyLineup, useFantasyPickWriter } from "../../data/hooks";
import { SLOTS, type Lineup, type SlotKey, type useLineupPicker } from "./fantasyField";
import type { LiveEvent } from "./fantasyLive";
import type { FantasySavedPick } from "../../types/fantasy";

type Picker = ReturnType<typeof useLineupPicker>;

type StoredSlot = { dayOne?: number; replacement?: number };

export function usePersistedLineup(picker: Picker, live: LiveEvent, signedIn: boolean, writable: boolean): Lineup | null {
  const { data: saved, isFetching } = useFantasyLineup(live.event.code, signedIn);
  const stored = useRef<Map<SlotKey, StoredSlot> | null>(null);
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
    if (!signedIn) {
      stored.current = null;
      return;
    }
    if (!saved || isFetching || stored.current) {
      return;
    }
    stored.current = storedSlots(saved, replacementRound);
    const lineup: Lineup = {};
    for (const [slot, picks] of stored.current) {
      const player = live.byId.get((picks.replacement ?? picks.dayOne) as number);
      if (player) {
        lineup[slot] = player;
      }
    }
    picker.setLineup(lineup);
    picker.setActiveSlot(pickingDayOne ? (SLOTS.find((slot) => !lineup[slot.key])?.key ?? null) : null);
  }, [signedIn, saved, isFetching, live, replacementRound, pickingDayOne]);

  useEffect(() => {
    const current = stored.current;
    if (!writable || !current) {
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

  return dayOneLineup;
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
