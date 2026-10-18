import { useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode, type RefObject } from "react";
import { X } from "lucide-react";

import { cn } from "../../../lib/utils";
import {
  FIRST_PICK_POINTS,
  ordinal,
  WHEEL_CARD_POINTS,
  type WheelPack,
  type WheelScore,
} from "../../../data/draftGames";
import { PIXEL_HEADING } from "../pixelStyles";
import { CardTitle, TitleSlot } from "./CardTitle";
import { ResultChip, revealOutcome } from "./PackGrid";
import { pickRevealDelay, REVEAL_START_MS, REVEAL_STEP_MS, useCountUp, useFlip, wheelRevealDelay } from "./motion";

const ROW_GRID = "grid grid-cols-[1.75rem_minmax(0,1fr)_6.25rem] items-center gap-x-2 gap-y-1 lg:-mr-2";
const ROW_GAP_PX = 4;
const EMPTY_SLOT = "rounded-[2.8%/30%] border-2 border-[#1a120b] bg-[#0f0b07] shadow-[inset_3px_3px_0_#05070a]";
const NEXT_SLOT = "border-[#f6c95e] bg-[#f6c95e]/10 shadow-none animate-slotPulse";
const SLOT_HINT = "font-display text-base leading-none";
const REORDER_THRESHOLD_PX = 4;

interface Reorder {
  card: number;
  from: number;
  target: number;
  offset: number;
  pointerId: number;
  startY: number;
  active: boolean;
}

export function OrderSection({
  pack,
  slots,
  score,
  animate,
  listRef,
  dropIndex,
  hint,
  onRemove,
  onReorder,
}: {
  pack: WheelPack;
  slots: number[];
  score: WheelScore | null;
  animate: boolean;
  listRef: RefObject<HTMLDivElement>;
  dropIndex: number | null;
  hint: string;
  onRemove: (card: number) => void;
  onReorder: (slots: number[]) => void;
}) {
  const slotCount = pack.order.length;
  const revealed = score != null;
  const [reorder, setReorder] = useState<Reorder | null>(null);
  const pitch = useRef(0);
  useFlip(listRef, reorder?.active ? String(reorder.card) : null);

  let shown = revealed ? pack.order.map((pick) => pick.card) : slots;
  if (reorder?.active) {
    shown = moveItem(slots, reorder.from, reorder.target);
  }

  const startReorder = (card: number, index: number) => (e: ReactPointerEvent<HTMLDivElement>) => {
    if (revealed || e.button !== 0) {
      return;
    }
    e.preventDefault();
    pitch.current = e.currentTarget.getBoundingClientRect().height + ROW_GAP_PX;
    if (e.isTrusted) {
      e.currentTarget.setPointerCapture(e.pointerId);
    }
    const { pointerId, clientY: startY } = e;
    setReorder({
      card,
      from: index,
      target: index,
      offset: 0,
      pointerId,
      startY,
      active: false,
    });
  };
  const moveReorder = (e: ReactPointerEvent) => {
    if (!reorder || e.pointerId !== reorder.pointerId) {
      return;
    }
    const offset = e.clientY - reorder.startY;
    if (!reorder.active && Math.abs(offset) < REORDER_THRESHOLD_PX) {
      return;
    }
    const target = clamp(Math.round(reorder.from + offset / pitch.current), 0, slots.length - 1);
    setReorder({ ...reorder, offset, target, active: true });
  };
  const endReorder = () => {
    if (reorder?.active && reorder.target !== reorder.from) {
      onReorder(moveItem(slots, reorder.from, reorder.target));
    }
    setReorder(null);
  };

  const shownPoints = useCountUp(score?.points ?? 0, animate, REVEAL_START_MS, slotCount * REVEAL_STEP_MS);

  return (
    <section>
      {revealed ? (
        <RevealHeader title="Real Order" count={<ResultCount value={shownPoints} label={`of ${score.max} Points`} />} />
      ) : (
        <div className={cn("mb-2 h-8", ROW_GRID)}>
          <h2 className={cn("col-span-2 text-2xl", PIXEL_HEADING)}>Your Order</h2>
          <HeaderCount value={slots.length} label={`of ${slotCount}`} className="text-subtle max-lg:hidden" />
        </div>
      )}
      <div ref={listRef} className={cn("relative", ROW_GRID)}>
        {pack.order.map((_, i) => (
          <span
            key={`seat-${i}`}
            className="pl-1 font-display text-lg leading-none text-[#f6c95e]"
            style={{ gridRow: i + 1, gridColumn: 1 }}
          >
            {ordinal(i + 1)}
          </span>
        ))}
        {Array.from({ length: slotCount }, (_, i) => {
          const card = shown[i];
          if (card == null) {
            const isNext = i === shown.length;
            return (
              <div key={`empty-${i}`} style={{ gridRow: i + 1, gridColumn: 2 }}>
                <TitleSlot className={cn(EMPTY_SLOT, isNext && NEXT_SLOT)}>
                  {isNext && <span className={cn(SLOT_HINT, "text-[#f6c95e]")}>{hint}</span>}
                </TitleSlot>
              </div>
            );
          }
          const dragging = reorder?.active && reorder.card === card;
          const dragShift = dragging ? (reorder.from - reorder.target) * pitch.current + reorder.offset : 0;
          return (
            <div
              key={card}
              data-flip={card}
              onPointerDown={startReorder(card, slots.indexOf(card))}
              onPointerMove={moveReorder}
              onPointerUp={endReorder}
              onPointerCancel={endReorder}
              className={cn(
                "animate-rowIn rounded-[2.8%/30%]",
                !revealed && "cursor-grab touch-none select-none active:cursor-grabbing",
                dragging && "relative z-20 shadow-[0_10px_24px_rgba(0,0,0,0.6)]",
              )}
              style={{
                gridRow: i + 1,
                gridColumn: 2,
                transform: dragging ? `translateY(${dragShift}px) scale(1.02)` : undefined,
              }}
            >
              <CardTitle card={pack.cards[card]} className="shadow-[0_1px_3px_rgba(0,0,0,0.6)]" />
            </div>
          );
        })}
        {Array.from({ length: slotCount }, (_, i) => (
          <div key={`trailing-${i}`} className="flex items-center pl-3" style={{ gridRow: i + 1, gridColumn: 3 }}>
            {revealed ? (
              <RowResult
                yourIndex={slots.indexOf(pack.order[i].card)}
                realIndex={i}
                points={i === 0 && score.firstPickExact ? FIRST_PICK_POINTS : 0}
                delay={pickRevealDelay(i, animate)}
              />
            ) : (
              slots[i] != null && (
                <span className="flex w-16 justify-center">
                  <button
                    onClick={() => onRemove(slots[i])}
                    aria-label={`Remove ${pack.cards[slots[i]].n}`}
                    className={cn(
                      "grid size-7 place-items-center border-2 border-[#1a120b] bg-[#2b3445] text-text",
                      "shadow-[2px_2px_0_#05070a] hover:brightness-125",
                    )}
                  >
                    <X size={16} />
                  </button>
                </span>
              )
            )}
          </div>
        ))}
        {dropIndex != null && (
          <div
            className="pointer-events-none absolute right-[6.75rem] left-[2.25rem] h-1 bg-[#f6c95e]"
            style={{
              top: `calc(${dropIndex} * (100% + ${ROW_GAP_PX}px) / ${slotCount} - 3px)`,
            }}
          />
        )}
      </div>
    </section>
  );
}

export function WheelSection({
  pack,
  slots,
  score,
  animate,
}: {
  pack: WheelPack;
  slots: number[];
  score: WheelScore | null;
  animate: boolean;
}) {
  const wheelCount = pack.wheel.length;
  const leftOut = pack.pack.filter((card) => !slots.includes(card));
  const cards = score ? pack.wheel : leftOut.length === wheelCount ? leftOut : [];
  const delay = wheelRevealDelay(pack.order.length, animate);
  return (
    <section className="mt-4 border-t-2 border-[#3a2a17] pt-4">
      {score ? (
        <RevealHeader
          title="Real Wheel"
          count={
            <span className="flex animate-stamp" style={{ animationDelay: `${delay}ms` }}>
              <ResultCount value={score.wheelCalled} label={`of ${wheelCount} Correct`} />
            </span>
          }
        />
      ) : (
        <div className="mb-2 flex h-10 items-center gap-3">
          <h2 className={cn("text-2xl", PIXEL_HEADING)}>Your Wheel</h2>
        </div>
      )}
      <div className={ROW_GRID}>
        {Array.from({ length: wheelCount }, (_, i) => {
          const card = cards[i];
          const row = i + 1;
          if (card == null) {
            return (
              <div
                key={`wheel-empty-${i}`}
                className={cn(i > 0 && "max-lg:hidden")}
                style={{ gridRow: row, gridColumn: 2 }}
              >
                <TitleSlot className={EMPTY_SLOT}>
                  {i === 0 && <span className={cn(SLOT_HINT, "truncate text-text")}>Unpicked cards appear here</span>}
                </TitleSlot>
              </div>
            );
          }
          const yourIndex = slots.indexOf(card);
          return (
            <div key={`wheel-${card}`} className="contents">
              <div
                className="animate-rowIn"
                style={{
                  gridRow: row,
                  gridColumn: 2,
                  animationDelay: `${i * 30}ms`,
                }}
              >
                <CardTitle card={pack.cards[card]} className="shadow-[0_1px_3px_rgba(0,0,0,0.6)]" />
              </div>
              <div className="flex items-center pl-3" style={{ gridRow: row, gridColumn: 3 }}>
                {score && (
                  <RowResult
                    yourIndex={yourIndex}
                    realIndex={-1}
                    points={yourIndex < 0 ? WHEEL_CARD_POINTS : 0}
                    delay={delay}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function RevealHeader({ title, count }: { title: string; count: ReactNode }) {
  return (
    <div className="mb-2 flex h-8 items-center gap-2 lg:-mr-2">
      <h2 className={cn("shrink-0 text-2xl", PIXEL_HEADING)}>{title}</h2>
      <span className="flex flex-1 justify-center">{count}</span>
      <span className="w-[6.25rem] shrink-0 pl-3">
        <span className={cn("flex w-16 justify-center whitespace-nowrap text-lg", PIXEL_HEADING)}>Your Order</span>
      </span>
    </div>
  );
}

function ResultCount({ value, label }: { value: number; label: string }) {
  return (
    <span className={cn("flex items-baseline gap-1.5 whitespace-nowrap", PIXEL_HEADING)}>
      <span className="text-3xl">{value}</span>
      <span className="text-lg">{label}</span>
    </span>
  );
}

function HeaderCount({ value, label, className }: { value: number; label: string; className: string }) {
  return (
    <span
      className={cn(
        "ml-3 flex w-16 items-baseline justify-center gap-1.5 whitespace-nowrap font-display leading-none",
        className,
      )}
    >
      <span className="text-3xl">{value}</span>
      <span className="text-lg">{label}</span>
    </span>
  );
}

function RowResult({
  yourIndex,
  realIndex,
  points,
  delay,
}: {
  yourIndex: number;
  realIndex: number;
  points: number;
  delay: number;
}) {
  return (
    <span className="flex items-center gap-1.5 animate-fadeIn" style={{ animationDelay: `${delay}ms` }}>
      <ResultChip yourIndex={yourIndex} outcome={revealOutcome(realIndex, yourIndex)} className="w-16 text-base" />
      {points > 0 && <span className="font-display text-lg leading-none text-[#f6c95e]">+{points}</span>}
    </span>
  );
}

function moveItem(list: number[], from: number, to: number): number[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
