import type { PodCardStatRow } from "../podCards";

// Stand-in raw-sum rows per (season, card) until real drafts accumulate. Real names + sets so art
// resolves. The client sums the rows in scope and divides, so these are components, not computed rates.
const mk = (
  season: string,
  name: string,
  set: string,
  colors: string,
  rarity: string,
  cmc: number,
  type: string,
  seen: number,
  alsa: number,
  picked: number,
  ata: number,
  maindecked: number,
  games: number,
  gameWins: number,
): PodCardStatRow => ({
  set_code: "PEASANT",
  season,
  card_name: name,
  card_set: set,
  colors,
  rarity,
  cmc,
  type_line: type,
  seen_count: seen,
  last_seen_sum: Math.round(alsa * picked),
  saw_count: picked,
  pick_count: picked,
  pick_sum: Math.round(ata * picked),
  maindeck_count: maindecked,
  drafts: picked,
  game_count: games,
  game_wins: gameWins,
});

export const peasantPodCardsFixture: PodCardStatRow[] = [
  mk("SOS", "Lightning Bolt", "2xm", "R", "common", 1, "Instant", 142, 2.1, 41, 1.6, 40, 118, 72),
  mk("SOS", "Counterspell", "mh2", "U", "common", 2, "Instant", 130, 3.4, 38, 2.7, 35, 101, 56),
  mk("SOS", "Llanowar Elves", "dom", "G", "common", 1, "Creature — Elf Druid", 118, 4.8, 33, 3.9, 30, 88, 46),
  mk("SOS", "Man-o'-War", "tpr", "U", "common", 3, "Creature — Jellyfish", 109, 3.1, 36, 2.4, 34, 95, 54),
  mk("MSH", "Fire // Ice", "apc", "UR", "uncommon", 2, "Instant // Instant", 96, 3.8, 29, 3.0, 26, 74, 40),
  mk("MSH", "Kor Skyfisher", "znr", "W", "common", 2, "Creature — Kor Soldier", 88, 5.5, 24, 4.6, 21, 60, 29),
  mk("MSH", "Gray Merchant of Asphodel", "ths", "B", "common", 5, "Creature — Zombie", 77, 4.2, 22, 3.3, 20, 55, 35),
  mk("HOB", "Prophetic Prism", "c16", "", "common", 2, "Artifact", 71, 7.9, 15, 7.1, 11, 30, 14),
  mk("HOB", "Evolving Wilds", "m21", "", "common", 0, "Land", 64, 8.4, 12, 7.8, 12, 33, 17),
  mk("HOB", "Mulldrifter", "mm2", "U", "common", 5, "Creature — Elemental", 58, 2.9, 20, 2.2, 19, 52, 31),
];
