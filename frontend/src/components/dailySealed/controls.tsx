import type { ReactNode } from "react";
import { Minus, Plus, Search } from "lucide-react";

import { Pip } from "../ManaPips";
import { FilterGroup, IconToggle } from "../TierFilterBar";
import { columnPipClass } from "../TierGrid";
import { RaritySetGlyph } from "../Brand";
import { cn } from "../../lib/utils";
import {
  BASIC_NAMES,
  basicCount,
  colorPips,
  COLORS,
  DECK_SIZE,
  filtersActive,
  isCreature,
  isLand,
  NO_FILTERS,
  RARITY_ORDER,
  typeGroupsIn,
  type Color,
  type PoolCard,
  type PoolEntry,
  type PoolFilters,
} from "../../data/dailySealed";
import type { Builder } from "./useBuilder";

const COLOR_NAMES: Record<Color, string> = { W: "White", U: "Blue", B: "Black", R: "Red", G: "Green" };

const CURVE_VALUES = [1, 2, 3, 4, 5, 6];

export const PoolFilterBar = ({
  setCode,
  cards,
  filters,
  onChange,
  ratings,
  onToggleRatings,
  ratingsAvailable,
  stacked = false,
}: {
  stacked?: boolean;
  setCode: string;
  cards: PoolCard[];
  filters: PoolFilters;
  onChange: (filters: PoolFilters) => void;
  ratings: boolean;
  onToggleRatings: () => void;
  ratingsAvailable: boolean;
}) => {
  const toggleType = (key: string) =>
    onChange({
      ...filters,
      types: filters.types.includes(key) ? filters.types.filter((type) => type !== key) : [...filters.types, key],
    });
  return (
    <div className={cn("flex flex-col gap-3", stacked && "items-center")}>
      <FilterGroup label="COLOR" stacked joined>
        <ColorToggles filters={filters} onChange={onChange} compact={false} withColorless />
      </FilterGroup>
      <div className={cn("flex items-end", stacked ? "justify-center gap-2" : "w-full justify-between")}>
        <FilterGroup label="RARITY" stacked joined>
          <RarityToggles setCode={setCode} filters={filters} onChange={onChange} compact={false} />
        </FilterGroup>
        {ratingsAvailable && (
          <FilterBlock label="GIH WR">
            <FilterToggle active={ratings} onClick={onToggleRatings} wide className="h-10">
              <span className="text-[12px]">{ratings ? "On" : "Off"}</span>
            </FilterToggle>
          </FilterBlock>
        )}
      </div>
      <FilterGroup label="TYPE" stacked joined>
        {typeGroupsIn(cards).map((group) => (
          <IconToggle
            key={group.key}
            active={filters.types.includes(group.key)}
            onClick={() => toggleType(group.key)}
            label={group.label}
            narrow
          >
            <i
              className={`ms ms-${group.ms} relative -top-[2px]`}
              style={{ fontSize: 17, WebkitTextStroke: "0.6px currentColor" }}
            />
          </IconToggle>
        ))}
      </FilterGroup>
      <FilterBlock label="SEARCH">
        <label className="flex h-9 w-full items-center gap-2 rounded border border-border2 px-2 text-muted focus-within:border-subtle">
          <Search size={14} />
          <input
            value={filters.search}
            onChange={(event) => onChange({ ...filters, search: event.target.value })}
            placeholder="Card name or type"
            className="min-w-0 flex-1 bg-transparent text-[13px] text-text placeholder:text-muted focus:outline-none"
          />
        </label>
      </FilterBlock>
      {filtersActive(filters) && (
        <button
          type="button"
          onClick={() => onChange(NO_FILTERS)}
          className="h-8 rounded border border-border2 text-[12px] text-subtle hover:bg-surface2 hover:text-text"
        >
          Clear Filters
        </button>
      )}
    </div>
  );
};

export const ColorToggles = ({
  filters,
  onChange,
  compact,
  withColorless,
  colorlessClassName,
}: {
  filters: PoolFilters;
  onChange: (filters: PoolFilters) => void;
  compact: boolean;
  withColorless: boolean;
  colorlessClassName?: string;
}) => {
  const toggleColor = (color: Color) => {
    const colors = filters.colors.includes(color)
      ? filters.colors.filter((c) => c !== color)
      : [...filters.colors, color];
    onChange({ ...filters, colors });
  };
  return (
    <>
      {COLORS.map((color) => (
        <IconToggle
          key={color}
          active={filters.colors.includes(color)}
          onClick={() => toggleColor(color)}
          label={COLOR_NAMES[color]}
          narrow
          compact={compact}
          tooltip={!compact}
        >
          <i className={columnPipClass(color)} style={{ fontSize: 15 }} />
        </IconToggle>
      ))}
      {withColorless && (
        <IconToggle
          active={filters.colorless}
          onClick={() => onChange({ ...filters, colorless: !filters.colorless })}
          label="Colorless"
          narrow
          compact={compact}
          tooltip={!compact}
          className={colorlessClassName}
        >
          <i className={columnPipClass("C")} style={{ fontSize: 15 }} />
        </IconToggle>
      )}
    </>
  );
};

export const RarityToggles = ({
  setCode,
  filters,
  onChange,
  compact,
}: {
  setCode: string;
  filters: PoolFilters;
  onChange: (filters: PoolFilters) => void;
  compact: boolean;
}) => (
  <>
    {RARITY_ORDER.map((rarity) => (
      <IconToggle
        key={rarity}
        active={filters.rarities.includes(rarity)}
        label={rarity[0].toUpperCase() + rarity.slice(1)}
        compact={compact}
        narrow
        tooltip={!compact}
        onClick={() =>
          onChange({
            ...filters,
            rarities: filters.rarities.includes(rarity)
              ? filters.rarities.filter((value) => value !== rarity)
              : [...filters.rarities, rarity],
          })
        }
      >
        <RaritySetGlyph code={setCode} rarity={rarity} size={compact ? 18 : 22} />
      </IconToggle>
    ))}
  </>
);

export const FilterBlock = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex flex-col gap-1">
    <span className="whitespace-nowrap text-center font-display text-[12px] tracking-[0.2em] text-subtle">{label}</span>
    <div className="flex flex-wrap justify-center gap-1.5">{children}</div>
  </div>
);

export const FilterToggle = ({
  active,
  onClick,
  label,
  wide = false,
  small = false,
  className,
  children,
}: {
  active: boolean;
  onClick: () => void;
  label?: string;
  wide?: boolean;
  small?: boolean;
  className?: string;
  children: ReactNode;
}) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={label}
    aria-pressed={active}
    className={cn(
      "flex items-center justify-center gap-1 rounded border",
      small ? "h-8 min-w-8 px-1" : "h-9",
      !small && (wide ? "px-2.5" : "w-9"),
      active ? "border-green bg-green/10 text-text" : "border-border2 text-muted hover:bg-surface2",
      className,
    )}
  >
    {children}
  </button>
);

export const BasicsGrid = ({ builder, readOnly }: { builder: Builder; readOnly: boolean }) => (
  <div className="flex flex-col gap-2">
    <div className="grid grid-cols-5 gap-1.5">
      {COLORS.map((color) => (
        <div key={color} className="flex flex-col items-stretch overflow-hidden rounded border border-border2">
          <StepButton
            label={`Add ${BASIC_NAMES[color]}`}
            disabled={readOnly}
            onClick={() => builder.adjustBasic(color, 1)}
            className="h-8 w-full"
          >
            <Plus size={14} />
          </StepButton>
          <span className="flex flex-col items-center gap-2 py-2">
            <Pip c={color} size={15} />
            <span className="font-num text-[16px] leading-none">{builder.basics[color]}</span>
          </span>
          <StepButton
            label={`Remove ${BASIC_NAMES[color]}`}
            disabled={readOnly || builder.basics[color] === 0}
            onClick={() => builder.adjustBasic(color, -1)}
            className="h-8 w-full"
          >
            <Minus size={14} />
          </StepButton>
        </div>
      ))}
    </div>
    {!readOnly && <FillLandsButton builder={builder} />}
  </div>
);

export const BasicsRow = ({ builder, readOnly }: { builder: Builder; readOnly: boolean }) => (
  <div className="flex min-w-0 flex-1 items-center gap-1">
    {COLORS.map((color) => (
      <div key={color} className="flex h-9 min-w-0 flex-1 items-center justify-between rounded border border-border2 px-0.5">
        <StepButton
          label={`Remove ${BASIC_NAMES[color]}`}
          disabled={readOnly || builder.basics[color] === 0}
          onClick={() => builder.adjustBasic(color, -1)}
        >
          <Minus size={13} />
        </StepButton>
        <span className="flex items-center gap-1 font-num text-[14px]">
          <Pip c={color} size={14} />
          {builder.basics[color]}
        </span>
        <StepButton label={`Add ${BASIC_NAMES[color]}`} disabled={readOnly} onClick={() => builder.adjustBasic(color, 1)}>
          <Plus size={13} />
        </StepButton>
      </div>
    ))}
  </div>
);

const StepButton = ({
  label,
  disabled,
  onClick,
  className,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}) => (
  <button
    type="button"
    aria-label={label}
    disabled={disabled}
    onClick={onClick}
    className={cn(
      "flex h-6 w-6 items-center justify-center rounded-sm text-subtle transition-colors duration-100",
      "hover:bg-green/15 hover:text-green active:bg-green/35 active:text-green",
      "disabled:pointer-events-none disabled:opacity-30",
      className,
    )}
  >
    {children}
  </button>
);

export const FillLandsButton = ({ builder }: { builder: Builder }) => {
  const open = DECK_SIZE - builder.deckSize;
  return (
    <button
      type="button"
      disabled={open <= 0 || builder.deck.length === 0}
      onClick={builder.fillLands}
      className="h-8 rounded border border-border2 text-[12px] text-subtle hover:bg-surface2 hover:text-text disabled:opacity-40"
    >
      Auto-fill lands
    </button>
  );
};

export const DeckStats = ({ builder }: { builder: Builder }) => {
  const counts = deckCounts(builder);
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 font-num text-[13px] text-subtle">
        <Stat label="CREATURES" value={counts.creatures} />
        <Stat label="SPELLS" value={counts.spells} />
        <Stat label="LANDS" value={counts.lands} />
      </div>
      <Curve entries={builder.deck} tall />
      <PipsVsSources builder={builder} fill />
    </div>
  );
};

export const DeckSummary = ({ builder }: { builder: Builder }) => {
  const counts = deckCounts(builder);
  return (
    <div className="flex items-end justify-between gap-2">
      <div className="flex flex-col gap-1 whitespace-nowrap font-num text-[12px] text-subtle">
        <span>
          <span className="text-[15px] text-text">{counts.creatures}</span> creatures
        </span>
        <span>
          <span className="text-[15px] text-text">{counts.spells}</span> spells
        </span>
        <span>
          <span className="text-[15px] text-text">{counts.lands}</span> lands
        </span>
      </div>
      <Curve entries={builder.deck} tall={false} />
      <PipsVsSources builder={builder} />
    </div>
  );
};

const deckCounts = (builder: Builder) => {
  let creatures = 0;
  let spells = 0;
  for (const entry of builder.deck) {
    if (isLand(entry.card)) {
      continue;
    }
    if (isCreature(entry.card)) {
      creatures += 1;
    } else {
      spells += 1;
    }
  }
  return { creatures, spells, lands: builder.deck.length - creatures - spells + basicCount(builder.basics) };
};

const Stat = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="flex flex-col items-center gap-1">
    <span className="font-display text-[12px] tracking-[0.16em] text-subtle">{label}</span>
    <span className="text-[18px] leading-none text-text">{value}</span>
  </div>
);

interface CurveBucket {
  mv: number;
  creatures: number;
  other: number;
}

const Curve = ({ entries, tall }: { entries: PoolEntry[]; tall: boolean }) => {
  const buckets = CURVE_VALUES.map((mv) => ({ mv, creatures: 0, other: 0 }));
  for (const entry of entries) {
    if (isLand(entry.card)) {
      continue;
    }
    const bucket = buckets[Math.min(Math.max(entry.card.cmc, 1), 6) - 1];
    if (isCreature(entry.card)) {
      bucket.creatures += 1;
    } else {
      bucket.other += 1;
    }
  }
  return <CurveBars buckets={buckets} tall={tall} />;
};

const CurveBars = ({
  buckets,
  tall,
  format = String,
}: {
  buckets: CurveBucket[];
  tall: boolean;
  format?: (value: number) => string;
}) => {
  let tallest = 1;
  for (const bucket of buckets) {
    tallest = Math.max(tallest, bucket.creatures + bucket.other);
  }
  return (
    <div className={cn("items-end", tall ? "grid grid-cols-6 gap-2" : "flex gap-[3px]")}>
      {buckets.map((bucket) => (
        <div key={bucket.mv} className={cn("flex flex-col items-center gap-0.5", tall ? "w-full" : "w-[13px]")}>
          {tall && (
            <span className="h-4 font-num text-[12px] leading-4 text-subtle">
              {bucket.creatures + bucket.other > 0 ? format(bucket.creatures + bucket.other) : null}
            </span>
          )}
          <div
            className={cn(
              "flex w-full flex-col justify-end",
              tall ? "h-20 w-5 overflow-hidden rounded-sm border border-border2" : "h-9",
            )}
          >
            <div className="w-full rounded-t-sm bg-border2" style={{ height: `${(bucket.other / tallest) * 100}%` }} />
            <div className="w-full bg-green/80" style={{ height: `${(bucket.creatures / tallest) * 100}%` }} />
          </div>
          <span className={cn("font-num text-subtle", tall ? "text-[12px]" : "text-[10px]")}>
            {bucket.mv === 6 && tall ? "6+" : bucket.mv}
          </span>
        </div>
      ))}
    </div>
  );
};

const PipsVsSources = ({ builder, fill = false }: { builder: Builder; fill?: boolean }) => {
  const rows = COLORS.map((color) => {
    let pips = 0;
    let sources = builder.basics[color];
    for (const entry of builder.deck) {
      if (isLand(entry.card)) {
        sources += entry.card.identity.includes(color) ? 1 : 0;
      } else {
        pips += colorPips(entry.card, color);
      }
    }
    return { color, pips, sources };
  }).filter((row) => row.pips > 0 || row.sources > 0);
  if (rows.length === 0) {
    return null;
  }
  return (
    <div
      className={cn(
        "grid grid-flow-col grid-rows-3 items-center gap-x-3 gap-y-1 font-num text-[13px]",
        fill ? "w-full justify-items-center" : "w-fit",
      )}
      style={fill ? { gridTemplateColumns: `auto repeat(${rows.length}, minmax(0, 1fr))` } : undefined}
    >
      <span />
      <span className="justify-self-start font-display text-[12px] tracking-[0.16em] text-subtle">PIPS</span>
      <span className="justify-self-start font-display text-[12px] tracking-[0.16em] text-subtle">SOURCES</span>
      {rows.map((row) => [
        <Pip key={`${row.color}-pip`} c={row.color} size={15} />,
        <span key={`${row.color}-pips`} className="text-center">
          {row.pips}
        </span>,
        <span key={`${row.color}-sources`} className="text-center">
          {row.sources}
        </span>,
      ])}
    </div>
  );
};

export const DeckCount = ({ size }: { size: number }) => {
  const tone =
    size === DECK_SIZE
      ? "text-green border-green/60"
      : size > DECK_SIZE
        ? "text-gold border-gold/60"
        : "text-text border-border";
  return (
    <div className={cn("flex h-9 items-center rounded-md border bg-surface2 px-3 font-num", tone)}>
      <span className="flex items-baseline gap-1 leading-none">
        <span className="inline-block w-[2ch] text-right text-[17px] tabular-nums">{size}</span>
        <span className="text-[13px] text-muted">/ {DECK_SIZE}</span>
      </span>
    </div>
  );
};
