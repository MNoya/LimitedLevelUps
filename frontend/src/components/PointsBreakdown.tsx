import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { ScoringInfoButton } from "./ScoringInfoButton";
import { Trophy } from "./Brand";
import { Record } from "./Record";
import { FMT_COLORS, FMT_DEFAULT_COLOR } from "../data/format-display";
import type { PlayerFormatBreakdown } from "../types/leaderboard";
import {
  computeRows,
  fullFormatName,
  pct,
  type BreakdownRow,
} from "./pointsBreakdownShared";

interface Props {
  open: boolean;
  onClose: () => void;
  breakdown: PlayerFormatBreakdown[];
  // When the breakdown is a format-filtered subset, the confidence factor stays player-wide rather
  // than recomputing from the subset's trophies. Omit for the full, unfiltered breakdown.
  confidenceOverride?: number;
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
              <div className="flex items-baseline gap-3 min-w-0">
                <span
                  className="font-display tracking-[0.06em] truncate shrink-0"
                  style={{ color, fontSize: 16, width: 120 }}
                >
                  {fullFormatName(r.label)}
                </span>
                <span
                  className="mono text-[10.5px] text-muted tabular-nums whitespace-nowrap shrink-0 text-left"
                  style={{ width: 68 }}
                >
                  {r.events} {r.events === 1 ? "event" : "events"}
                </span>
                <Record
                  mono
                  wins={r.wins}
                  losses={r.losses}
                  className="mono text-[10.5px] text-muted tabular-nums whitespace-nowrap shrink-0 text-left"
                  style={{ width: 56 }}
                />
              </div>
              <div className="mt-1 text-[10.5px] text-muted tabular-nums tracking-tight flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                {r.isPod ? (
                  <>
                    <span className="mono inline-flex items-center gap-1">
                      {r.count}
                      <Trophy size={11} color="#ffc63a" />
                    </span>
                    <span className="text-green text-[14px] leading-none align-middle">×</span>
                    <span className="mono">5 pts</span>
                    {r.twoWins > 0 && (
                      <>
                        <span className="text-green text-[16px] font-bold leading-none align-middle">+</span>
                        <span className="mono">{r.twoWins} 2-win</span>
                        <span className="text-green text-[14px] leading-none align-middle">×</span>
                        <span className="mono">2 pts</span>
                      </>
                    )}
                    {r.oneWins > 0 && (
                      <>
                        <span className="text-green text-[16px] font-bold leading-none align-middle">+</span>
                        <span className="mono">{r.oneWins} 1-win</span>
                        <span className="text-green text-[14px] leading-none align-middle">×</span>
                        <span className="mono">½ pts</span>
                      </>
                    )}
                  </>
                ) : isLcqD2 ? (
                  <>
                    <span className="mono inline-flex items-center gap-0.5">
                      {r.count}
                      <span className="ml-0.5">wins</span>
                    </span>
                    {earned && (
                      <>
                        <span className="text-green text-[14px] leading-none align-middle">×</span>
                        <span className="mono">{pct(r.rate)} win rate</span>
                      </>
                    )}
                    <span className="text-green text-[14px] leading-none align-middle">×</span>
                    <span className="mono">{r.points} pts</span>
                  </>
                ) : (
                  <>
                    <span className="mono inline-flex items-center gap-1">
                      {r.count}
                      <Trophy size={11} color="#ffc63a" />
                    </span>
                    <span className="text-green text-[14px] leading-none align-middle">×</span>
                    <span className="mono">{r.points} pts</span>
                    {earned && (
                      <>
                        <span className="text-green text-[14px] leading-none align-middle">×</span>
                        <span className="mono">{pct(r.rate)} trophy rate</span>
                      </>
                    )}
                    {earned && confidence > 0 && (
                      <>
                        <span className="text-green text-[14px] leading-none align-middle">×</span>
                        <span className="mono">{pct(confidence)} confidence</span>
                      </>
                    )}
                  </>
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

export function PointsBreakdown({ open, onClose, breakdown, confidenceOverride, anchorRef }: Props) {
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

  const { rows: allRows, confidence } = computeRows(breakdown, confidenceOverride);
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
