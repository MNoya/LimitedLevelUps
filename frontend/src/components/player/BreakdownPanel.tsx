import { useEffect, useMemo, useRef, useState } from "react";
import { fmtPts } from "../Brand";
import { DonutChart } from "../DonutChart";
import { Pip, Pips } from "../ManaPips";
import { Record } from "../Record";
import { SectionLabel } from "../SectionLabel";
import { TrophyCount } from "../TrophyCount";
import { cn } from "../../lib/utils";
import { COLOR_STROKES, comboColors, FMT_COLORS, shortFormat } from "../../data/format-display";
import { colorsDisplayName } from "../../data/filters";
import { colorsOf, mainColors } from "../../data/utils";
import type { PlayerDraftEvent, PlayerFormatBreakdown, SelfReportedEvent } from "../../types/leaderboard";

export const COLOR_KEYS: Array<"W" | "U" | "B" | "R" | "G"> = ["W", "U", "B", "R", "G"];

export const COLOR_NAMES: Record<"W" | "U" | "B" | "R" | "G", string> = {
  W: "White",
  U: "Blue",
  B: "Black",
  R: "Red",
  G: "Green",
};

const PANEL_TITLE_COLOR = "#e6ecf5";

interface DonutSize {
  size: number;
  radius: number;
  strokeWidth: number;
  deckRowHeight: number | null;
  deckListHeight: number;
}

const DONUT_SIZES: Record<"regular" | "compact", DonutSize> = {
  regular: { size: 148, radius: 56, strokeWidth: 18, deckRowHeight: null, deckListHeight: 148 },
  compact: { size: 124, radius: 48, strokeWidth: 15, deckRowHeight: 26, deckListHeight: 4 * 26 },
};

const SCROLL_LIST_CLASS =
  "overflow-y-auto overflow-x-hidden pr-2 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent " +
  "[&::-webkit-scrollbar-thumb]:bg-border2 [&::-webkit-scrollbar-thumb]:rounded-full";

const SCROLL_LIST_STYLE = { scrollbarWidth: "thin", scrollbarColor: "#3b4458 transparent" } as const;

interface PlayerAggregates {
  colorCount: Record<"W" | "U" | "B" | "R" | "G", number>;
  comboCount: Record<string, number>;
  comboTrophies: Record<string, number>;
}

export function BreakdownPanel({
  breakdown,
  totalScore,
  events,
  selfReported,
  showPoints,
  lockedFormats,
  bordered = true,
  compact = false,
  labels = true,
  colorsPlayed = true,
  className,
}: {
  breakdown: PlayerFormatBreakdown[];
  totalScore: number;
  events: PlayerDraftEvent[];
  selfReported: SelfReportedEvent[];
  showPoints: boolean;
  lockedFormats?: string[] | null;
  bordered?: boolean;
  compact?: boolean;
  labels?: boolean;
  colorsPlayed?: boolean;
  className?: string;
}) {
  const donut = compact ? DONUT_SIZES.compact : DONUT_SIZES.regular;
  const formatBreakdown = useMemo(
    () => [...breakdown].sort((a, b) => b.scoreContribution - a.scoreContribution),
    [breakdown],
  );
  const total = formatBreakdown.reduce((s, f) => s + f.scoreContribution, 0) || 1;
  const aggregates = aggregate(events, selfReported);
  const hasPoints = showPoints && formatBreakdown.length > 0;

  const [fmtHover, setFmtHover] = useState<string | null>(null);
  const activeFmt = fmtHover ?? lockedFormats ?? null;

  return (
    <section className={cn("py-5 pr-8 pl-6 min-[1360px]:pl-10", bordered && "border-r border-border", className)}>
      {hasPoints && (
        <>
          {labels && (
            <SectionLabel size={15} letterSpacing="0.18em" color={PANEL_TITLE_COLOR} className={cn("text-center whitespace-nowrap", compact ? "mb-2" : "mb-3.5")} style={{ width: donut.size }}>POINTS BY FORMAT</SectionLabel>
          )}
          <div className={cn("flex items-center gap-5", compact ? "mb-3" : "mb-4")}>
            <DonutChart
              pieHole={0.5}
              entries={formatBreakdown.map((f) => ({
                key: f.formatLabel,
                value: f.scoreContribution / total,
                color: FMT_COLORS[f.formatLabel] ?? "#5c8aff",
              }))}
              radius={donut.radius}
              strokeWidth={donut.strokeWidth}
              size={donut.size}
              activeKey={activeFmt}
              onHoverEntry={setFmtHover}
            />
            <FormatLegend
              breakdown={formatBreakdown}
              totalScore={totalScore}
              hoveredKey={activeFmt}
              onHover={setFmtHover}
              compact={compact}
              maxHeight={compact ? donut.size : undefined}
            />
          </div>
        </>
      )}

      {labels && (
        <SectionLabel size={15} letterSpacing="0.18em" color={PANEL_TITLE_COLOR} className={cn("mb-3 text-center whitespace-nowrap", hasPoints && "mt-6")} style={{ width: 148 }}>DECK COLORS</SectionLabel>
      )}
      <DeckColorsChart {...aggregates} donut={donut} />
      {colorsPlayed && (
        <>
          <SectionLabel size={15} letterSpacing="0.18em" color={PANEL_TITLE_COLOR} className="mt-6 mb-3 text-center whitespace-nowrap" style={{ width: 148 }}>COLORS PLAYED</SectionLabel>
          <ColorsPlayedChart {...aggregates} donut={donut} />
        </>
      )}
    </section>
  );
}

export function aggregate(
  events: PlayerDraftEvent[],
  selfReported: readonly SelfReportedEvent[] = [],
): PlayerAggregates {
  const colorCount: PlayerAggregates["colorCount"] = { W: 0, U: 0, B: 0, R: 0, G: 0 };
  const comboCount: Record<string, number> = {};
  const comboTrophies: Record<string, number> = {};
  for (const e of [...events, ...selfReported]) {
    const main = mainColors(e.colors);
    for (const c of main) {
      if (c in colorCount) colorCount[c as keyof typeof colorCount]++;
    }
    const combo = colorsOf(e.colors);
    if (combo.length === 0) continue;
    comboCount[combo] = (comboCount[combo] ?? 0) + 1;
    if (e.isTrophy) comboTrophies[combo] = (comboTrophies[combo] ?? 0) + 1;
  }
  return { colorCount, comboCount, comboTrophies };
}

function DeckColorsChart({ comboCount, comboTrophies, donut }: PlayerAggregates & { donut: DonutSize }) {
  const comboEntries = Object.entries(comboCount).sort((a, b) => b[1] - a[1]);
  const [deckHover, setDeckHover] = useState<string | null>(null);
  const deckRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  useEffect(() => {
    if (deckHover) {
      deckRowRefs.current[deckHover]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [deckHover]);
  return (
    <div className="flex items-center gap-5">
      <DonutChart
        pieHole={0.5}
        entries={comboEntries.map(([k, v]) => ({
          key: k,
          value: v,
          colors: comboColors(k),
        }))}
        radius={donut.radius}
        strokeWidth={donut.strokeWidth}
        size={donut.size}
        activeKey={deckHover}
        onHoverEntry={setDeckHover}
      />
      <div
        className={cn("flex-1 flex flex-col", !donut.deckRowHeight && "gap-1", SCROLL_LIST_CLASS)}
        style={{ ...SCROLL_LIST_STYLE, maxHeight: donut.deckListHeight }}
      >
        {comboEntries.map(([code, count]) => (
          <div
            key={code}
            ref={(el) => {
              deckRowRefs.current[code] = el;
            }}
            onMouseEnter={() => setDeckHover(code)}
            onMouseLeave={() => setDeckHover(null)}
            className={cn(
              "grid gap-2 items-center px-1.5 rounded transition-colors cursor-default",
              deckHover === code && "bg-surface2",
            )}
            style={{
              gridTemplateColumns: "auto 1fr 44px 40px",
              height: donut.deckRowHeight ?? undefined,
              flexShrink: 0,
            }}
          >
            <Pips colors={code} size={14} />
            <span className="font-display text-[15px] tracking-[0.06em]">
              {colorsDisplayName(code)}
            </span>
            <TrophyCount
              count={comboTrophies[code] ?? 0}
              size="md"
              display
              fixedDigits={2}
              className="text-subtle justify-self-end"
            />
            <span className="font-num text-[15px] text-subtle text-right">
              ×{count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ColorsPlayedChart({ colorCount, donut }: PlayerAggregates & { donut: DonutSize }) {
  const colorTotal = Object.values(colorCount).reduce((a, b) => a + b, 0) || 1;
  const [colorHover, setColorHover] = useState<string | null>(null);
  return (
    <div className="flex items-center gap-5">
      <DonutChart
        pieHole={0.5}
        entries={Object.entries(colorCount)
          .filter(([, v]) => v > 0)
          .map(([k, v]) => ({ key: k, value: v, color: COLOR_STROKES[k] }))}
        radius={donut.radius}
        strokeWidth={donut.strokeWidth}
        size={donut.size}
        activeKey={colorHover}
        onHoverEntry={setColorHover}
      />
      <div className="flex-1 flex flex-col gap-1 pr-4">
        {COLOR_KEYS.map((c) => {
          const pct = (colorCount[c] / colorTotal) * 100;
          return (
            <div
              key={c}
              onMouseEnter={() => setColorHover(c)}
              onMouseLeave={() => setColorHover(null)}
              className={cn(
                "grid gap-2 items-center px-1.5 -mx-1.5 rounded transition-colors cursor-default",
                colorHover === c && "bg-surface2",
              )}
              style={{ gridTemplateColumns: "auto 1fr 48px" }}
            >
              <Pip c={c} size={14} />
              <span className="font-display text-[15px] tracking-[0.06em]">
                {COLOR_NAMES[c]}
              </span>
              <span className="font-num text-[15px] text-subtle text-right">
                {pct.toFixed(0)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FormatLegend({
  breakdown,
  totalScore,
  hoveredKey,
  onHover,
  compact = false,
  maxHeight,
}: {
  breakdown: PlayerFormatBreakdown[];
  totalScore: number;
  hoveredKey?: string | string[] | null;
  onHover?: (key: string | null) => void;
  compact?: boolean;
  maxHeight?: number;
}) {
  const isHighlighted = (label: string) =>
    Array.isArray(hoveredKey) ? hoveredKey.includes(label) : hoveredKey === label;
  return (
    <div
      className={cn("flex-1 flex flex-col", maxHeight && SCROLL_LIST_CLASS)}
      style={maxHeight ? { ...SCROLL_LIST_STYLE, maxHeight } : undefined}
    >
      {breakdown.map((f) => {
        const pct = totalScore ? (f.scoreContribution / totalScore) * 100 : 0;
        return (
          <div
            key={f.formatLabel}
            onMouseEnter={onHover ? () => onHover(f.formatLabel) : undefined}
            onMouseLeave={onHover ? () => onHover(null) : undefined}
            className={cn(
              "grid items-center gap-2.5 px-1.5 -mx-1.5 rounded transition-colors cursor-default",
              compact ? "py-[3px]" : "py-[5px]",
              isHighlighted(f.formatLabel) && "bg-surface2",
            )}
            style={{ gridTemplateColumns: "1fr 44px 68px 48px" }}
          >
            <span
              className="font-display text-[15px] tracking-[0.06em]"
              style={{ color: FMT_COLORS[f.formatLabel] ?? "#5c8aff" }}
            >
              {shortFormat(f.formatLabel)}
            </span>
            <TrophyCount
              count={f.trophies}
              size="md"
              display
              fixedDigits={2}
              className="text-subtle justify-self-end"
            />
            <Record
              mono
              wins={f.wins}
              losses={f.losses}
              className="font-num text-[13px] text-right text-subtle"
            />
            <span
              className={cn(
                "font-display text-[17px] text-right",
                pct > 0 ? "text-green" : "text-muted",
              )}
            >
              {fmtPts(f.scoreContribution)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
