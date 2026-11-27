import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { ChevronLeft, ChevronRight, LayoutGrid, Rows2 } from "lucide-react";

import { Pip, Pips } from "../ManaPips";
import { usePersistentBool } from "../../lib/use-persistent-bool";
import { TabButton } from "../TabButton";
import { Tooltip } from "../Tooltip";
import { cn } from "../../lib/utils";
import { SCROLL_LIST_CLASS, SCROLL_LIST_STYLE } from "../../lib/scroll-list";
import {
  basicCount,
  groupByColor,
  isCreature,
  isLand,
  mainColors,
  type Basics,
  type DailySealedPool,
  type PoolCard,
  type PoolEntry,
} from "../../data/dailySealed";
import { cardsFitPileKey, sortZone, type Pile, type Row, type SortKey } from "../../data/dailySealedLayout";
import {
  bandOf,
  cardRates,
  colorSplashRows,
  comparisonWithPeers,
  EVENT_NAMES,
  isSplit,
  mostContested,
  topGihBuild,
  pairRows,
  rateShare,
  RATE_BANDS,
  rateText,
  splashCounts,
  type CardRate,
  type RateBasis,
} from "../../data/dailySealedBreakdown";
import type { BuilderView } from "../../pages/DailySealedPage";
import { chipClass, SwitchToggle } from "../pod/review/reviewControls";
import { ColorPie } from "./ColorPie";
import { CardGrid, ColumnRow, PHONE_PILE_WIDTH, StripList, type CardActions } from "./cards";
import { DECK_LAYOUT_KEY, usePreference, type DeckLayout } from "./usePreference";
import { MARK_OUTLINE } from "./markStyle";
import { FilterToggle } from "./controls";
import { Pane, Panel, SIDEBAR_WIDTH_CLASS, SORT_LABELS } from "./panels";
import { PILE_GAP, PileBoard } from "./piles";
import { useWidth } from "./elementSize";
import { PileSymbol } from "./PileSymbol";

type CardSort = SortKey | "rate";
type ExtraTab = "close" | "splashes" | "you";
type CardsTab = "oncolor" | "overall";
type Tab = CardsTab | ExtraTab | "decks";

interface DeckChoice {
  key: string;
  colors: string | null;
  main: number[];
  basics: Basics | null;
}

const CARD_WIDTH = 195;
const NO_RATE: CardRate = { played: 0, decks: 0 };
const PAIRS_SHOWN = 5;
const NONCREATURE_PREFIX = "noncreature-";
const TAB_ANCHORS: Record<Tab, string> = {
  oncolor: "on-color",
  overall: "played",
  close: "split",
  splashes: "splashes",
  you: "you",
  decks: "decks",
};
const OVERVIEW_ANCHOR = "overview";
const TAB_TITLES: Record<Tab, string> = {
  decks: "DECKS",
  oncolor: "ON-COLOR",
  overall: "PLAYED",
  close: "SPLIT",
  splashes: "SPLASHES",
  you: "YOU",
};

export const DesktopBreakdown = ({ view }: { view: BuilderView }) => {
  const state = useBreakdown(view);
  const [chosenSort, setSort] = useState<CardSort>("rate");
  const { tab, tabs, setTab } = useBreakdownTab(state);
  const cardsTab = tab === "oncolor" || tab === "overall";
  const sort = tab === "overall" && chosenSort === "rate" ? "color" : chosenSort;
  const cardRows = useMemo(() => state.rowsFor(state.uniqueIndexes, sort), [state, sort]);
  const boardRef = useRef<HTMLDivElement>(null);
  const boardWidth = useWidth(boardRef);
  const deck = state.deck;
  const deckRows = deck
    ? alignedZone(
        view.pool.cards,
        deck.main,
        "mana",
        state.split,
        deck.basics && basicCount(deck.basics) > 0 ? "land" : null,
      )
    : [];
  if (view.results.builds.length === 0) {
    return <Empty loading={view.results.loading} />;
  }
  const board = (rows: Row[], actions: CardActions, rateSort = false) => {
    const dividerBefore = rateSort ? rows[0]?.find((pile) => pile.key.startsWith(NONCREATURE_PREFIX))?.key : undefined;
    return (
      <PileBoard
        zone="side"
        setCode={view.pool.setCode}
        rows={rows}
        cards={view.pool.cards}
        width={dividerBefore ? fittedDividerWidth(boardWidth, rows[0].length) : CARD_WIDTH}
        visible={null}
        actions={state.inOrder(actions, rows.flatMap((row) => row.flatMap((pile) => pile.cards)))}
        dragging={null}
        readOnly
        pileHeader={(pile) => state.pileHeader(pile, rateSort)}
        dividerBefore={dividerBefore}
      />
    );
  };
  return (
    <div className="grid min-h-0 flex-1 grid-cols-[max-content_minmax(0,1fr)]">
      <div className={cn("flex min-h-0 flex-col overflow-y-auto border-r border-border", SIDEBAR_WIDTH_CLASS)}>
        {state.original && (
          <Panel title="ORIGINAL BUILD">
            <OriginalResult
              pool={view.pool}
              onShow={() => {
                state.setDeckKey("original");
                setTab("decks");
              }}
            />
          </Panel>
        )}
        <Panel title="COLORS">
          <PairList state={state} />
          <div className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] items-center gap-3">
            <ColorPie builds={view.results.builds} size={140} />
            <div className="flex flex-col gap-2">
              <span className="text-center font-display text-[12px] tracking-[0.16em] text-subtle">SPLASHES</span>
              <SplashBars state={state} />
            </div>
          </div>
        </Panel>
        <Panel title="INSIGHTS" grow>
          <Insights
            state={state}
            spread
            onShowBuild={(position) => {
              state.showBuild(position);
              setTab("decks");
            }}
          />
        </Panel>
      </div>
      <div className="flex min-h-0 flex-col">
        <Pane
          zone="side"
          className="flex-1 border-b-0"
          title={
            <span className="flex items-center gap-4">
              <PaneTabs
                tabs={tabs}
                active={tab}
                onPick={setTab}
                className="-ml-3 max-2xl:[&>button]:px-1.5 max-2xl:[&>button]:text-[13px] max-2xl:[&>button]:tracking-[0.1em]"
              />
              {!cardsTab && tab !== "decks" && <TabNote tab={tab} state={state} />}
            </span>
          }
          count={null}
          controls={
            cardsTab ? (
              <span className="flex items-center gap-3">
                <SortChips sort={sort} withRate={tab === "oncolor"} onSort={setSort} />
                {state.yourNames && state.markYours && <MarkLegend />}
              </span>
            ) : (
              tab === "decks" && <DeckPicker state={state} />
            )
          }
          extra={
            <span className="flex items-center gap-2">
              {tab !== "you" && (
                <SwitchToggle
                  label="SEPARATE NONCREATURES"
                  on={state.split}
                  onToggle={state.toggleSplit}
                  ariaLabel="Separate noncreatures"
                  tooltip="Show noncreatures in a second row"
                />
              )}
              {state.yourNames && (
                <SwitchToggle
                  label="OUTLINE BUILD"
                  on={state.markYours}
                  onToggle={() => state.setMarkYours(!state.markYours)}
                  ariaLabel="Outline build"
                  tooltip="Outline the cards you played"
                />
              )}
            </span>
          }
        >
          <div ref={boardRef}>
            {cardsTab &&
              board(cardRows, sort === "rate" ? state.plainActions : state.runActions(cardRows), sort === "rate")}
          </div>
          {tab === "decks" && deck && (
            <PileBoard
              zone="side"
              setCode={view.pool.setCode}
              rows={deckRows}
              cards={view.pool.cards}
              width={CARD_WIDTH}
              visible={null}
              actions={state.deckActions}
              dragging={null}
              basics={
                deck.basics
                  ? { row: deckRows.length - 1, pileKey: "land", entries: view.basicCardsOf(deck.basics), at: 0 }
                  : null
              }
              readOnly
            />
          )}
          {!cardsTab && tab !== "decks" && <ExtraBoard tab={tab} state={state} board={board} />}
        </Pane>
      </div>
    </div>
  );
};

const MarkLegend = () => (
  <span className={cn("flex h-7 items-center whitespace-nowrap rounded px-2 text-[13px] text-text", MARK_OUTLINE)}>
    Your Build
  </span>
);

export const PhoneBreakdown = ({ view, stickyTop }: { view: BuilderView; stickyTop: number }) => {
  const [overview, setOverview] = useState(() => breakdownTabFromHash() === null);
  const state = useBreakdown(view);
  const { tab, tabs, setTab } = useBreakdownTab(state);
  const tabsRef = useRef<HTMLDivElement>(null);
  const loaded = view.results.builds.length > 0;
  useEffect(() => {
    setAnchor(overview ? OVERVIEW_ANCHOR : TAB_ANCHORS[tab]);
  }, [overview, tab]);
  const groups = useMemo(() => state.phoneGroups(), [state]);
  const [deckLayout, setDeckLayout] = usePreference<DeckLayout>(DECK_LAYOUT_KEY, "piles");
  const overviewRef = useRef<HTMLDivElement>(null);
  const overviewHeight = useRestOfScreen(overviewRef, overview && loaded);
  if (!loaded) {
    return <Empty loading={view.results.loading} />;
  }
  const pick = (key: string) => {
    const bar = tabsRef.current;
    if (bar && bar.getBoundingClientRect().top <= stickyTop) {
      window.scrollTo({ top: bar.offsetTop - stickyTop });
    }
    if (key === OVERVIEW_ANCHOR) {
      setOverview(true);
      return;
    }
    setOverview(false);
    setTab(key as Tab);
  };
  const phoneTabs: Tab[] = ["decks", ...tabs.filter((key) => key !== "decks")];
  const tabItems = [
    { key: OVERVIEW_ANCHOR, label: "OVERVIEW" },
    ...phoneTabs.map((key) => ({ key, label: TAB_TITLES[key] })),
  ];
  const cardActions = state.runActions([
    groups.map((group) => ({ key: group.key, label: null, cards: group.entries.map((entry) => entry.index) })),
  ]);
  const deck = state.deck;
  return (
    <div className="flex flex-col gap-3">
      <div
        ref={tabsRef}
        className="sticky z-30 -mx-2 overflow-x-auto border-b border-border bg-bg px-2 [scrollbar-width:none]"
        style={{ top: stickyTop }}
      >
        <PhoneTabRow items={tabItems} active={overview ? OVERVIEW_ANCHOR : tab} onPick={pick} />
      </div>
      <PairChips state={state} yoursShortcut={!overview && tab === "decks"} />
      {overview && (
        <div ref={overviewRef} className="flex flex-col gap-4 pt-1" style={{ minHeight: overviewHeight }}>
          <section
            className={cn(
              "grid items-start gap-4 border-b border-border pb-4",
              state.pair === null ? "grid-cols-[minmax(0,1fr)_132px]" : "grid-cols-1",
            )}
          >
            {state.pair === null && (
              <div className="flex flex-col items-center gap-2">
                <PhoneHeading title="COLORS" />
                <ColorPie builds={view.results.builds} size={200} />
              </div>
            )}
            <div className="flex flex-col gap-2 self-center pr-3">
              <PhoneHeading title="SPLASHES" />
              <SplashBars state={state} />
            </div>
          </section>
          {!state.single && (
            <PhoneSection title="INSIGHTS" grow>
              <Insights
                state={state}
                spread
                centerCards
                communityPick={false}
                onShowBuild={(position) => {
                  state.showBuild(position);
                  pick("decks");
                }}
              />
            </PhoneSection>
          )}
        </div>
      )}
      {!overview && (tab === "oncolor" || tab === "overall" || tab === "close") && state.yourNames && state.markYours && (
        <div className="pointer-events-none fixed inset-x-0 bottom-4 z-40 flex justify-center">
          <span className="rounded bg-bg/90 shadow-lg backdrop-blur-sm">
            <MarkLegend />
          </span>
        </div>
      )}
      {!overview && (tab === "oncolor" || tab === "overall") && (
        <>
          {groups.map((group) => (
            <div key={group.key} className="flex flex-col gap-1">
              <div className="flex h-6 items-center justify-center">{group.header}</div>
              <CardGrid entries={group.entries} actions={state.inOrder(cardActions, indexesOf(groups.flatMap((each) => each.entries)))} />
            </div>
          ))}
        </>
      )}
      {!overview && (tab === "close" || tab === "splashes" || tab === "you") && (
        <>
          <div className="flex justify-center text-center">
            <TabNote tab={tab} state={state} />
          </div>
          <PhoneExtra tab={tab} state={state} />
        </>
      )}
      {!overview && tab === "decks" && (
        <>
          <div className="relative flex h-8 justify-center">
            <PhoneDeckPicker state={state} />
            <div className="absolute right-0 top-0 flex gap-1">
              <FilterToggle small active={state.split} onClick={state.toggleSplit} label="Split creatures">
                <Rows2 size={15} />
              </FilterToggle>
              <FilterToggle
                small
                active={deckLayout === "piles"}
                onClick={() => setDeckLayout(deckLayout === "piles" ? "names" : "piles")}
                label="Show full cards"
              >
                <LayoutGrid size={15} />
              </FilterToggle>
            </div>
          </div>
          {deck && <PhoneDeck state={state} view={view} layout={deckLayout} />}
          {state.deckKey === "original" && <OriginalLine pool={view.pool} />}
        </>
      )}
    </div>
  );
};

const PhoneDeck = ({ state, view, layout }: { state: BreakdownState; view: BuilderView; layout: DeckLayout }) => {
  const deck = state.deck;
  if (!deck) {
    return null;
  }
  const basics = deck.basics ? view.basicCardsOf(deck.basics) : [];
  if (layout === "names") {
    const byValue = state.entriesByValue(deck.main);
    const entries = [...byValue.filter((entry) => !isLand(entry.card)), ...byValue.filter((entry) => isLand(entry.card))];
    return (
      <>
        <StripList entries={entries} actions={state.inOrder(state.deckActions, indexesOf(entries))} />
        {deck.basics && <BasicsLine basics={deck.basics} />}
      </>
    );
  }
  const rows = alignedZone(view.pool.cards, deck.main, "mana", state.split, basics.length > 0 ? "land" : null);
  return (
    <>
      {rows.map((row, rowIndex) => (
        <div key={rowIndex} className="-mx-2 overflow-x-auto px-2 pb-1">
          <div className="w-max">
            <ColumnRow
              groups={row.map((pile) => ({
                key: pile.key,
                label: pile.key,
                entries: [
                  ...(rowIndex === rows.length - 1 && pile.key === "land" ? basics : []),
                  ...pile.cards.map((index) => ({ index, card: view.pool.cards[index] })),
                ],
              }))}
              setCode={view.pool.setCode}
              width={PHONE_PILE_WIDTH}
              actions={state.inOrder(state.deckActions, rows.flatMap((each) => each.flatMap((pile) => pile.cards)))}
            />
          </div>
        </div>
      ))}
    </>
  );
};

const useRestOfScreen = (ref: RefObject<HTMLElement | null>, active: boolean) => {
  const [height, setHeight] = useState<number | undefined>(undefined);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!active || !element) {
      return;
    }
    const pageBottomPadding = 24;
    const measure = () =>
      setHeight(window.innerHeight - (element.getBoundingClientRect().top + window.scrollY) - pageBottomPadding);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [ref, active]);
  return height;
};

const PairChips = ({ state, yoursShortcut }: { state: BreakdownState; yoursShortcut: boolean }) => (
  <div className="-mx-2 flex gap-1.5 overflow-x-auto px-2 [scrollbar-width:none] [&>*]:shrink-0">
    <FilterToggle active={state.pair === null} onClick={() => state.setPair(null)} wide>
      <span className="font-display text-[12px] tracking-[0.14em]">ALL</span>
      <span className="font-num text-[13px] text-text">{state.builds.length}</span>
    </FilterToggle>
    {yoursShortcut && state.yours && (
      <FilterToggle active={state.deckKey === "yours"} onClick={() => state.setDeckKey("yours")} wide>
        <span className="font-display text-[12px] tracking-[0.14em]">YOURS</span>
      </FilterToggle>
    )}
    {state.pairs.map((row) => (
      <FilterToggle
        key={row.pair}
        active={state.pair === row.pair}
        onClick={() => state.setPair(state.pair === row.pair ? null : row.pair)}
        wide
      >
        <Pips colors={row.pair} size={14} />
        <span className="font-num text-[13px] text-text">{row.decks}</span>
      </FilterToggle>
    ))}
  </div>
);

const SplashBars = ({ state }: { state: BreakdownState }) => {
  const total = state.counted.length;
  const rows = colorSplashRows(state.counted).filter((row) => !state.pair?.includes(row.color));
  const splashed = rows.filter((row) => row.splash > 0);
  if (splashed.length === 0) {
    return <span className="text-center text-[13px] text-subtle">No splashes</span>;
  }
  return (
    <div className="flex flex-col gap-2">
      {splashed.map((row) => (
        <div key={row.color} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2">
          <Pip c={row.color} size={16} />
          <span className="h-2 overflow-hidden rounded-full bg-surface2">
            <span className="block h-full rounded-full bg-green" style={{ width: `${(100 * row.splash) / total}%` }} />
          </span>
          <span className="text-right font-num text-[13px] text-text">
            {row.splash}/{total}
          </span>
        </div>
      ))}
    </div>
  );
};

const PhoneDeckPicker = ({ state }: { state: BreakdownState }) => {
  if (!state.original) {
    return <DeckPicker state={state} />;
  }
  const total = state.counted.length;
  const position = state.deckKey === "original" ? 0 : state.buildIndex + 1;
  const step = (offset: number) => {
    const next = (position + offset + total + 1) % (total + 1);
    if (next === 0) {
      state.setDeckKey("original");
    } else {
      state.showBuild(next - 1);
    }
  };
  const colors = position === 0 ? state.original.colors : state.build?.colors;
  const widest = widestColors(state, [state.original.colors ?? ""]);
  return (
    <div className="flex items-center justify-center gap-1">
      <StepButton label="Previous build" onClick={() => step(-1)}>
        <ChevronLeft size={16} />
      </StepButton>
      <DeckChip active={state.deckKey !== "yours"} onClick={() => step(0)}>
        <span className="grid justify-items-center">
          <span className={cn("invisible col-start-1 row-start-1 flex items-center gap-1.5", stackPips(widest))}>
            <span className="font-num tabular-nums">#{state.builds.length}</span>
            <Pips colors={widest} size={13} />
          </span>
          <span className={cn("col-start-1 row-start-1 flex items-center gap-1.5", stackPips(colors ?? ""))}>
            <span className="font-num tabular-nums">#{position}</span>
            <Pips colors={colors ?? ""} size={13} />
          </span>
        </span>
      </DeckChip>
      <StepButton label="Next build" onClick={() => step(1)}>
        <ChevronRight size={16} />
      </StepButton>
    </div>
  );
};

const stackPips = (colors: string) => (colors.length >= 4 ? "[&_.inline-flex>*+*]:-ml-1" : "");

const OriginalLine = ({ pool }: { pool: DailySealedPool }) => (
  <div className="flex items-center justify-center gap-2.5">
    <span className="font-display text-[12px] tracking-[0.16em] text-subtle">ORIGINAL BUILD</span>
    <span className="font-num text-[15px] text-text">
      {pool.wins}-{pool.losses}
    </span>
    <span className="text-[13px] text-subtle">{EVENT_NAMES[pool.format] ?? pool.format}</span>
  </div>
);

const PhoneTabRow = ({
  items,
  active,
  onPick,
}: {
  items: { key: string; label: string }[];
  active: string;
  onPick: (key: string) => void;
}) => (
  <span className="flex h-8 w-max min-w-full [&>button]:h-full [&>button]:flex-auto [&>button]:px-2.5 [&>button]:py-0 [&>button]:text-[13px] [&>button]:tracking-[0.1em]">
    {items.map((item) => (
      <TabButton key={item.key} active={active === item.key} onClick={() => onPick(item.key)}>
        {item.label}
      </TabButton>
    ))}
  </span>
);

const fittedDividerWidth = (boardWidth: number, columns: number) => {
  const dividerWidth = 17;
  const fit = Math.floor((boardWidth - dividerWidth - PILE_GAP * columns) / columns);
  return boardWidth > 0 ? Math.max(150, Math.min(CARD_WIDTH, fit)) : CARD_WIDTH;
};

const useBreakdownTab = (state: BreakdownState) => {
  const [chosenTab, setChosenTab] = useState<Tab>(() => breakdownTabFromHash() ?? "oncolor");
  const available =
    chosenTab === "oncolor" || chosenTab === "overall" || chosenTab === "decks" || state.extraTabs.includes(chosenTab);
  const tab = state.single ? "decks" : available ? chosenTab : "oncolor";
  useEffect(() => {
    setAnchor(TAB_ANCHORS[tab]);
  }, [tab]);
  const setTab = (next: Tab) => {
    setChosenTab(next);
    if (next === "oncolor" || next === "overall") {
      state.setBasis(next);
    }
  };
  const tabs: Tab[] = state.single ? ["decks"] : ["oncolor", "overall", ...state.extraTabs, "decks"];
  return { tab, tabs, setTab };
};

export const setAnchor = (anchor: string | null) => {
  const { pathname, search } = window.location;
  window.history.replaceState(
    window.history.state,
    "",
    anchor ? `${pathname}${search}#${anchor}` : `${pathname}${search}`,
  );
};

export const breakdownTabFromHash = (): Tab | null => {
  const anchor = window.location.hash.slice(1);
  for (const [tab, name] of Object.entries(TAB_ANCHORS)) {
    if (name === anchor) {
      return tab as Tab;
    }
  }
  return null;
};

export const breakdownAnchored = () =>
  breakdownTabFromHash() !== null || window.location.hash === `#${OVERVIEW_ANCHOR}`;

type BreakdownState = ReturnType<typeof useBreakdown>;

const useBreakdown = (view: BuilderView) => {
  const { pool } = view;
  const builds = view.results.builds;
  const [pair, setPair] = useState<string | null>(null);
  const [basis, setBasis] = useState<RateBasis>(() => (breakdownTabFromHash() === "overall" ? "overall" : "oncolor"));
  const [markYours, setMarkYours] = useState(true);
  const [split, setSplit] = usePersistentBool("daily-sealed:breakdown-split", false);
  const [deckKey, setDeckKey] = useState<string>(
    pool.originalMain.length > 0 && builds.length !== 1 ? "original" : "build",
  );
  const [buildAt, setBuildAt] = useState(0);
  const pairs = useMemo(() => pairRows(builds), [builds]);
  const counted = useMemo(() => {
    const inPair = pair ? builds.filter((build) => mainColors(build.colors) === pair) : builds;
    const popularity = new Map(pairs.map((row, rank) => [row.pair, rank]));
    return [...inPair].sort(
      (a, b) => (popularity.get(mainColors(a.colors)) ?? 0) - (popularity.get(mainColors(b.colors)) ?? 0),
    );
  }, [builds, pair, pairs]);
  const onColorRates = useMemo(() => cardRates(pool, counted), [pool, counted]);
  const shownRates = useMemo(
    () => (basis === "oncolor" ? onColorRates : cardRates(pool, counted, "overall")),
    [basis, onColorRates, pool, counted],
  );
  const splashes = useMemo(() => splashCounts(pool, counted), [pool, counted]);
  const splashedBuilds = counted.filter((build) => build.colors !== build.colors.toUpperCase()).length;
  const uniqueIndexes = useMemo(() => firstIndexPerName(pool), [pool]);
  const yourBuild = view.yourBuild;
  const comparison = useMemo(
    () => (yourBuild ? comparisonWithPeers(pool, builds, { buildKey: "you", ...yourBuild }) : null),
    [pool, builds, yourBuild],
  );
  const yourNames = useMemo(
    () => (yourBuild ? new Set(yourBuild.main.map((index) => pool.cards[index]?.name)) : null),
    [yourBuild, pool.cards],
  );
  const rateOf = (card: PoolCard) => shownRates.get(card.name) ?? NO_RATE;
  const byRate = (a: number, b: number) => {
    const left = rateOf(pool.cards[a]);
    const right = rateOf(pool.cards[b]);
    return orderShare(right) - orderShare(left) || right.played - left.played || pool.cards[a].cmc - pool.cards[b].cmc;
  };
  const yourPair = yourBuild ? mainColors(yourBuild.colors) : null;
  const marked = markYours && yourNames ? (card: PoolCard) => yourNames.has(card.name) : undefined;
  const plainActions: CardActions = {
    onPick: view.openCard,
    onPreview: view.openCard,
    dimmed: (card) => rateOf(card).played === 0,
    marked,
  };
  const runActions = (rows: Row[]): CardActions => {
    const labeled = new Set<string>();
    for (const row of rows) {
      for (const pile of row) {
        let previous: string | null = null;
        for (const index of pile.cards) {
          const rate = rateOf(pool.cards[index]);
          const text = rate.decks === 0 ? null : rateText(rate);
          if (text !== null && text !== previous) {
            labeled.add(pool.cards[index].name);
          }
          previous = text;
        }
      }
    }
    return {
      ...plainActions,
      ratingFor: (card) => (labeled.has(card.name) ? rateShare(rateOf(card)) : null),
      ratingText: (card) => rateText(rateOf(card)),
    };
  };
  const rateActions = (source: Map<string, CardRate>): CardActions => ({
    onPick: view.openCard,
    onPreview: view.openCard,
    ratingFor: (card) => rateShare(source.get(card.name) ?? NO_RATE),
    ratingText: (card) => rateText(source.get(card.name) ?? NO_RATE),
  });
  const splashActions: CardActions = {
    onPick: view.openCard,
    onPreview: view.openCard,
    ratingFor: () => 1,
    ratingText: (card) => `${splashes.get(card.name) ?? 0}/${splashedBuilds}`,
  };
  const indexOfName = (name: string) => pool.cards.findIndex((card) => card.name === name);
  const contestedName = mostContested(onColorRates);
  let splashedName: string | null = null;
  for (const [name, count] of splashes) {
    if (splashedName === null || count > (splashes.get(splashedName) ?? 0)) {
      splashedName = name;
    }
  }
  const topBuild = topGihBuild(pool, counted, view.gihWrOf);
  const closeCalls = uniqueIndexes.filter((index) => isSplit(onColorRates.get(pool.cards[index].name) ?? NO_RATE));
  const splashIndexes = [...splashes.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => indexOfName(name));
  const bandRow = (indexes: number[]): Row => {
    const piles: Pile[] = RATE_BANDS.map((band) => ({ key: band.key, label: band.label, cards: [] }));
    for (const index of [...indexes].sort(byRate)) {
      piles.find((pile) => pile.key === bandOf(rateOf(pool.cards[index])))?.cards.push(index);
    }
    return piles.filter((pile) => pile.cards.length > 0);
  };
  const rowsFor = (indexes: number[], sort: CardSort, splitRows = split): Row[] =>
    yoursFirst(sortedRows(indexes, sort, splitRows));
  const yoursFirst = (rows: Row[]): Row[] => {
    if (!marked) {
      return rows;
    }
    return rows.map((row) =>
      row.map((pile) => ({
        ...pile,
        cards: [
          ...pile.cards.filter((index) => marked(pool.cards[index])),
          ...pile.cards.filter((index) => !marked(pool.cards[index])),
        ],
      })),
    );
  };
  const sortedRows = (indexes: number[], sort: CardSort, splitRows: boolean): Row[] => {
    if (sort === "rate") {
      if (!splitRows) {
        return [bandRow(indexes)];
      }
      const creatures = indexes.filter((index) => isCreature(pool.cards[index]));
      const others = indexes.filter((index) => !isCreature(pool.cards[index]));
      return [
        [
          ...bandRow(creatures),
          ...bandRow(others).map((pile) => ({ ...pile, key: `${NONCREATURE_PREFIX}${pile.key}` })),
        ],
      ];
    }
    return alignedZone(pool.cards, indexes, sort, splitRows).map((row) =>
      row.map((pile) => ({ ...pile, cards: [...pile.cards].sort(byRate) })),
    );
  };
  const pileHeader = (pile: Pile, rateSort: boolean): ReactNode =>
    pile.cards.length === 0 ? null : rateSort ? (
      <span className="font-display text-[12px] tracking-[0.16em] text-text">{pile.label}</span>
    ) : cardsFitPileKey(
        pile.key,
        pile.cards.map((index) => pool.cards[index]),
      ) ? (
      <PileSymbol pileKey={pile.key} setCode={pool.setCode} />
    ) : null;
  const phoneGroups = () => {
    if (basis === "oncolor") {
      return rowsFor(uniqueIndexes, "rate", false)[0].map((pile) => ({
        key: pile.key,
        header: pileHeader(pile, true),
        entries: pile.cards.map((index) => ({ index, card: pool.cards[index] })),
      }));
    }
    return groupByColor(uniqueIndexes.map((index) => ({ index, card: pool.cards[index] }))).map((group) => ({
      key: group.key,
      header: <PileSymbol pileKey={group.key} setCode={pool.setCode} />,
      entries: [...group.entries].sort(
        (a, b) => Number(!!marked?.(b.card)) - Number(!!marked?.(a.card)) || byRate(a.index, b.index),
      ),
    }));
  };
  const entriesByValue = (indexes: number[]) =>
    [...indexes].sort((a, b) => pool.cards[a].cmc - pool.cards[b].cmc).map((index) => ({ index, card: pool.cards[index] }));
  const original: DeckChoice | null =
    pool.originalMain.length > 0
      ? { key: "original", colors: pool.colors, main: pool.originalMain, basics: pool.originalBasics }
      : null;
  const yours: DeckChoice | null = yourBuild
    ? { key: "yours", colors: yourBuild.colors, main: yourBuild.main, basics: yourBuild.basics }
    : null;
  const buildIndex = Math.min(buildAt, Math.max(counted.length - 1, 0));
  const shownBuild = counted[buildIndex];
  const build: DeckChoice | null = shownBuild
    ? { key: "build", colors: shownBuild.colors, main: shownBuild.main, basics: shownBuild.basics }
    : null;
  const deck = (deckKey === "original" && original) || (deckKey === "yours" && yours) || build;
  return {
    pool,
    builds,
    counted,
    pair,
    setPair: (next: string | null) => {
      setPair(next);
      const inPair = next ? builds.filter((build) => mainColors(build.colors) === next) : builds;
      if (inPair.length === 1) {
        setDeckKey("build");
        setBuildAt(0);
      }
    },
    single: counted.length === 1,
    pairs,
    basis,
    setBasis,
    uniqueIndexes,
    yourNames,
    markYours,
    setMarkYours,
    split,
    toggleSplit: () => setSplit((value) => !value),
    plainActions,
    yourPair,
    runActions,
    rateActions,
    splashActions,
    onColorRates,
    deckActions: { onPick: view.openCard, onPreview: view.openCard } as CardActions,
    rowsFor,
    pileHeader,
    phoneGroups,
    entriesByValue,
    inOrder: (actions: CardActions, indexes: number[]): CardActions => {
      const open = (entry: PoolEntry) => view.openCard(entry, indexes);
      return { ...actions, onPick: open, onPreview: open };
    },
    closeCalls,
    closeActions: { ...rateActions(onColorRates), marked },
    closeEntries: entriesByValue(closeCalls).sort((a, b) => Number(!!marked?.(b.card)) - Number(!!marked?.(a.card))),
    yoursFirst,
    extraTabs: [
      ...(closeCalls.length > 0 ? (["close"] as const) : []),
      "splashes" as const,
      ...(comparison ? (["you"] as const) : []),
    ] as ExtraTab[],
    splashIndexes,
    splashedBuilds,
    comparison,
    youPicks: comparison ? comparison.yourPicks.map(indexOfName) : [],
    theirPicks: comparison ? comparison.theirPicks.map(indexOfName) : [],
    original,
    yours,
    build,
    buildIndex,
    deck,
    deckKey: deck?.key ?? null,
    setDeckKey,
    contested: contestedName === null ? null : indexOfName(contestedName),
    mostSplashed: splashedName === null ? null : indexOfName(splashedName),
    topBuild: topBuild ? { ...topBuild, position: counted.indexOf(topBuild.build) } : null,
    rateLabel: (index: number) => rateText(onColorRates.get(pool.cards[index].name) ?? NO_RATE),
    splashLabel: (index: number) => `${splashes.get(pool.cards[index].name) ?? 0}/${splashedBuilds}`,
    showBuild: (position: number) => {
      setDeckKey("build");
      setBuildAt(position);
    },
    stepBuild: (offset: number) => {
      setDeckKey("build");
      setBuildAt((buildIndex + offset + counted.length) % counted.length);
    },
  };
};

const alignedZone = (
  cards: PoolCard[],
  indexes: number[],
  sort: SortKey,
  split: boolean,
  leading: string | null = null,
): Row[] => {
  const order = (sortZone(cards, indexes, sort, false)[0] ?? []).map((pile) => pile.key);
  if (leading && !order.includes(leading)) {
    order.unshift(leading);
  }
  return alignRows(sortZone(cards, indexes, sort, split), order, leading);
};

const alignRows = (rows: Row[], order: string[], kept: string | null = null): Row[] => {
  const filled = rows.filter((row) => row.some((pile) => pile.cards.length > 0));
  if (filled.length < 2) {
    return filled;
  }
  const keys = order.filter(
    (key) => key === kept || filled.some((row) => row.some((pile) => pile.key === key && pile.cards.length > 0)),
  );
  return filled.map((row) =>
    keys.map((key) => row.find((pile) => pile.key === key) ?? { key, label: null, cards: [] }),
  );
};

const firstIndexPerName = (pool: DailySealedPool) => {
  const seen = new Set<string>();
  const indexes: number[] = [];
  for (const [index, card] of pool.cards.entries()) {
    if (!seen.has(card.name)) {
      seen.add(card.name);
      indexes.push(index);
    }
  }
  return indexes;
};

const orderShare = (rate: CardRate) => (rate.decks === 0 ? -1 : rate.played / rate.decks);

const ExtraBoard = ({
  tab,
  state,
  board,
}: {
  tab: ExtraTab;
  state: BreakdownState;
  board: (rows: Row[], actions: CardActions) => ReactNode;
}) => {
  if (tab === "close") {
    return board(state.yoursFirst(alignedZone(state.pool.cards, state.closeCalls, "color", state.split)), state.closeActions);
  }
  if (tab === "splashes") {
    return state.splashIndexes.length === 0 ? (
      <Nothing text="No splashes in these builds" />
    ) : (
      board(alignedZone(state.pool.cards, state.splashIndexes, "color", state.split), state.splashActions)
    );
  }
  const comparison = state.comparison;
  if (!comparison) {
    return null;
  }
  const actions = state.rateActions(comparison.rates);
  return (
    <div className="flex flex-col gap-3">
      <YouGroup title="ONLY YOU PLAYED" empty={state.youPicks.length === 0}>
        {board(alignedZone(state.pool.cards, state.youPicks, "color", false), actions)}
      </YouGroup>
      <YouGroup title="YOU CUT" empty={state.theirPicks.length === 0}>
        {board(alignedZone(state.pool.cards, state.theirPicks, "color", false), actions)}
      </YouGroup>
    </div>
  );
};

const YouGroup = ({ title, empty, children }: { title: string; empty: boolean; children: ReactNode }) => (
  <div className="flex flex-col gap-1">
    <h3 className="font-display text-[13px] tracking-[0.16em] text-subtle">{title}</h3>
    {empty ? <Nothing text="No differences" /> : children}
  </div>
);

const TabNote = ({ tab, state }: { tab: ExtraTab; state: BreakdownState }) => {
  let text: ReactNode = null;
  if (tab === "close") {
    text = "Played by some but not all of the decks in their colors";
  } else if (tab === "splashes") {
    text = `Off-color cards splashed across ${state.splashedBuilds} builds`;
  } else if (state.comparison) {
    text = (
      <span className="flex items-center gap-1.5">
        Compared with the {state.comparison.peers} other <Pips colors={state.comparison.pair} size={13} /> builds
      </span>
    );
  }
  return <span className="text-[13px] text-subtle">{text}</span>;
};

const PhoneExtra = ({ tab, state }: { tab: ExtraTab; state: BreakdownState }) => {
  if (tab === "close") {
    return (
      <CardGrid entries={state.closeEntries} actions={state.inOrder(state.closeActions, indexesOf(state.closeEntries))} />
    );
  }
  if (tab === "splashes") {
    const entries = state.entriesByValue(state.splashIndexes);
    return <CardGrid entries={entries} actions={state.inOrder(state.splashActions, indexesOf(entries))} />;
  }
  if (!state.comparison) {
    return null;
  }
  const youPlayed = state.entriesByValue(state.youPicks);
  const youCut = state.entriesByValue(state.theirPicks);
  const actions = state.inOrder(state.rateActions(state.comparison.rates), indexesOf([...youPlayed, ...youCut]));
  return (
    <div className="flex flex-col gap-2">
      <span className="text-center font-display text-[12px] tracking-[0.16em] text-subtle">ONLY YOU PLAYED</span>
      {youPlayed.length === 0 ? <Nothing text="No differences" /> : <CardGrid entries={youPlayed} actions={actions} />}
      <span className="text-center font-display text-[12px] tracking-[0.16em] text-subtle">YOU CUT</span>
      {youCut.length === 0 ? <Nothing text="No differences" /> : <CardGrid entries={youCut} actions={actions} />}
    </div>
  );
};

const indexesOf = (entries: PoolEntry[]) => entries.map((entry) => entry.index);

const OriginalResult = ({ pool, onShow }: { pool: DailySealedPool; onShow: () => void }) => (
  <div className="flex flex-col items-center gap-1.5">
    <button
      type="button"
      onClick={onShow}
      className={cn("flex h-10 items-center gap-3 px-3 text-text", chipClass(false))}
    >
      {pool.colors && <Pips colors={pool.colors} size={18} />}
      <span className="font-num text-[22px] leading-none">
        {pool.wins}-{pool.losses}
      </span>
      <ChevronRight size={15} className="-mr-1 text-subtle" />
    </button>
    <span className="text-[13px] text-subtle">{EVENT_NAMES[pool.format] ?? pool.format}</span>
  </div>
);

const PairList = ({ state }: { state: BreakdownState }) => (
  <div className="flex flex-col gap-1">
    <PairButton
      active={state.pair === null}
      onClick={() => state.setPair(null)}
      decks={state.builds.length}
      total={state.builds.length}
    >
      <span className="font-display text-[12px] tracking-[0.16em]">ALL BUILDS</span>
    </PairButton>
    <div
      className={cn("-mr-2 flex flex-col gap-1", SCROLL_LIST_CLASS)}
      style={{ ...SCROLL_LIST_STYLE, maxHeight: `calc(${PAIRS_SHOWN} * 2rem + ${PAIRS_SHOWN - 1} * 0.25rem)` }}
    >
      {state.pairs.map((row) => (
        <PairButton
          key={row.pair}
          active={state.pair === row.pair}
          onClick={() => state.setPair(state.pair === row.pair ? null : row.pair)}
          decks={row.decks}
          total={state.builds.length}
        >
          <Pips colors={row.pair} size={15} />
          {row.decks === 1 && row.pair === state.yourPair && (
            <span className="ml-2 font-display text-[12px] tracking-[0.16em] text-subtle">(YOURS)</span>
          )}
        </PairButton>
      ))}
    </div>
  </div>
);

const PairButton = ({
  active,
  onClick,
  decks,
  total,
  children,
}: {
  active: boolean;
  onClick: () => void;
  decks: number;
  total: number;
  children: ReactNode;
}) => (
  <FilterToggle
    active={active}
    onClick={onClick}
    wide
    small
    className="w-full shrink-0 justify-between px-2.5 text-text"
  >
    <span className="flex items-center">{children}</span>
    <span className="flex items-baseline gap-3 font-num">
      <span className="text-[14px]">{decks}</span>
      <span className="w-[4ch] text-right text-[13px] text-subtle">{Math.round((100 * decks) / total)}%</span>
    </span>
  </FilterToggle>
);

const Insights = ({
  state,
  onShowBuild,
  spread = false,
  centerCards = false,
  communityPick = true,
}: {
  state: BreakdownState;
  onShowBuild: (position: number) => void;
  spread?: boolean;
  centerCards?: boolean;
  communityPick?: boolean;
}) => {
  const contested = state.contested;
  const splashed = state.mostSplashed;
  const top = state.topBuild;
  return (
    <div className={cn("flex flex-col gap-3", spread && "flex-1 justify-evenly")}>
      {contested !== null && !state.single && (
        <Insight label="MOST CONTESTED">
          <InsightCard state={state} index={contested} figure={state.rateLabel(contested)} centered={centerCards} />
        </Insight>
      )}
      {splashed !== null && !state.single && (
        <Insight label="MOST SPLASHED">
          <InsightCard state={state} index={splashed} figure={state.splashLabel(splashed)} centered={centerCards} />
        </Insight>
      )}
      {top && !state.single && (
        <Insight label="HIGHEST GIH WR BUILD">
          <BuildLink colors={top.build.colors} average={top.average} onClick={() => onShowBuild(top.position)} />
        </Insight>
      )}
      {communityPick && (
        <Insight label="COMMUNITY PICK">
          <div className="flex h-8 items-center justify-center rounded border border-dashed border-border2 text-[13px] text-subtle">
            Vote for best build: coming soon!
          </div>
        </Insight>
      )}
    </div>
  );
};

const BuildLink = ({ colors, average, onClick }: { colors: string; average: number; onClick: () => void }) => (
  <button
    type="button"
    onClick={onClick}
    className={cn("flex h-9 items-center gap-3 self-center px-3 text-text", chipClass(false))}
  >
    <Pips colors={colors} size={16} />
    <span className="font-num text-[15px]">{(average * 100).toFixed(1)}%</span>
    <ChevronRight size={15} className="-mr-1 text-subtle" />
  </button>
);

const InsightCard = ({
  state,
  index,
  figure,
  centered = false,
}: {
  state: BreakdownState;
  index: number;
  figure: string;
  centered?: boolean;
}) => (
  <div className="flex items-center gap-2">
    {centered && <span className="w-[5ch] shrink-0" />}
    <div className="min-w-0 flex-1">
      <StripList entries={state.entriesByValue([index])} actions={state.deckActions} />
    </div>
    <span className="w-[5ch] shrink-0 font-num text-[14px] text-text">{figure}</span>
  </div>
);

const Insight = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex flex-col gap-1">
    <span className="text-center font-display text-[12px] tracking-[0.16em] text-subtle">{label}</span>
    {children}
  </div>
);

const PaneTabs = ({
  tabs,
  active,
  onPick,
  className,
}: {
  tabs: Tab[];
  active: Tab;
  onPick: (tab: Tab) => void;
  className?: string;
}) => (
  <span
    className={cn(
      className,
      "flex h-10 [&>button]:h-full [&>button]:flex-none [&>button]:px-2 [&>button]:pb-1 [&>button]:pt-[7px]",
      "[&>button:hover]:bg-white/5 [&>button:hover]:text-text [&>button:active]:bg-white/10",
    )}
  >
    {tabs.map((tab) => (
      <TabButton key={tab} active={active === tab} onClick={() => onPick(tab)}>
        {TAB_TITLES[tab]}
      </TabButton>
    ))}
  </span>
);

const SortChips = ({
  sort,
  withRate,
  onSort,
}: {
  sort: CardSort;
  withRate: boolean;
  onSort: (sort: CardSort) => void;
}) => (
  <div className="flex items-center gap-2">
    <span className="font-display text-[13px] tracking-[0.18em] text-subtle max-2xl:hidden">SORT BY</span>
    <div className="flex gap-1">
      {withRate && (
        <Tooltip label="How many of the decks in its colors played each card" side="bottom">
          <button
            type="button"
            onClick={() => onSort("rate")}
            className={cn("h-8 px-2.5 text-[12px] uppercase tracking-[0.12em] max-2xl:px-2", chipClass(sort === "rate"))}
          >
            On-Color Rate
          </button>
        </Tooltip>
      )}
      {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
        <button
          key={key}
          type="button"
          onClick={() => onSort(key)}
          className={cn("h-8 px-2.5 text-[12px] uppercase tracking-[0.12em] max-2xl:px-2", chipClass(sort === key))}
        >
          {SORT_LABELS[key]}
        </button>
      ))}
    </div>
  </div>
);

const DeckPicker = ({ state }: { state: BreakdownState }) => (
  <div className="flex flex-wrap items-center gap-1 md:ml-4">
    {state.original && (
      <DeckChip active={state.deckKey === "original"} onClick={() => state.setDeckKey("original")}>
        ORIGINAL
        {state.original.colors && <Pips colors={state.original.colors} size={13} />}
      </DeckChip>
    )}
    {state.yours && (
      <DeckChip active={state.deckKey === "yours"} onClick={() => state.setDeckKey("yours")}>
        YOURS
        <Pips colors={state.yours.colors ?? ""} size={13} />
      </DeckChip>
    )}
    {state.build && (
      <span className="flex items-center gap-1">
        <StepButton label="Previous build" onClick={() => state.stepBuild(-1)}>
          <ChevronLeft size={16} />
        </StepButton>
        <DeckChip active={state.deckKey === "build"} onClick={() => state.setDeckKey("build")}>
          BUILD
          <span className="grid justify-items-center font-num tabular-nums">
            <span className="invisible col-start-1 row-start-1">
              {state.counted.length}/{state.counted.length}
            </span>
            <span className="col-start-1 row-start-1">
              {state.buildIndex + 1}/{state.counted.length}
            </span>
          </span>
          <span className="grid justify-items-center">
            <span className="invisible col-start-1 row-start-1">
              <Pips colors={widestColors(state)} size={13} />
            </span>
            <span className="col-start-1 row-start-1">
              <Pips colors={state.build.colors ?? ""} size={13} />
            </span>
          </span>
        </DeckChip>
        <StepButton label="Next build" onClick={() => state.stepBuild(1)}>
          <ChevronRight size={16} />
        </StepButton>
      </span>
    )}
  </div>
);

const widestColors = (state: BreakdownState, others: string[] = []) => {
  let widest = "";
  for (const colors of [...state.builds.map((build) => build.colors), ...others]) {
    if (colors.length > widest.length) {
      widest = colors;
    }
  }
  return widest;
};

const DeckChip = ({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) => (
  <button
    type="button"
    onClick={onClick}
    className={cn("flex h-8 items-center gap-2 px-2.5 text-[12px] tracking-[0.12em]", chipClass(active))}
  >
    {children}
  </button>
);

const StepButton = ({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={label}
    className={cn(
      "relative flex h-8 w-7 items-center justify-center before:absolute before:-inset-1.5 before:content-['']",
      chipClass(false),
    )}
  >
    {children}
  </button>
);

const BasicsLine = ({ basics }: { basics: Basics }) => (
  <div className="flex flex-wrap justify-center gap-x-4 font-num text-[14px] text-text">
    {(Object.keys(basics) as (keyof Basics)[])
      .filter((color) => basics[color] > 0)
      .map((color) => (
        <span key={color} className="flex items-center gap-1.5">
          <Pips colors={color} size={14} />
          {basics[color]}
        </span>
      ))}
  </div>
);

const PhoneHeading = ({ title }: { title: string }) => (
  <h2 className="flex min-h-9 items-center justify-center font-display text-[15px] tracking-[0.18em] text-text">{title}</h2>
);

const PhoneSection = ({ title, grow = false, children }: { title: string; grow?: boolean; children: ReactNode }) => (
  <section className={cn("flex flex-col gap-3 border-b border-border pb-4 last:border-b-0", grow && "flex-1")}>
    <div className="flex min-h-9 items-center justify-center">
      <h2 className="text-center font-display text-[15px] tracking-[0.18em] text-text">{title}</h2>
    </div>
    {children}
  </section>
);

const Nothing = ({ text }: { text: string }) => (
  <span className="py-2 text-center text-[13px] text-subtle">{text}</span>
);

const Empty = ({ loading }: { loading: boolean }) => (
  <div className="flex flex-1 items-center justify-center py-20 text-[14px] text-subtle">
    {loading ? "Loading the builds" : "No builds for this pool yet"}
  </div>
);
