import { TROPHY_DAILY_ROUNDS, type TrophyCalls, type TrophyMageRound } from "../../../data/trophyMage";
import type { GameDay, GameDayRules } from "../gameDay";

export type TrophyDay = GameDay<TrophyCalls>;

export const TROPHY_DAY: GameDayRules<TrophyCalls, TrophyMageRound> = {
  storagePrefix: "trophy-mage-daily",
  roundsPerDay: TROPHY_DAILY_ROUNDS,
  openDays: 3,
};
