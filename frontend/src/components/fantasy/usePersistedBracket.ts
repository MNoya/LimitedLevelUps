import { useEffect, useRef, useState } from "react";
import { useFantasyBracketWriter, useFantasyOwnBracket } from "../../data/hooks";
import { fullName } from "./fantasyField";
import { BRACKET_KEY, BRACKET_MATCHES, type BracketMatchKey, type BracketPicks, type GameScore } from "./fantasyTop8";
import type { LiveEvent } from "./fantasyLive";

export function usePersistedBracket(
  live: LiveEvent,
  signedIn: boolean,
  writable: boolean,
  fieldLoading: boolean,
): [BracketPicks, (picks: BracketPicks) => void] {
  const { data: fetched, isFetching } = useFantasyOwnBracket(live.event.code, signedIn && !live.demo);
  const saved = live.demo ? live.demo.ownBracket : fetched;
  const [picks, setPicks] = useState<BracketPicks>({});
  const stored = useRef<BracketPicks | null>(null);
  const writer = useFantasyBracketWriter(live.event.code, () => {
    stored.current = null;
  });

  useEffect(() => {
    if (!saved || isFetching || fieldLoading || stored.current) {
      return;
    }
    const loaded: BracketPicks = {};
    for (const pick of saved) {
      const key = BRACKET_KEY[pick.position];
      const winner = live.byId.get(pick.winnerId);
      if (key && winner) {
        loaded[key] = { winner: fullName(winner), games: (pick.games ?? undefined) as GameScore | undefined };
      }
    }
    stored.current = loaded;
    setPicks(loaded);
  }, [saved, isFetching, fieldLoading, live]);

  const update = (next: BracketPicks) => {
    setPicks(next);
    const current = stored.current;
    if (!writable || !current) {
      return;
    }
    for (const match of BRACKET_MATCHES) {
      persistPick(match.key, next, current);
    }
  };

  const persistPick = (key: BracketMatchKey, next: BracketPicks, current: BracketPicks) => {
    const wanted = next[key];
    const before = current[key];
    if (wanted?.winner === before?.winner && wanted?.games === before?.games) {
      return;
    }
    const position = POSITION_OF[key];
    const winner = wanted ? live.byName.get(wanted.winner) : undefined;
    if (!wanted || !winner?.id) {
      if (before) {
        writer.remove(position);
      }
      delete current[key];
      return;
    }
    writer.save({ position, winnerId: winner.id, games: wanted.games ?? null });
    current[key] = wanted;
  };

  return [picks, update];
}

const POSITION_OF: Record<BracketMatchKey, string> = {
  qf1: "QF1",
  qf2: "QF2",
  qf3: "QF3",
  qf4: "QF4",
  sf1: "SF1",
  sf2: "SF2",
  final: "F",
};
