import { describe, expect, it } from "vitest";

import type { PoolCard } from "./dailySealed";
import { cardsFitPileKey, sortZone } from "./dailySealedLayout";

describe("sortZone by mana value", () => {
  it("makes piles only for the cards it sorts, lands first", () => {
    const pool = [card("Bear", 2), card("Giant", 5), card("Ruins", 0, "Land"), card("Ornithopter", 0)];

    const [row] = sortZone(pool, [0, 1, 2], "mana", false);

    expect(row.map((pile) => pile.key)).toEqual(["land", "mv2", "mv5"]);
  });
});

describe("cardsFitPileKey", () => {
  it("keeps a pile's symbol only while every card in it belongs to that group", () => {
    const red = { ...card("Shock", 1), identity: "R" };
    const black = { ...card("Duress", 1), identity: "B" };

    const pure = cardsFitPileKey("R", [red]);
    const mixed = cardsFitPileKey("R", [red, black]);

    expect([pure, mixed]).toEqual([true, false]);
  });
});

const card = (name: string, cmc: number, type = "Creature"): PoolCard => ({
  name,
  cmc,
  identity: "G",
  cost: "",
  image: "",
  back: null,
  rarity: "common",
  types: [type],
});
