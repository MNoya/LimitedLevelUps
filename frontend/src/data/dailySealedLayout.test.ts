import { describe, expect, it } from "vitest";

import type { PoolCard } from "./dailySealed";
import { cardsFitPileKey, moveDeckPile, sortZone, withLandsPile, type Layout } from "./dailySealedLayout";

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

describe("moveDeckPile", () => {
  it("moves the whole pile and points the basics at its new spot", () => {
    const layout: Layout = {
      side: [],
      deck: [[pile("land", [0]), pile("mv1", [1]), pile("mv2", [2])]],
      hidden: [],
    };

    const moved = moveDeckPile(layout, { row: 0, pile: 0 }, { row: 0, pile: 2 });

    expect(moved.deck[0].map((each) => each.key)).toEqual(["mv1", "mv2", "land"]);
    expect(moved.basicsSlot).toEqual({ row: 0, pile: 2 });
  });
});

describe("withLandsPile", () => {
  it("opens an empty lands pile where the basics column sits", () => {
    const layout: Layout = {
      side: [],
      deck: [[pile("mv1", [1]), pile("mv2", [2])]],
      hidden: [],
      basicsSlot: { row: 0, pile: 1 },
    };

    const opened = withLandsPile(layout, "mana");

    expect(opened.deck[0].map((each) => `${each.key}:${each.cards.length}`)).toEqual(["mv1:1", "land:0", "mv2:1"]);
  });
});

const pile = (key: string, cards: number[]) => ({ key, label: key, cards });

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
