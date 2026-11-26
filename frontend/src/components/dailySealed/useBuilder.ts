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
  type DailySealedPool,
  type PoolEntry,
  type Zone,
} from "../../data/dailySealed";
import {
  hideCards,
  placeAt,
  placeInSlot,
  pruneEmptyPiles,
  sortZone,
  zoneCards,
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

export const useBuilder = (pool: DailySealedPool, ownBuild: OwnBuildInput | null | undefined) => {
  const storageKey = `daily-sealed:v2:${pool.day}`;
  const allIndexes = useMemo(() => pool.cards.map((_, index) => index), [pool.cards]);
  const build = (main: number[], basics: Basics, sort = DEFAULT_SORT, split = false): BuildState => {
    const inDeck = new Set(main);
    return {
      layout: {
        side: sortZone(pool.cards, allIndexes.filter((index) => !inDeck.has(index)), sort.side, false),
        deck: sortZone(pool.cards, main, sort.deck, split),
        hidden: [],
      },
      basics,
      sort,
      split,
    };
  };
  const fresh = () => build([], { ...EMPTY_BASICS });
  const [saved] = useState(() => readSaved(storageKey, pool.cards.length));
  const [state, setState] = useState<BuildState>(() => saved ?? fresh());
  const [history, setHistory] = useState<BuildState[]>([]);
  const touched = useRef(saved !== null);
  const dragStart = useRef<BuildState | null>(null);
  const dragLayout = useRef<Layout | null>(null);

  useEffect(() => {
    if (touched.current || !ownBuild) {
      return;
    }
    setState(build(ownBuild.main, ownBuild.basics));
  }, [ownBuild, pool.cards]);

  useEffect(() => {
    writeSaved(storageKey, state);
  }, [storageKey, state]);

  const apply = (next: BuildState) => {
    touched.current = true;
    setHistory((prev) => [...prev.slice(-HISTORY_LIMIT + 1), state]);
    setState(next);
  };
  const withLayout = (layout: Layout) => apply({ ...state, layout: pruneEmptyPiles(layout) });

  const entryOf = (index: number): PoolEntry => ({ index, card: pool.cards[index] });
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
    pool,
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
      withLayout(placeInSlot(state.layout, pool.cards, indexes, zone, state.sort[zone], zone === "deck" && state.split));
    },
    sortBy: (zone: PileZone, key: SortKey) => {
      const indexes = zoneCards(state.layout[zone]);
      const split = zone === "deck" && state.split;
      apply({
        ...state,
        sort: { ...state.sort, [zone]: key },
        layout: { ...state.layout, [zone]: sortZone(pool.cards, indexes, key, split) },
      });
    },
    toggleSplit: () => {
      const split = !state.split;
      const deckRows = sortZone(pool.cards, zoneCards(state.layout.deck), state.sort.deck, split);
      apply({ ...state, split, layout: { ...state.layout, deck: deckRows } });
    },
    beginDrag: () => {
      dragStart.current = state;
      dragLayout.current = state.layout;
    },
    dragTo: (indexes: number[], target: PileTarget | null) => {
      const before = dragStart.current;
      if (!before) {
        return;
      }
      const layout = target ? placeAt(before.layout, indexes, target) : before.layout;
      dragLayout.current = layout;
      setState((current) => ({ ...current, layout }));
    },
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
      withLayout(placeInSlot(state.layout, pool.cards, state.layout.hidden, "side", state.sort.side, false)),
    undo: () => {
      touched.current = true;
      const previous = history[history.length - 1];
      if (!previous) {
        return;
      }
      setHistory((prev) => prev.slice(0, -1));
      setState(previous);
    },
    reset: () => apply(fresh()),
    colors: () => deckColors(deckCards),
    exportText: () =>
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
