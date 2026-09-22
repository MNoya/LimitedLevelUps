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
  FRA: [
    {
      colors: "WU",
      poolId: "bWzk9SpyZv",
      cards: [
        ["Unsummon", 1],
        ["Academic Ascent", 2],
        ["Surgical Precision", 2],
        ["Tam's Resistance", 2],
        ["Fatehold Chronologist // Peer Review", 2],
        ["Campus Crier", 2],
        ["Surveillance Phantasm", 2],
        ["Infinite Coursework", 3],
        ["Memory Trap", 3],
        ["Keeper of the Quiet Hour", 3],
        ["Mindseeker Oculus", 3],
        ["Semester Foreseer // Peer Review", 4],
        ["Hexhaven Battalion", 6],
      ],
      splitCards: [
        ["Icy Reception", 2],
        ["Fatehold Charm", 2],
        ["Shatterwing Pegasus", 3],
        ["Prudent Fateseer // Peer Review", 3],
        ["Protege's Awakening", 4],
        ["Blossom-Blessed Angel // Seed Suture", 4],
        ["Desperate Futurescribe", 4],
      ],
    },
    {
      colors: "UB",
      poolId: "pdFsnuxH13",
      cards: [
        ["Unsummon", 1],
        ["Icy Reception", 2],
        ["Last Gasp", 2],
        ["Solve for Disappointment", 2],
        ["Twinned Vision", 2],
        ["Rank Rat", 2],
        ["Void Extrapolator // Omit Variables", 2],
        ["Infinite Coursework", 3],
        ["Mindseeker Oculus", 3],
        ["Theorix Metamage // Omit Variables", 3],
        ["Extended Absence", 4],
      ],
      splitCards: [
        ["Surveillance Phantasm", 2],
        ["Paradox Shaper // Omit Variables", 2],
        ["Theorix Charm", 2],
        ["Protege's Awakening", 4],
        ["Recursive Recruitment", 4],
        ["Undulating Witness", 5],
        ["Apex Witchstalker", 6],
      ],
    },
    {
      colors: "BR",
      poolId: "Y1gbZnMWsC",
      cards: [
        ["Blazing Crescendo", 2],
        ["No Admittance", 2],
        ["Last Gasp", 2],
        ["Skilled Battlecarver", 2],
        ["Wrath of the Bloodmane", 3],
        ["Hallway Heckler // Vicious Verse", 3],
        ["Screeching Soulbreaker", 3],
        ["Extended Absence", 4],
        ["Heartstring Puller", 4],
        ["Awaken the Inferno", 5],
      ],
      splitCards: [
        ["Stingerquill Voxmancer // Vicious Verse", 1],
        ["Afterthought Sentry", 2],
        ["Ferocity of the Hunt", 2],
        ["Eardrum Rattler", 2],
        ["Stingerquill Charm", 2],
        ["Grim Repriser", 2],
        ["Cast Away Doubt", 3],
        ["Rampart Hunter", 4],
        ["Whiplash Wordsmith // Vicious Verse", 4],
        ["Tether Technician", 5],
      ],
    },
    {
      colors: "RG",
      poolId: "ihmbHaSE4h",
      cards: [
        ["No Admittance", 2],
        ["Compel Brutality", 2],
        ["Twinned Vision", 2],
        ["Something Worth Saving", 2],
        ["Arcane Amphisbaena", 2],
        ["Konstrari Improviser // Soul Tether", 2],
        ["Wrath of the Bloodmane", 3],
        ["Greenhouse Propagator", 3],
        ["Heartstring Puller", 4],
        ["Bestial Incursion", 4],
        ["Awaken the Inferno", 5],
        ["Vinelasher Adept", 6],
      ],
      splitCards: [
        ["Sureshot Sower", 2],
        ["Konstrari Charm", 2],
        ["Murmuring Volume", 3],
        ["Woodwork Prodigy // Soul Tether", 3],
        ["Wrecking Gecko", 5],
        ["Craftwork Crusher", 7],
      ],
    },
    {
      colors: "WG",
      poolId: "oMjNAiSAzx",
      cards: [
        ["Emergency Phytomedic // Seed Suture", 1],
        ["Compel Brutality", 2],
        ["Surgical Precision", 2],
        ["Medic's Kitesail", 2],
        ["Campus Crier", 2],
        ["Arcane Amphisbaena", 2],
        ["Unflinching Hortimancer", 2],
        ["Memory Trap", 3],
        ["Graft Surgeon", 3],
        ["Greenhouse Propagator", 3],
        ["Blossom-Blessed Angel // Seed Suture", 4],
        ["Bestial Incursion", 4],
        ["Hexhaven Battalion", 6],
      ],
      splitCards: [
        ["Tethermage's Advantage", 1],
        ["Blessed Ghoul", 1],
        ["Academic Ascent", 2],
        ["Konstrari Improviser // Soul Tether", 2],
        ["Something Worth Saving", 2],
        ["Vigorbloom Charm", 2],
        ["Vigorbloom Vanguard // Seed Suture", 2],
        ["Bloombrute", 4],
        ["Fateshaper Aspirant", 5],
      ],
    },
    {
      colors: "WB",
      poolId: "mtCmKd6ZdJ",
      cards: [
        ["Blessed Ghoul", 1],
        ["Surgical Precision", 2],
        ["Last Gasp", 2],
        ["Solve for Disappointment", 2],
        ["Silence the Echo", 2],
        ["Campus Crier", 2],
        ["Rank Rat", 2],
        ["Memory Trap", 3],
        ["Extended Absence", 4],
        ["Hexhaven Battalion", 6],
        ["Apex Witchstalker", 6],
      ],
      splitCards: [
        ["Edgar, Ancient Bloodlord", 2],
        ["Theoretical Necromancer", 3],
        ["Twisted Fates", 5],
      ],
    },
    {
      colors: "BG",
      poolId: "m2XkdDgGDM",
      cards: [
        ["Solve for Disappointment", 2],
        ["Last Gasp", 2],
        ["Compel Brutality", 2],
        ["Something Worth Saving", 2],
        ["Rank Rat", 2],
        ["Arcane Amphisbaena", 2],
        ["Extended Absence", 4],
        ["Bestial Incursion", 4],
        ["Apex Witchstalker", 6],
        ["Vinelasher Adept", 6],
      ],
      splitCards: [
        ["Void Extrapolator // Omit Variables", 2],
        ["Ferocity of the Hunt", 2],
        ["Theorix Metamage // Omit Variables", 3],
        ["Primal Witchstalker", 3],
        ["Hapatra, the Desert Fang", 5],
      ],
    },
    {
      colors: "UG",
      poolId: "YJBGVr8Q8Z",
      cards: [
        ["Unsummon", 1],
        ["Compel Brutality", 2],
        ["Tam's Resistance", 2],
        ["Surveillance Phantasm", 2],
        ["Arcane Amphisbaena", 2],
        ["Infinite Coursework", 3],
        ["Keeper of the Quiet Hour", 3],
        ["Mindseeker Oculus", 3],
        ["Protege's Awakening", 4],
        ["Bestial Incursion", 4],
      ],
      splitCards: [
        ["Icy Reception", 2],
        ["Something Worth Saving", 2],
        ["Sureshot Sower", 2],
        ["Murmuring Volume", 3],
        ["Inspired Tethermage", 3],
        ["Kiora of Salt and Sand", 3],
        ["Mind Meanderer", 6],
      ],
    },
    {
      colors: "UR",
      poolId: "dfUoj2Erd8",
      cards: [
        ["Unsummon", 1],
        ["No Admittance", 2],
        ["Twinned Vision", 2],
        ["Mindseeker Oculus", 3],
        ["Wrath of the Bloodmane", 3],
        ["Heartstring Puller", 4],
        ["Awaken the Inferno", 5],
      ],
      splitCards: [
        ["Artifist Acumen", 1],
        ["Surveillance Phantasm", 2],
        ["Icy Reception", 2],
        ["Blazing Crescendo", 2],
        ["Konstrari Improviser // Soul Tether", 2],
        ["Tam's Resistance", 2],
        ["Cryotheory Adept", 2],
        ["Skilled Battlecarver", 2],
        ["Infinite Coursework", 3],
        ["Chandra's Emberling", 3],
        ["Clash of Elements", 3],
        ["Protege's Awakening", 4],
        ["Whiplash Wordsmith // Vicious Verse", 4],
        ["Saheeli, Jewel of Avishkar", 4],
      ],
    },
    {
      colors: "WR",
      poolId: "46LomaRBpQ",
      cards: [
        ["Surgical Precision", 2],
        ["No Admittance", 2],
        ["Skilled Battlecarver", 2],
        ["Campus Crier", 2],
        ["Memory Trap", 3],
        ["Wrath of the Bloodmane", 3],
        ["Graft Surgeon", 3],
        ["Heartstring Puller", 4],
        ["Awaken the Inferno", 5],
        ["Hexhaven Battalion", 6],
      ],
      splitCards: [
        ["Emergency Phytomedic // Seed Suture", 1],
        ["Blazing Crescendo", 2],
        ["Konstrari Improviser // Soul Tether", 2],
        ["Medic's Kitesail", 2],
        ["Unflinching Hortimancer", 2],
        ["Shatterwing Pegasus", 3],
        ["Charge the Sanctum", 3],
        ["Mabel, Valley Hero", 3],
        ["Blossom-Blessed Angel // Seed Suture", 4],
        ["Warrior's Blades", 4],
      ],
    },
  ],
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
