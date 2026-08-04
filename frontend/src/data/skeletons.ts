import type { ArtifactCard } from "../types/leaderboard";

// Baked once because a skeleton is never revised; source: sealeddeck.tech/api/pools/<poolId>?columns=true
// where `columns` is the top half and `splitColumns` the half below the divider. Mana values come from
// Scryfall: sealeddeck stores hand-placed columns whose index does not track mana value.

type SkeletonRow = [name: string, cmc: number];

interface SkeletonSeed {
  colors: string;
  poolId: string;
  cards: SkeletonRow[];
  splitCards: SkeletonRow[];
}

export interface Skeleton {
  colors: string;
  poolId: string;
  cards: ArtifactCard[];
  // Below sealeddeck's divider: the signpost uncommons and the commons that matter to the strategy
  splitCards: ArtifactCard[];
}

const SKELETON_SEEDS: Record<string, SkeletonSeed[]> = {
  HOB: [
    {
      colors: "WU",
      poolId: "meuRkRJix5",
      cards: [
        ["Plunder the Trollshaws", 2],
        ["Lakeshore Apothecary", 2],
        ["Enchanted River's Grasp", 3],
        ["Bilbo Baggins, Burglar", 3],
        ["Confusticate and Bebother", 3],
        ["Patient Instructor", 3],
        ["Uneasy Partings", 4],
        ["Long Lake Nuisance", 4],
        ["Esgaroth Garrison", 5],
        ["Magnificent End", 5],
      ],
      splitCards: [
        ["Moment of Glory", 1],
        ["Dwarven Provisioner", 2],
        ["Bard the Bowman", 3],
        ["Thorin's Last Stand", 4],
        ["Eagle's Rescue", 4],
      ],
    },
    {
      colors: "BR",
      poolId: "ywz5ZRxnz1",
      cards: [
        ["Stir Up Trouble", 1],
        ["Front Porch Sentries", 2],
        ["Stony-Voiced Goblins", 2],
        ["Goblin-town Flunkies", 2],
        ["Pinecone Strike", 2],
        ["Ragged Short Spear", 2],
        ["Goblin Plate Mail", 2],
        ["Bilbo's Deadly Slice", 3],
        ["Crude Bent Blade", 3],
        ["Rage into the Valley", 3],
        ["Gundabad Opportunist", 4],
      ],
      splitCards: [
        ["Tidings of War", 1],
        ["Reverent Howl", 3],
        ["Dori, Bearer of Friends", 3],
        ["Fearsome Goblin Pair", 3],
        ["Bolg of the North", 5],
        ["Smaug, the Great Calamity", 7],
      ],
    },
    {
      colors: "BG",
      poolId: "mWKhTYSL5x",
      cards: [
        ["Ravening Warg", 2],
        ["Quarrel", 2],
        ["Wargling", 2],
        ["Bilbo's Deadly Slice", 3],
        ["Crude Bent Blade", 3],
        ["Rage into the Valley", 3],
        ["Duskwatch Hunter", 3],
        ["Ordinary Bear", 4],
      ],
      splitCards: [
        ["Gollum, Silent Slinker", 4],
        ["The Chief Warg", 4],
        ["Beorn, Reluctant Host", 5],
        ["Large Bear", 5],
        ["Boughside Wanderers", 6],
      ],
    },
    {
      colors: "WR",
      poolId: "1rsV9yhVb9",
      cards: [
        ["Pinecone Strike", 2],
        ["Ragged Short Spear", 2],
        ["Goblin Plate Mail", 2],
        ["Dori, Bearer of Friends", 3],
        ["Dwarven Shortsword", 4],
        ["Iron Hills Stalwart", 5],
      ],
      splitCards: [
        ["Well-Worn Spatula", 1],
        ["Goblin-town Flunkies", 2],
        ["Dwarven Provisioner", 2],
        ["Vow to Erebor", 2],
        ["Óin the Brave", 2],
        ["Nori, Teller of Tales", 2],
        ["Thorin Oakenshield", 2],
        ["Ori, Keeper of Songs", 3],
        ["Gundabad Opportunist", 4],
        ["Bifur, Melodic Rider", 6],
        ["Smaug, the Great Calamity", 7],
      ],
    },
    {
      colors: "UG",
      poolId: "kkBNLoDQBD",
      cards: [
        ["Plunder the Trollshaws", 2],
        ["Quarrel", 2],
        ["Attercop", 2],
        ["Bilbo Baggins, Burglar", 3],
        ["Enchanted River's Grasp", 3],
        ["Confusticate and Bebother", 3],
        ["Wood Elves", 3],
        ["Mirkwood Nurturer", 3],
        ["Uneasy Partings", 4],
        ["Boughside Wanderers", 6],
      ],
      splitCards: [
        ["Elvenking's Harper", 2],
        ["Guardian of the Halls", 2],
        ["Thranduil, Sindarin Liege", 4],
        ["Silvan Reveler", 4],
      ],
    },
  ],
};

export function skeletonsFor(setCode: string): Skeleton[] {
  const seeds = SKELETON_SEEDS[setCode.toUpperCase()];
  if (!seeds) {
    return [];
  }
  const set = setCode.toLowerCase();
  const toCards = (rows: SkeletonRow[]): ArtifactCard[] =>
    rows.map(([name, cmc]) => ({ n: name, cn: null, s: set, r: null, c: null, cmc, type: null }));
  return seeds.map((seed) => ({
    colors: seed.colors,
    poolId: seed.poolId,
    cards: toCards(seed.cards),
    splitCards: toCards(seed.splitCards),
  }));
}

export interface SkeletonLayout {
  columns: ArtifactCard[][];
  splitColumns: ArtifactCard[][];
}

// A mana value only one half plays keeps its empty slot, so the halves line up column for column
export function skeletonLayout(skeleton: Skeleton): SkeletonLayout {
  const all = [...skeleton.cards, ...skeleton.splitCards];
  let top = 1;
  for (const card of all) {
    if ((card.cmc ?? 0) > top) {
      top = card.cmc ?? 0;
    }
  }
  const belongs = (card: ArtifactCard, manaValue: number) =>
    manaValue === 1 ? (card.cmc ?? 0) <= 1 : card.cmc === manaValue;
  const columnsOf = (cards: ArtifactCard[]) =>
    Array.from({ length: top }, (_, i) => cards.filter((card) => belongs(card, i + 1)));
  const columns = columnsOf(skeleton.cards);
  const splitColumns = columnsOf(skeleton.splitCards);
  const played = columns.map((column, i) => column.length > 0 || splitColumns[i].length > 0);
  return {
    columns: columns.filter((_, i) => played[i]),
    splitColumns: splitColumns.filter((_, i) => played[i]),
  };
}
