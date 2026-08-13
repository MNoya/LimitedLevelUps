import { useState, type ReactNode } from "react";
import { cn } from "../lib/utils";
import { keyruneClass } from "./Brand";
import { columnPipClass } from "./TierGrid";
import { Tooltip } from "./Tooltip";
import {
  MANA_VALUE_BUCKETS,
  TREND_COLOR,
  TREND_GLYPH,
  type TierFilterOptions,
  type TierFilters,
} from "../data/tierList";

const RARITY_KEYRUNE: Record<string, string> = { C: "common", U: "uncommon", R: "rare", M: "mythic" };

export function TierFilterBar({
  filters,
  setFilters,
  options,
  setCode,
  hideArt,
  setHideArt,
  stacked = false,
}: {
  filters: TierFilters;
  setFilters: (f: TierFilters) => void;
  options: TierFilterOptions;
  setCode: string;
  hideArt: boolean;
  setHideArt: (value: boolean) => void;
  stacked?: boolean;
}) {
  const toggle = (key: keyof TierFilters, value: string) => {
    const arr = filters[key];
    const next = arr.includes(value) ? arr.filter((x) => x !== value) : [...arr, value];
    setFilters({ ...filters, [key]: next });
  };

  const pickColor = (value: string) => {
    setFilters({ ...filters, colors: filters.colors.includes(value) ? [] : [value] });
  };

  const [trendTipOpen, setTrendTipOpen] = useState(false);
  const trendMode =
    filters.trends.length === 2
      ? "both"
      : filters.trends.length === 1
        ? (filters.trends[0] as "up" | "down")
        : "off";
  const cycleTrend = () => {
    const next =
      trendMode === "off" ? ["up", "down"] : trendMode === "both" ? ["up"] : trendMode === "up" ? ["down"] : [];
    setFilters({ ...filters, trends: next });
    setTrendTipOpen(true);
  };
  const trendCycleLabel =
    trendMode === "off"
      ? `Show cards that moved (${options.trends.up + options.trends.down})`
      : trendMode === "both"
        ? `Show only cards that moved up (${options.trends.up})`
        : trendMode === "up"
          ? `Show only cards that moved down (${options.trends.down})`
          : "Show all cards";

  const colorGroup = (
    <FilterGroup label="COLOR" stacked={stacked} joined inline>
      {options.colors.map((c) => (
        <IconToggle
          key={c.value}
          active={filters.colors.includes(c.value)}
          onClick={() => pickColor(c.value)}
          label={`${c.name} (${c.count})`}
          narrow
        >
          <i className={columnPipClass(c.value)} style={{ fontSize: c.value === "M" ? 21 : 15 }} />
        </IconToggle>
      ))}
    </FilterGroup>
  );

  const rarityGroup = (
    <FilterGroup label="RARITY" stacked={stacked} joined>
      {options.rarities.map((r) => {
        const isCommon = r.value === "C";
        return (
          <IconToggle
            key={r.value}
            active={filters.rarities.includes(r.value)}
            onClick={() => toggle("rarities", r.value)}
            label={`${r.name} (${r.count})`}
            roomy
          >
            <i
              className={cn(
                "ss",
                `ss-${keyruneClass(setCode)}`,
                isCommon ? "" : `ss-${RARITY_KEYRUNE[r.value]} ss-grad`,
              )}
              style={{ fontSize: 22, color: isCommon ? "#fff" : undefined }}
            />
          </IconToggle>
        );
      })}
    </FilterGroup>
  );

  const typeGroup = (
    <FilterGroup label="TYPE" stacked={stacked} joined>
      {options.types.map((t) => (
        <IconToggle
          key={t.value}
          active={filters.cardTypes.includes(t.value)}
          onClick={() => toggle("cardTypes", t.value)}
          label={`${t.label} (${t.count})`}
          roomy
        >
          <i
            className={`ms ms-${t.ms} relative -top-[2px]`}
            style={{ fontSize: 20, WebkitTextStroke: "0.6px currentColor" }}
          />
        </IconToggle>
      ))}
    </FilterGroup>
  );

  const compact = stacked && options.sets.length >= 3;

  const manaValueGroup = (
    <FilterGroup label="MANA VALUE" stacked={stacked} joined className={stacked ? undefined : "max-[1150px]:hidden"}>
      {MANA_VALUE_BUCKETS.map((mv) => (
        <IconToggle
          key={mv}
          active={filters.manaValues.includes(mv)}
          onClick={() => toggle("manaValues", mv)}
          label={`Mana value ${mv}`}
          narrow
          compact={compact}
        >
          <span className={cn("font-display font-bold leading-none", compact ? "text-[15px]" : "text-[18px]")}>
            {mv}
          </span>
        </IconToggle>
      ))}
    </FilterGroup>
  );

  const setGroup =
    options.sets.length > 1 ? (
      <FilterGroup label="SET GROUP" stacked={stacked} joined>
        {options.sets.map((s) => (
          <IconToggle
            key={s.value}
            active={filters.sets.includes(s.value)}
            onClick={() => toggle("sets", s.value)}
            label={`${s.label} (${s.count})`}
            compact={compact}
          >
            <i className={`ss ss-${keyruneClass(s.value)}`} style={{ fontSize: compact ? 16 : 19 }} />
          </IconToggle>
        ))}
      </FilterGroup>
    ) : null;

  const trendGroup = (
    <FilterGroup label="TREND" stacked={stacked} joined>
      <IconToggle
        active={trendMode !== "off"}
        onClick={cycleTrend}
        label={trendCycleLabel}
        narrow
        tooltipOpen={trendTipOpen}
        onTooltipOpenChange={setTrendTipOpen}
      >
        <span className="flex w-[28px] items-center justify-center">
          {trendMode === "up" || trendMode === "down" ? (
            <span className="text-[15px] leading-none" style={{ color: TREND_COLOR[trendMode] }}>
              {TREND_GLYPH[trendMode]}
            </span>
          ) : (
            <span className={cn("flex gap-0.5 text-[12px] leading-none", trendMode === "off" && "opacity-70")}>
              <span style={{ color: TREND_COLOR.up }}>{TREND_GLYPH.up}</span>
              <span style={{ color: TREND_COLOR.down }}>{TREND_GLYPH.down}</span>
            </span>
          )}
        </span>
      </IconToggle>
    </FilterGroup>
  );

  const artGroup = (
    <FilterGroup label="ART" stacked={stacked} joined>
      <IconToggle
        active={hideArt}
        onClick={() => setHideArt(!hideArt)}
        label={hideArt ? "Show card art" : "Hide card art"}
        narrow
        mutedActive
      >
        <span className="flex w-[28px] items-center justify-center">
          <ArtIcon hidden={hideArt} />
        </span>
      </IconToggle>
    </FilterGroup>
  );

  if (stacked) {
    return (
      <div className="flex w-full flex-col gap-y-3">
        <div className="grid w-full grid-cols-2 items-end justify-items-center gap-x-1.5">
          {rarityGroup}
          {typeGroup}
        </div>
        <div className="flex w-full flex-wrap items-end justify-between gap-x-1.5 gap-y-3">
          {manaValueGroup}
          {setGroup}
          {trendGroup}
          {artGroup}
          {colorGroup}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
      {rarityGroup}
      {typeGroup}
      {manaValueGroup}
      {setGroup}
      {trendGroup}
      {artGroup}
    </div>
  );
}

function ArtIcon({ hidden }: { hidden: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2" strokeLinejoin="round" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path d="M21 15l-5-5L5 21" strokeLinecap="round" strokeLinejoin="round" />
      {hidden && <path d="M3 3l18 18" strokeLinecap="round" />}
    </svg>
  );
}

const LABEL = "font-display text-[13px] tracking-[0.2em] text-muted";

const JOINED = cn(
  "[&>button]:rounded-none",
  "[&>button:first-child]:rounded-l-md [&>button:last-child]:rounded-r-md",
  "[&>button:not(:first-child)]:-ml-px",
);

function FilterGroup({
  label,
  children,
  stacked,
  joined = false,
  inline = false,
  className,
}: {
  label: string;
  children: ReactNode;
  stacked: boolean;
  joined?: boolean;
  inline?: boolean;
  className?: string;
}) {
  const buttons = <div className={cn("flex", joined ? JOINED : "gap-1.5")}>{children}</div>;
  if (inline) {
    return (
      <div className={cn("flex grow items-center justify-center", className)}>
        <div className="relative">
          <span className={cn(LABEL, "absolute right-full top-1/2 mr-2 -translate-y-1/2")}>{label}</span>
          {buttons}
        </div>
      </div>
    );
  }
  return (
    <div className={cn("flex flex-col", stacked ? "items-center gap-1" : "gap-0.5", className)}>
      <span className={LABEL}>{label}</span>
      {buttons}
    </div>
  );
}

function IconToggle({
  active,
  onClick,
  label,
  children,
  roomy = false,
  narrow = false,
  compact = false,
  mutedActive = false,
  tooltipOpen,
  onTooltipOpenChange,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  children: ReactNode;
  roomy?: boolean;
  narrow?: boolean;
  compact?: boolean;
  mutedActive?: boolean;
  tooltipOpen?: boolean;
  onTooltipOpenChange?: (open: boolean) => void;
}) {
  const activeClass = mutedActive
    ? "z-10 border-border2 bg-surface2 text-subtle"
    : "z-10 border-green bg-green/10 text-text";
  return (
    <Tooltip label={label} open={tooltipOpen} onOpenChange={onTooltipOpenChange}>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "relative flex h-10 items-center justify-center rounded border transition-colors",
          roomy
            ? "min-w-[40px] px-2.5"
            : narrow
              ? compact
                ? "min-w-[28px] px-1"
                : "min-w-[34px] px-1.5"
              : compact
                ? "min-w-[32px] px-1.5"
                : "min-w-[40px] px-2",
          active
            ? activeClass
            : "border-border2 bg-transparent text-muted hover:bg-surface2 hover:text-text",
        )}
      >
        {children}
      </button>
    </Tooltip>
  );
}
