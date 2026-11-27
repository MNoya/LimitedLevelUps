import { useEffect, useMemo, useRef, useState } from "react";

import {
  arenaExport,
  basicCount,
  COLORS,
  deckColors,
  EMPTY_BASICS,
  fillLands,
  type Basics,
  type Color,
  type PoolCard,
  type PoolEntry,
  type Zone,
} from "../../data/dailySealed";
import {
  hideCards,
  moveDeckPile,
  placeAt,
  placeInSlot,
  pruneEmptyPiles,
  sortZone,
  withLandsPile,
  zoneCards,
  type BasicsSlot,
  type Layout,
  type PileTarget,
  type PileZone,
  type SortKey,
} from "../../data/dailySealedLayout";
import type { OwnBuildInput } from "../../data/dailySealedApi";

interface BuildState {
  layout: Layout;
  basics: Basics;
  sort: Record<PileZone, SortKey>;
  split: boolean;
}

const HISTORY_LIMIT = 50;
const DEFAULT_SORT: Record<PileZone, SortKey> = { side: "color", deck: "mana" };

export type Builder = ReturnType<typeof useBuilder>;

export interface BuildSeed {
  main: number[];
  basics: Basics;
  hidden?: number[];
}

export const useBuilder = (cards: PoolCard[], storageKey: string | null, seed: BuildSeed | null | undefined) => {
  const allIndexes = useMemo(() => cards.map((_, index) => index), [cards]);
  const build = (main: number[], basics: Basics, hidden: number[] = [], sort = DEFAULT_SORT, split = false): BuildState => {
    const placed = new Set([...main, ...hidden]);
    return {
      layout: {
        side: sortZone(cards, allIndexes.filter((index) => !placed.has(index)), sort.side, false),
        deck: sortZone(cards, main, sort.deck, split),
        hidden,
      },
      basics,
      sort,
      split,
    };
  };
  const fresh = () => build([], { ...EMPTY_BASICS });
  const [saved] = useState(() => (storageKey ? readSaved(storageKey, cards.length) : null));
  const [state, setState] = useState<BuildState>(() => saved ?? (seed ? build(seed.main, seed.basics, seed.hidden) : fresh()));
  const [history, setHistory] = useState<BuildState[]>([]);
  const touched = useRef(saved !== null);
  const dragStart = useRef<BuildState | null>(null);
  const dragLayout = useRef<Layout | null>(null);

  useEffect(() => {
    if (touched.current || !seed) {
      return;
    }
    setState(build(seed.main, seed.basics, seed.hidden));
  }, [seed, cards]);

  useEffect(() => {
    if (storageKey) {
      writeSaved(storageKey, state);
    }
  }, [storageKey, state]);

  const apply = (next: BuildState) => {
    touched.current = true;
    setHistory((prev) => [...prev.slice(-HISTORY_LIMIT + 1), state]);
    setState(next);
  };
  const withLayout = (layout: Layout) => apply({ ...state, layout: pruneEmptyPiles(layout) });
  const previewDrag = (layoutFrom: (start: Layout) => Layout) => {
    const before = dragStart.current;
    if (!before) {
      return;
    }
    const layout = layoutFrom(before.layout);
    dragLayout.current = layout;
    setState((current) => ({ ...current, layout }));
  };

  const entryOf = (index: number): PoolEntry => ({ index, card: cards[index] });
  const deck = zoneCards(state.layout.deck).map(entryOf);
  const side = zoneCards(state.layout.side).map(entryOf);
  const hidden = state.layout.hidden.map(entryOf);
  const deckCards = deck.map((entry) => entry.card);
  const zones = useMemo(() => {
    const byIndex = new Map<number, Zone>();
    for (const index of zoneCards(state.layout.deck)) {
      byIndex.set(index, "deck");
    }
    for (const index of state.layout.hidden) {
      byIndex.set(index, "hidden");
    }
    return byIndex;
  }, [state.layout]);

  return {
    layout: state.layout,
    sort: state.sort,
    deck,
    side,
    hidden,
    basics: state.basics,
    deckSize: deck.length + basicCount(state.basics),
    split: state.split,
    canUndo: history.length > 0,
    zoneOf: (index: number): Zone => zones.get(index) ?? "side",
    move: (indexes: number[], zone: Zone) => {
      if (zone === "hidden") {
        withLayout(hideCards(state.layout, indexes));
        return;
      }
      withLayout(placeInSlot(state.layout, cards, indexes, zone, state.sort[zone], zone === "deck" && state.split));
    },
    sortBy: (zone: PileZone, key: SortKey) => {
      const indexes = zoneCards(state.layout[zone]);
      const split = zone === "deck" && state.split;
      const layout = { ...state.layout, [zone]: sortZone(cards, indexes, key, split) };
      apply({
        ...state,
        sort: { ...state.sort, [zone]: key },
        layout: zone === "deck" ? { ...layout, basicsSlot: undefined } : layout,
      });
    },
    toggleSplit: () => {
      const split = !state.split;
      const deckRows = sortZone(cards, zoneCards(state.layout.deck), state.sort.deck, split);
      apply({ ...state, split, layout: { ...state.layout, deck: deckRows, basicsSlot: undefined } });
    },
    beginDrag: (openLandsPile: boolean) => {
      const layout =
        openLandsPile && basicCount(state.basics) > 0 ? withLandsPile(state.layout, state.sort.deck) : state.layout;
      const start = layout === state.layout ? state : { ...state, layout };
      dragStart.current = start;
      dragLayout.current = layout;
      if (start !== state) {
        setState(start);
      }
    },
    dragTo: (indexes: number[], target: PileTarget | null) =>
      previewDrag((start) => (target ? placeAt(start, indexes, target) : start)),
    dragBasicsTo: (slot: BasicsSlot) => previewDrag((start) => ({ ...start, basicsSlot: slot })),
    dragLandsPileTo: (from: BasicsSlot, slot: BasicsSlot) => previewDrag((start) => moveDeckPile(start, from, slot)),
    endDrag: () => {
      const before = dragStart.current;
      const layout = dragLayout.current;
      dragStart.current = null;
      dragLayout.current = null;
      if (!before || !layout || layout === before.layout) {
        return;
      }
      touched.current = true;
      setHistory((prev) => [...prev.slice(-HISTORY_LIMIT + 1), before]);
      setState((current) => ({ ...current, layout: pruneEmptyPiles(layout) }));
    },
    cancelDrag: () => {
      if (dragStart.current) {
        setState(dragStart.current);
      }
      dragStart.current = null;
      dragLayout.current = null;
    },
    adjustBasic: (color: Color, by: number) =>
      apply({ ...state, basics: { ...state.basics, [color]: Math.max(0, state.basics[color] + by) } }),
    fillLands: () => apply({ ...state, basics: fillLands(deckCards, state.basics) }),
    clearHidden: () =>
      withLayout(placeInSlot(state.layout, cards, state.layout.hidden, "side", state.sort.side, false)),
    undo: () => {
      touched.current = true;
      const previous = history[history.length - 1];
      if (!previous) {
        return;
      }
      setHistory((prev) => prev.slice(0, -1));
      setState(previous);
    },
    reset: () => apply(seed ? build(seed.main, seed.basics, seed.hidden, state.sort, state.split) : fresh()),
    colors: () => deckColors(deckCards),
    arenaList: () =>
      arenaExport(
        deckCards,
        [...side, ...hidden].map((entry) => entry.card),
        state.basics,
      ),
    submission: (): OwnBuildInput => ({
      main: deck.map((entry) => entry.index),
      basics: state.basics,
      colors: deckColors(deckCards),
    }),
  };
};

const readSaved = (key: string, cardCount: number): BuildState | null => {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as BuildState;
    return isWholeBuild(parsed, cardCount) ? parsed : null;
  } catch {
    return null;
  }
};

const SORT_KEYS: SortKey[] = ["mana", "color", "rarity"];

const isWholeBuild = (build: BuildState, cardCount: number) => {
  const placed = [...zoneCards(build.layout.side), ...zoneCards(build.layout.deck), ...build.layout.hidden];
  const unique = new Set(placed);
  const everyCardOnce =
    placed.length === cardCount && unique.size === cardCount && placed.every((index) => index >= 0 && index < cardCount);
  const validSort = SORT_KEYS.includes(build.sort?.side) && SORT_KEYS.includes(build.sort?.deck);
  const validBasics = COLORS.every((color) => Number.isInteger(build.basics?.[color]) && build.basics[color] >= 0);
  return everyCardOnce && validSort && validBasics && typeof build.split === "boolean";
};

const writeSaved = (key: string, build: BuildState) => {
  try {
    localStorage.setItem(key, JSON.stringify(build));
  } catch {
    return;
  }
};
