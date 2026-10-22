import { DAILY_ROUNDS, type WheelPack } from "../../../data/draftGames";
import type { GameDay, GameDayRules } from "../gameDay";

export type WheelDay = GameDay<number[]>;

export const NEXT_PACKS_LABEL = "New Packs In";

export const WHEEL_DAY: GameDayRules<number[], WheelPack> = {
  storagePrefix: "wheel-of-fortune-featured",
  roundsPerDay: DAILY_ROUNDS,
  openDays: 2,
  pickFitsRound: (pack, slots) => slots.every((card) => pack.pack.includes(card)),
};
