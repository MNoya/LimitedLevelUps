import { useState, type ReactNode } from "react";
import { Check, Copy, Download, EyeOff, LayoutGrid, Rows2, SlidersHorizontal, Undo2, X } from "lucide-react";

import { SetGlyph } from "../Brand";
import { useCopyFeedback } from "../CopyTextButton";
import { cn } from "../../lib/utils";
import { groupByColor, type PoolEntry } from "../../data/dailySealed";
import type { BuilderView } from "../../pages/DailySealedPage";
import { BASICS_PILE_KEY } from "../../data/dailySealedLayout";
import { CardFace, CardPreview, ColumnRow, RatingBadge, StripList, type CardActions } from "./cards";
import {
  BasicsRow,
  ColorToggles,
  DeckCount,
  DeckSummary,
  FillLandsButton,
  FilterToggle,
  PoolFilterBar,
  RarityToggles,
} from "./controls";
import { FilterGroup } from "../TierFilterBar";
import { breakdownTabFromHash, PhoneBreakdown, setAnchor } from "./Breakdown";
import { DayNav, PreviewMove, SubmitButton, Toast, TodayPoolLink } from "./shared";
import { usePreference } from "./usePreference";

type Tab = "pool" | "deck" | "results";

const PILE_WIDTH = 104;

export const MobileBuilder = ({ view }: { view: BuilderView }) => {
  const [tab, setTab] = useState<Tab>(
    view.results.available && (!view.isToday || breakdownTabFromHash()) ? "results" : "pool",
  );
  const leaveResults = (next: Tab) => {
    setAnchor(null);
    setTab(next);
  };
  const [filtersOpen, setFiltersOpen] = useState(false);
  const { builder } = view;
  return (
    <div className={cn("flex flex-col", tab === "results" ? "pb-6" : "pb-[60px]")}>
      <div className="flex items-center justify-between gap-2 px-2 pt-2 font-display text-[13px] tracking-[0.14em] text-subtle">
        <span className="truncate">
          {view.setName.toUpperCase()} POOL <span className="text-green">#{view.pool.poolNumber}</span>
        </span>
        <DayNav view={view} withToday={false} />
      </div>
      {!view.isToday && <TodayPoolLink className="mx-2 mt-1.5" />}
      <div className="sticky top-0 z-40 flex items-center gap-2 border-b border-border bg-bg px-2 py-1.5">
        <SetGlyph code={view.pool.setCode} size={22} />
        <div
          className={cn(
            "grid flex-1 rounded border border-border2 p-0.5",
            view.results.available ? "grid-cols-[auto_auto_minmax(0,1fr)]" : "grid-cols-2",
          )}
        >
          <TabButton
            active={tab === "pool"}
            onClick={() => leaveResults("pool")}
            label="POOL"
            count={builder.side.length}
          />
          <TabButton
            active={tab === "deck"}
            onClick={() => leaveResults("deck")}
            label="DECK"
            count={builder.deck.length}
          />
          {view.results.available && (
            <TabButton
              active={tab === "results"}
              onClick={() => setTab("results")}
              label="CARD BREAKDOWN"
              count={null}
            />
          )}
        </div>
        <CopyIconButton label="Copy Link" text={view.linkText} onBlocked={view.copyBlocked}>
          <Copy size={16} />
        </CopyIconButton>
        <CopyIconButton label="Export for Arena" text={view.exportText} onBlocked={view.copyBlocked}>
          <Download size={16} />
        </CopyIconButton>
      </div>
      {view.notice && <Toast notice={view.notice} phone />}
      {tab === "pool" && <PoolTab view={view} onOpenFilters={() => setFiltersOpen(true)} />}
      {tab === "deck" && <DeckTab view={view} />}
      {tab === "results" && (
        <div className="px-2 pt-3">
          <PhoneBreakdown view={view} />
        </div>
      )}
      {tab !== "results" && <BottomBar view={view} />}
      {filtersOpen && (
        <FilterSheet onClose={() => setFiltersOpen(false)}>
          <PoolFilterBar
            stacked
            setCode={view.pool.setCode}
            cards={view.pool.cards}
            filters={view.filters}
            onChange={view.setFilters}
            ratings={view.ratings}
            onToggleRatings={view.toggleRatings}
            ratingsAvailable={view.ratingsAvailable}
          />
        </FilterSheet>
      )}
      {view.preview && (
        <CardPreview entry={view.preview} onClose={view.closePreview} step={view.previewStep}>
          <PreviewMove view={view} entry={view.preview} />
        </CardPreview>
      )}
    </div>
  );
};

const PoolTab = ({ view, onOpenFilters }: { view: BuilderView; onOpenFilters: () => void }) => {
  const [layout, setLayout] = usePreference<"strips" | "cards">("daily-sealed:pool-view", "cards");
  const fullCards = layout === "cards";
  const groups = groupByColor(view.sideEntries);
  const shownTotal = view.showHidden ? view.builder.hidden.length : view.builder.side.length;
  return (
    <div className="flex flex-col gap-3 px-2 pt-2">
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-1">
          <FilterGroup stacked joined>
            <ColorToggles
              filters={view.filters}
              onChange={view.setFilters}
              compact
              withColorless
              colorlessClassName="max-[419px]:hidden"
            />
          </FilterGroup>
          <FilterGroup stacked joined>
            <RarityToggles setCode={view.pool.setCode} filters={view.filters} onChange={view.setFilters} compact />
          </FilterGroup>
          <div className="ml-auto flex gap-2">
            <FilterToggle small active={view.showHidden} onClick={view.toggleShowHidden} label="Show hidden cards">
              <EyeOff size={14} />
              <span className="text-[12px]">{view.builder.hidden.length}</span>
            </FilterToggle>
            <FilterToggle small active={false} onClick={onOpenFilters} label="Filters">
              <SlidersHorizontal size={14} />
            </FilterToggle>
            <FilterToggle
              small
              active={fullCards}
              onClick={() => setLayout(fullCards ? "strips" : "cards")}
              label="Show full cards"
            >
              <LayoutGrid size={14} />
            </FilterToggle>
          </div>
        </div>
        {view.sideEntries.length !== shownTotal && <PoolCount shown={view.sideEntries.length} total={shownTotal} />}
      </div>
      {view.showHidden && (
        <div className="flex items-center justify-between text-[12px] text-muted">
          <span>Hidden cards</span>
          {view.builder.hidden.length > 0 && (
            <button type="button" onClick={view.builder.clearHidden} className="text-subtle underline">
              Clear Hidden
            </button>
          )}
        </div>
      )}
      {groups.length === 0 && (
        <span className="py-6 text-center text-[13px] text-muted">No cards match these filters</span>
      )}
      {groups.map((group) =>
        fullCards ? (
          <FullCardGrid key={group.key} entries={group.entries} actions={view.sideActions} />
        ) : (
          <StripList key={group.key} entries={group.entries} actions={view.sideActions} />
        ),
      )}
    </div>
  );
};

const DeckTab = ({ view }: { view: BuilderView }) => {
  const { builder } = view;
  const [deckLayout, setDeckLayout] = usePreference<"piles" | "names">("daily-sealed:deck-grid", "piles");
  const basicsKey = BASICS_PILE_KEY[builder.sort.deck];
  const lastRow = builder.layout.deck.length - 1;
  const runs = builder.layout.deck.map((row, rowIndex) => {
    const groups = row
      .map((pile) => ({
        key: pile.key,
        label: pile.key,
        entries: [
          ...pile.cards.map((index) => ({ index, card: view.pool.cards[index] })),
          ...(rowIndex === lastRow && pile.key === basicsKey ? view.basicCards : []),
        ],
      }))
      .filter((group) => group.entries.length > 0);
    const hasBasicsPile = row.some((pile) => pile.key === basicsKey);
    return rowIndex === lastRow && !hasBasicsPile && view.basicCards.length > 0
      ? [{ key: "land", label: "land", entries: view.basicCards }, ...groups]
      : groups;
  });
  return (
    <div className="flex flex-col gap-3 px-2 pt-2">
      <div className="rounded border border-border bg-surface px-2.5 py-2">
        <DeckSummary builder={builder} />
      </div>
      <BasicsRow builder={builder} readOnly={false} />
      <div className="flex items-center gap-1 [&>button:first-child]:flex-1">
        <FillLandsButton builder={builder} />
        <FilterToggle small active={builder.split} onClick={builder.toggleSplit} label="Split creatures">
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
      {builder.deck.length === 0 && view.basicCards.length === 0 && (
        <span className="py-6 text-center text-[13px] text-muted">Tap cards in the Pool to add them</span>
      )}
      {runs.map((groups, run) => {
        const filled = groups.filter((group) => group.entries.length > 0);
        if (filled.length === 0) {
          return null;
        }
        if (deckLayout === "names") {
          return (
            <div key={run} className="flex flex-col gap-3">
              {filled.map((group) => (
                <StripList key={group.key} entries={group.entries} actions={view.deckActions} />
              ))}
            </div>
          );
        }
        return (
          <div key={run} className="-mx-2 overflow-x-auto px-2 pb-1">
            <div className="w-max">
              <ColumnRow groups={filled} setCode={view.pool.setCode} width={PILE_WIDTH} actions={view.deckActions} />
            </div>
          </div>
        );
      })}
    </div>
  );
};

const PoolCount = ({ shown, total }: { shown: number; total: number }) => (
  <span className="flex items-baseline gap-1.5 font-num text-[13px] text-subtle">
    <span className="line-through">{total}</span>
    <span className="text-text">{shown}</span>
    <span>cards</span>
  </span>
);

const FullCardGrid = ({ entries, actions }: { entries: PoolEntry[]; actions: CardActions }) => (
  <div className="grid grid-cols-3 gap-1.5">
    {entries.map((entry) => {
      const rating = actions.ratingFor?.(entry.card) ?? null;
      return (
        <button
          key={entry.index}
          type="button"
          className="relative"
          onClick={() => actions.onPick(entry)}
          onContextMenu={(event) => {
            event.preventDefault();
            actions.onPreview(entry);
          }}
        >
          <CardFace card={entry.card} className="aspect-[488/680]" />
          {rating !== null && <RatingBadge value={rating} />}
        </button>
      );
    })}
  </div>
);

const BottomBar = ({ view }: { view: BuilderView }) => (
  <div className="fixed inset-x-0 bottom-0 z-50 flex items-center gap-1.5 border-t border-border bg-surface px-2 py-2">
    <DeckCount size={view.builder.deckSize} />
    <IconButton label="Undo" onClick={view.builder.undo} disabled={!view.builder.canUndo}>
      <Undo2 size={16} />
    </IconButton>
    {view.submitState.visible ? (
      <SubmitButton view={view} wide />
    ) : (
      <span className="flex-1 text-center text-[12px] text-muted">Submissions closed</span>
    )}
  </div>
);

const TabButton = ({
  active,
  onClick,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number | null;
}) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      "flex h-8 items-center justify-center gap-2.5 whitespace-nowrap rounded-sm px-2 font-display text-[13px] tracking-[0.1em]",
      active ? "bg-green/15 text-text" : "text-muted",
    )}
  >
    {label}
    {count !== null && <span className="font-num text-[12px] text-muted">{count}</span>}
  </button>
);

const IconButton = ({
  label,
  onClick,
  disabled = false,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) => (
  <button
    type="button"
    aria-label={label}
    onClick={onClick}
    disabled={disabled}
    className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-border2 text-subtle disabled:opacity-40"
  >
    {children}
  </button>
);

const CopyIconButton = ({
  label,
  text,
  onBlocked,
  children,
}: {
  label: string;
  text: () => string;
  onBlocked: () => void;
  children: ReactNode;
}) => {
  const { copied, copy } = useCopyFeedback();
  const run = async () => {
    if (!(await copy(text()))) {
      onBlocked();
    }
  };
  return (
    <button
      type="button"
      aria-label={label}
      onClick={run}
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded border transition-colors",
        copied ? "border-green/60 text-green" : "border-border2 text-subtle",
      )}
    >
      {copied ? <Check size={16} /> : children}
    </button>
  );
};

const FilterSheet = ({ onClose, children }: { onClose: () => void; children: ReactNode }) => (
  <div className="fixed inset-0 z-[90] flex items-end bg-black/60" onClick={onClose}>
    <div
      className="max-h-[80vh] w-full overflow-y-auto rounded-t-lg border-t border-border bg-surface p-3"
      onClick={(event) => event.stopPropagation()}
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-display text-[14px] tracking-[0.2em] text-subtle">FILTERS</h2>
        <IconButton label="Close" onClick={onClose}>
          <X size={16} />
        </IconButton>
      </div>
      {children}
    </div>
  </div>
);
