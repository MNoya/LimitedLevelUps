// Arena prize tables, indexed by wins. Reconstructed from the MSH, SOS, TMT and ECL
// deck logs of the tracker spreadsheet, so every entry below is an observed payout.
//
// Premier, Quick and PickTwo are Bo1, so the index is game wins. Traditional is Bo3 and
// draft_events.wins already holds match wins, so its index is 0..3.

export interface Payout {
  gems: number;
  packs: number;
}

interface QueuePrizes {
  entryGems: number;
  payouts: Payout[];
}

const PRIZES: Record<string, QueuePrizes> = {
  PremierDraft: {
    entryGems: 1500,
    payouts: [
      { gems: 50, packs: 1 },
      { gems: 100, packs: 1 },
      { gems: 250, packs: 2 },
      { gems: 1000, packs: 2 },
      { gems: 1400, packs: 3 },
      { gems: 1600, packs: 4 },
      { gems: 1800, packs: 5 },
      { gems: 2200, packs: 6 },
    ],
  },
  TradDraft: {
    entryGems: 1500,
    payouts: [
      { gems: 100, packs: 1 },
      { gems: 250, packs: 1 },
      { gems: 1000, packs: 3 },
      { gems: 2500, packs: 6 },
    ],
  },
  QuickDraft: {
    entryGems: 750,
    payouts: [
      { gems: 50, packs: 1 },
      { gems: 100, packs: 1 },
      { gems: 200, packs: 1 },
      { gems: 300, packs: 1 },
      { gems: 450, packs: 1 },
      { gems: 650, packs: 1 },
      { gems: 850, packs: 1 },
      { gems: 950, packs: 2 },
    ],
  },
  PickTwoDraft: {
    entryGems: 0,
    payouts: [
      { gems: 50, packs: 1 },
      { gems: 150, packs: 1 },
      { gems: 800, packs: 1 },
      { gems: 1000, packs: 2 },
      { gems: 1300, packs: 3 },
    ],
  },
};

/** Null when the queue has no reconstructed table, so callers show a blank instead of a wrong number */
export function payoutFor(format: string, wins: number): Payout | null {
  const queue = PRIZES[format];
  if (!queue) return null;
  return queue.payouts[Math.min(Math.max(wins, 0), queue.payouts.length - 1)] ?? null;
}

export function entryGemsFor(format: string): number | null {
  return PRIZES[format]?.entryGems ?? null;
}

export function hasPrizeTable(format: string): boolean {
  return format in PRIZES;
}
