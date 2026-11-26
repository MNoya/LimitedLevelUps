import { describe, expect, it } from "vitest";

import { EMPTY_BASICS, fillLands, filterEntries, NO_FILTERS, type PoolCard } from "./dailySealed";

describe("fillLands", () => {
  it("fills basics up to 17 lands counting nonbasic lands, split by colored pips", () => {
    const deck = [spell("{W}{W}"), spell("{1}{U}"), land("Ruins"), land("Spaceport")];

    const basics = fillLands(deck, EMPTY_BASICS);

    expect(basics).toEqual({ W: 10, U: 5, B: 0, R: 0, G: 0 });
  });

  it("replaces the current basics instead of adding to them", () => {
    const deck = [spell("{B}"), spell("{R}")];

    const basics = fillLands(deck, { W: 3, U: 0, B: 9, R: 0, G: 0 });

    expect(basics).toEqual({ W: 0, U: 0, B: 9, R: 8, G: 0 });
  });
});

describe("filterEntries by color", () => {
  it("hides colorless cards when a color is selected", () => {
    const entries = [
      { index: 0, card: { ...spell("{W}"), identity: "W" } },
      { index: 1, card: { ...spell("{3}"), identity: "" } },
    ];

    const shown = filterEntries(entries, { ...NO_FILTERS, colors: ["W"] });

    expect(shown.map((entry) => entry.index)).toEqual([0]);
  });

  it("shows colorless cards when Colorless is selected, alongside the chosen colors", () => {
    const entries = [
      { index: 0, card: { ...spell("{W}"), identity: "W" } },
      { index: 1, card: { ...spell("{3}"), identity: "" } },
      { index: 2, card: { ...spell("{U}"), identity: "U" } },
    ];

    const shown = filterEntries(entries, { ...NO_FILTERS, colors: ["W"], colorless: true });

    expect(shown.map((entry) => entry.index)).toEqual([0, 1]);
  });
});

const spell = (cost: string): PoolCard => ({
  name: cost,
  cmc: 1,
  identity: "",
  cost,
  image: "",
  back: null,
  rarity: "common",
  types: ["Instant"],
});

const land = (name: string): PoolCard => ({ ...spell(""), name, cmc: 0, types: ["Land"] });
