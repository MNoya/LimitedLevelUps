import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { ScoringInfoButton } from "./ScoringInfoButton";
import { ArenaRankIcon } from "./ArenaRankIcon";
import { Trophy } from "./Brand";
import { Record } from "./Record";
import { FMT_COLORS, FMT_DEFAULT_COLOR } from "../data/format-display";
import type { PlayerDraftEvent, PlayerFormatBreakdown } from "../types/leaderboard";
import {
  computeRows,
  fullFormatName,
  pct,
  trophyTierCounts,
  type BreakdownRow,
  type RankTerm,
} from "./pointsBreakdownShared";

interface Props {
  open: boolean;
  onClose: () => void;
  breakdown: PlayerFormatBreakdown[];
  // When the breakdown is a format-filtered subset, the confidence factor stays player-wide rather
  // than recomputing from the subset's trophies. Omit for the full, unfiltered breakdown.
  confidenceOverride?: number;
  // Source of the per-rank trophy split. Omit to show one flat points term per format
  events?: readonly PlayerDraftEvent[];
  anchorRef?: React.RefObject<HTMLElement | null>;
}

interface AnchorPos {
  top: number;
  left: number;
  width: number;
  notchLeft: number;
}

const TARGET_WIDTH = 540;
const SIDE_MARGIN = 8;
const GAP = 10;

function CardsLayout({ rows, confidence = 0 }: { rows: BreakdownRow[]; confidence?: number }) {
  return (
    <>
      {rows.map((r) => {
        const color = FMT_COLORS[r.label] ?? FMT_DEFAULT_COLOR;
        const isLcqD2 = r.isLcq;
        const earned = r.isPod ? r.score > 0 : r.count > 0;
        return (
          <div
            key={r.label}
            className="px-4 py-2 border-b border-border last:border-b-0 flex items-center gap-3"
          >
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 min-w-0">
                <span
                  className="font-display tracking-[0.06em] truncate shrink-0"
                  style={{ color, fontSize: 16, width: 120 }}
                >
                  {fullFormatName(r.label)}
                </span>
                <span
                  className="text-[12px] text-subtle tabular-nums whitespace-nowrap shrink-0 text-left"
                  style={{ width: 78 }}
                >
                  {r.events} {r.events === 1 ? "event" : "events"}
                </span>
                <Record
                  mono
                  wins={r.wins}
                  losses={r.losses}
                  className="text-[12px] text-subtle tabular-nums whitespace-nowrap shrink-0 text-left"
                  style={{ width: 62 }}
                />
                {r.rankTerms.length > 0 && (
                  <span className="text-[12px] text-subtle tabular-nums flex flex-wrap items-center gap-x-3 gap-y-0.5 min-w-0">
                    {r.rankTerms.map((t) => (
                      <RankChip key={t.tier ?? "unranked"} term={t} />
                    ))}
                  </span>
                )}
              </div>
              <div className="mt-1 text-[10.5px] text-subtle tabular-nums">
                {r.isPod ? (
                  <TermLine>
                    <TrophyTerm count={r.count} />
                    <Times />
                    <span>5 pts</span>
                    {r.twoWins > 0 && (
                      <>
                        <Plus />
                        <span>{r.twoWins} 2-win</span>
                        <Times />
                        <span>2 pts</span>
                      </>
                    )}
                    {r.oneWins > 0 && (
                      <>
                        <Plus />
                        <span>{r.oneWins} 1-win</span>
                        <Times />
                        <span>½ pts</span>
                      </>
                    )}
                  </TermLine>
                ) : isLcqD2 ? (
                  <TermLine>
                    <span className="inline-flex items-center gap-0.5">
                      {r.count}
                      <span className="ml-0.5">wins</span>
                    </span>
                    {earned && (
                      <>
                        <Times />
                        <span>{pct(r.rate)} win rate</span>
                      </>
                    )}
                    <Times />
                    <span>{r.points} pts</span>
                  </TermLine>
                ) : (
                  <TermLine>
                    <TrophyTerm count={r.count} />
                    {r.rankWeighted ? (
                      <span>({fmtPoints(r.weightedPoints)} pts)</span>
                    ) : (
                      <>
                        <Times />
                        <span>{r.points} pts</span>
                      </>
                    )}
                    {earned && (
                      <>
                        <Times />
                        <span>{pct(r.rate)} trophy rate</span>
                      </>
                    )}
                    {earned && confidence > 0 && (
                      <>
                        <Times />
                        <span>{pct(confidence)} confidence</span>
                      </>
                    )}
                  </TermLine>
                )}
              </div>
            </div>
            <span className="font-display text-text tabular-nums shrink-0 self-center leading-none text-[20px]">
              {earned ? (r.isPod ? r.score.toFixed(0) : r.score.toFixed(2)) : <span className="text-dim">—</span>}
            </span>
          </div>
        );
      })}
    </>
  );
}

export function PointsBreakdown({ open, onClose, breakdown, confidenceOverride, events, anchorRef }: Props) {
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<AnchorPos | null>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      const el = anchorRef?.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const vw = window.innerWidth;
      const width = Math.min(TARGET_WIDTH, vw - SIDE_MARGIN * 2);
      const anchorCenterX = (rect.left + rect.right) / 2;
      const popoverRightX = Math.min(vw - SIDE_MARGIN, rect.right);
      const left = Math.max(SIDE_MARGIN, popoverRightX - width);
      const notchLeft = Math.max(16, Math.min(width - 16, anchorCenterX - left));
      setPos({
        top: rect.bottom + GAP,
        left,
        width,
        notchLeft,
      });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node | null;
      if (!target) return;
      if (anchorRef?.current?.contains(target)) return;
      if (popoverRef.current?.contains(target)) return;
      if (
        target instanceof Element &&
        target.closest("[data-popover-keep-open]")
      ) {
        return;
      }
      onClose();
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open, onClose, anchorRef]);

  if (!open || !pos) return null;

  const tierCounts = events ? trophyTierCounts(events) : undefined;
  const { rows: allRows, confidence } = computeRows(breakdown, confidenceOverride, tierCounts);
  const sorted = [...allRows].sort((a, b) => b.score - a.score);
  const queueRows = sorted.filter((r) => !r.isPod);
  const podRows = sorted.filter((r) => r.isPod);
  const rounded = Math.round(allRows.reduce((s, r) => s + r.score, 0));

  return createPortal(
    <div
      ref={popoverRef}
      role="dialog"
      aria-modal="false"
      aria-label="Points breakdown"
      style={{
        position: "fixed",
        top: pos.top,
        left: pos.left,
        width: pos.width,
      }}
      className="z-50 bg-surface border border-border2 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.7)] animate-fadeUpIn outline-none"
    >
      <span
        aria-hidden="true"
        className="absolute -top-[7px] w-[12px] h-[12px] rotate-45 bg-surface border-l border-t border-border2"
        style={{ left: pos.notchLeft - 6 }}
      />

      <header className="flex items-center justify-between px-4 py-2.5 border-b border-border">
        <span
          className="font-display text-text"
          style={{
            fontSize: 18,
            lineHeight: 1,
            letterSpacing: "0.06em",
            fontFamily: "'Bebas Neue', sans-serif",
            paddingTop: 3,
          }}
        >
          POINTS BREAKDOWN
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-muted hover:text-text transition-colors p-1 bg-transparent border-0 cursor-pointer shrink-0 -mr-1"
        >
          <X size={15} />
        </button>
      </header>

      <div className="pt-1">
        <CardsLayout rows={queueRows} confidence={confidence} />
      </div>

      {podRows.length > 0 && (
        <div className="border-t border-border">
          <CardsLayout rows={podRows} />
        </div>
      )}

      <footer className="px-4 py-2.5 border-t border-border flex items-center justify-between gap-3">
        <ScoringInfoButton size={14} label="ABOUT POINTS" />
        <span className="font-display text-green text-[22px] leading-none tabular-nums shrink-0">
          {rounded}
        </span>
      </footer>
    </div>,
    document.body,
  );
}

function TermLine({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">{children}</div>;
}

function TrophyTerm({ count }: { count: number }) {
  return (
    <span className="inline-flex items-center gap-1">
      {count}
      <Trophy size={11} color="#ffc63a" />
    </span>
  );
}

// Rank art is per division, so a tier stands for itself with its first division's icon
function RankChip({ term }: { term: RankTerm }) {
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      {term.count}
      {term.tier ? (
        <ArenaRankIcon
          endRank={term.tier === "Mythic" ? "Mythic" : `${term.tier}-1`}
          size={15}
          title={`${term.tier}, ${term.points} pts each`}
        />
      ) : (
        <Trophy size={12} color="#ffc63a" />
      )}
    </span>
  );
}

function fmtPoints(points: number): string {
  return String(Math.round(points * 100) / 100);
}

function Times() {
  return <span className="text-green text-[14px] leading-none align-middle">×</span>;
}

function Plus() {
  return <span className="text-green text-[16px] font-bold leading-none align-middle">+</span>;
}
