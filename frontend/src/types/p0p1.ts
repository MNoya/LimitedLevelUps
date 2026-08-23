export interface Card {
  name: string;
  manaCost: string;
  cmc: number;
  colors: string[];
  rarity: "common" | "uncommon" | "rare";
  typeLine: string;
  collectorNumber: string;
  imageSmall: string;
  imageNormal: string;
  imageArtCrop: string;
}

export interface P0P1Pick {
  slot: SlotKey;
  cardName: string;
  lastUpdated: string;
}

/** One contest's window, keyed by set code in the shared `p0p1_contests.json`. Dates are ISO
 * instants so a contest resolves before its set is public anywhere, and so the noon-ET release
 * boundary is computed once in `bot/sets.py` instead of re-derived in the browser. */
export interface ContestConfig {
  name: string;
  release: string;
  previewsOpen: string;
  votingDeadline?: string;
  scoringDate?: string;
  hybridCommonSlots?: boolean;
}

export type SlotKey =
  | "white_common"
  | "blue_common"
  | "black_common"
  | "red_common"
  | "green_common"
  | "multicolor_uncommon"
  | "wildcard_common"
  | "wildcard_uncommon";

export interface SlotDefinition {
  key: SlotKey;
  label: string;
  filter: (card: Card, pickedCards: Set<string>) => boolean;
}

export interface P0P1PickStat {
  setCode: string;
  slot: SlotKey;
  cardName: string;
  pickCount: number;
  pickPct: number;
}

export interface P0P1BallotRow {
  setCode: string;
  ballotId: number;
  name: string;
  avatarUrl: string | null;
  slot: SlotKey;
  cardName: string;
}

export type PickVersusState = "matched" | "minority" | "rogue";

export interface PickVersusSide {
  name: string;
  imageUrl: string;
  pickPct: number;
}

export interface PickVersus {
  slotKey: SlotKey;
  slotLabel: string;
  state: PickVersusState;
  agreed: boolean;
  tiedCount: number;
  crowd: PickVersusSide;
  yours: PickVersusSide;
}
