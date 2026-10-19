import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { ArrowRight, Check, X } from "lucide-react";

import { Trophy } from "../../Brand";
import { Pips } from "../../ManaPips";
import { CardImage } from "../../pod/review/ReviewCard";
import { cn } from "../../../lib/utils";
import { FIRST_PICK_POINTS, ordinal, ordinalSuffix, type WheelPack } from "../../../data/draftGames";
import type { ArtifactCard } from "../../../types/leaderboard";
import { pickRevealDelay, wheelRevealDelay } from "./motion";

const CARD_RADIUS = "rounded-[4.5%/3.2%]";
export const PACK_GRID_WIDTH = "lg:w-[min(calc((100vh-140px)*1.19+32px),calc(100vw-600px))]";
export const GAME_COLUMNS = "lg:grid-cols-[auto_minmax(340px,456px)]";
const SIDEBAR_MIN_PX = 340;
const LAYOUT_GAP_PX = 16;
const CARD_GAP_PX = 8;
const CHROME_HEIGHT_PX = 124;
const CARD_ASPECT = 488 / 680;

interface PackFit {
  columns: number;
  width: number | null;
}
const LONG_PRESS_MS = 450;
const WAVE_STEP_MS = 40;
const PackShapeContext = createContext({ columns: 5, cardCount: 0, waveSteps: [] as number[] });
const DRAG_THRESHOLD_PX = 6;

export function PackGrid({
  children,
  cardCount,
  className,
  onClick,
  gridRef,
}: {
  children: ReactNode;
  cardCount: number;
  className?: string;
  onClick?: () => void;
  gridRef?: RefObject<HTMLDivElement>;
}) {
  const ownRef = useRef<HTMLDivElement>(null);
  const ref = gridRef ?? ownRef;
  const { columns, width } = usePackFit(ref, cardCount);
  const shape = useMemo(
    () => ({ columns, cardCount, waveSteps: snakeWaveSteps(columns, cardCount) }),
    [columns, cardCount],
  );
  return (
    <PackShapeContext.Provider value={shape}>
      <div
        ref={ref}
        onClick={onClick}
        className={cn(
          "grid gap-2 lg:col-start-1 lg:row-span-2 lg:row-start-1",
          "relative [perspective:1200px] lg:self-start",
          PACK_GRID_WIDTH,
          className,
        )}
        style={{ gridTemplateColumns: `repeat(${columns * 2}, minmax(0, 1fr))`, width: width ?? undefined }}
      >
        {children}
      </div>
    </PackShapeContext.Provider>
  );
}

export function PackSlot({ index, flipKey, children }: { index: number; flipKey?: string; children: ReactNode }) {
  const { columns, cardCount } = useContext(PackShapeContext);
  const lastRowStart = Math.floor((cardCount - 1) / columns) * columns;
  const lastRowLength = cardCount - lastRowStart;
  const centeredStart = index === lastRowStart ? `${columns - lastRowLength + 1} / span 2` : "span 2";
  return (
    <div data-flip={flipKey} style={{ gridColumn: centeredStart }}>
      {children}
    </div>
  );
}

export function PulseCard({ index }: { index?: number }) {
  const delayMs = useWaveDelay(index ?? 0);
  return (
    <span
      className={cn("block", index != null && "animate-fadeIn")}
      style={index != null ? { animationDelay: `${delayMs}ms` } : undefined}
    >
      <span className={cn("block aspect-[488/680] animate-pulse bg-surface2", CARD_RADIUS)} />
    </span>
  );
}

export function PickingCard({
  card,
  pickNumber,
  dealDelayMs,
  opening,
  onToggle,
  onDragOut,
  onZoom,
}: {
  card: ArtifactCard;
  pickNumber: number | null;
  dealDelayMs?: number;
  opening?: CardOpening;
  onToggle: () => void;
  onDragOut: (event: ReactPointerEvent) => void;
  onZoom: () => void;
}) {
  const gesture = useCardGesture({ onTap: onToggle, onDragOut, onZoom });
  const picked = pickNumber != null;
  return (
    <div
      className={cn(dealDelayMs != null && "animate-cardDeal")}
      style={dealDelayMs != null ? { animationDelay: `${dealDelayMs}ms` } : undefined}
    >
      <button
        type="button"
        aria-pressed={picked}
        aria-label={picked ? `${card.n}, pick ${pickNumber}` : (card.n ?? "Card")}
        {...gesture}
        className={cn(
          "group relative block w-full touch-manipulation select-none [container-type:inline-size]",
          CARD_RADIUS,
          "top-0 transition-[top,box-shadow] duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
          "hover:-top-1 active:top-0",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white",
          "focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
          picked ? "shadow-[0_0_0_3px_#f6c95e,5px_6px_0_3px_#05070a]" : "hover:shadow-[0_12px_28px_rgba(0,0,0,0.6)]",
        )}
      >
        {opening ? <CrossfadeImage card={card} opening={opening} /> : <CardImage card={card} className={CARD_RADIUS} />}
        {picked && (
          <ChipRow>
            <ChipFrame key={pickNumber} className="animate-stamp">
              <span className={cn(CALL_CHIP, CALL_GOLD)}>{pickLabel(pickNumber - 1)}</span>
            </ChipFrame>
          </ChipRow>
        )}
      </button>
    </div>
  );
}

export type RevealLayout = "in-place" | "real-order";
export type RevealOutcome = "first" | "right" | "missed" | "neutral";

const CALL_CHIP = "flex items-center whitespace-nowrap px-[0.35em] pt-[0.18em] pb-[0.12em] font-display leading-none";
const BADGE_LAG_MS = 320;
const CALL_GOLD = "bg-[#f6c95e] text-[#1a120b]";
const RESULT_RING: Record<RevealOutcome, string> = {
  first: "shadow-[0_0_0_1px_#2ee85c,2px_2px_0_1px_#05070a]",
  right: "shadow-[0_0_0_1px_#2ee85c,2px_2px_0_1px_#05070a]",
  missed: "shadow-[0_0_0_1px_#ef4444,2px_2px_0_1px_#05070a]",
  neutral: "shadow-[0_0_0_1px_#5b6b85,2px_2px_0_1px_#05070a]",
};
const CALL_FILL: Record<RevealOutcome, string> = {
  first: "bg-green text-[#0b1a10]",
  right: "bg-green text-[#0b1a10]",
  missed: "bg-[#2b3445] text-[#ff7a7a]",
  neutral: "bg-[#2b3445] text-text",
};

export function useRevealLayout(): RevealLayout {
  return new URLSearchParams(window.location.search).get("option")?.toLowerCase() === "b" ? "real-order" : "in-place";
}

export function RevealCard({
  pack,
  card,
  slots,
  animate,
  showDrafter,
}: {
  pack: WheelPack;
  card: number;
  slots: number[];
  showDrafter: boolean;
  animate: boolean;
}) {
  const realIndex = pack.order.findIndex((pick) => pick.card === card);
  const pick = realIndex >= 0 ? pack.order[realIndex] : null;
  const yourIndex = slots.indexOf(card);
  const outcome = revealOutcome(realIndex, yourIndex);
  const delay = pick ? pickRevealDelay(realIndex, animate) : wheelRevealDelay(pack.order.length, animate);
  const delayStyle = { animationDelay: `${delay}ms` };
  return (
    <div>
      <div
        className={cn(
          "relative [container-type:inline-size]",
          CARD_RADIUS,
          animate && outcome === "missed" && "animate-missShake",
        )}
        style={delayStyle}
      >
        <CardImage card={pack.cards[card]} className={CARD_RADIUS} />
        {animate && (
          <span
            className={cn("pointer-events-none absolute inset-0 bg-black animate-revealSpotlight", CARD_RADIUS)}
            style={delayStyle}
          />
        )}
        <CallChip yourIndex={yourIndex} realIndex={realIndex} outcome={outcome} style={delayStyle} still={!animate} />
        {showDrafter && pick && (
          <span className="absolute inset-x-[5%] bottom-[4%] flex justify-center animate-fadeUpIn" style={delayStyle}>
            <span
              className={cn(
                "flex max-w-full items-center gap-1.5 border-2 border-[#1a120b] bg-[#16110c] px-2 py-1",
                "text-[13px] font-semibold shadow-[3px_3px_0_#05070a]",
              )}
            >
              {pick.deckColors && <Pips colors={pick.deckColors} size={13} />}
              <span className="truncate">{pick.drafter}</span>
              {pick.trophy && (
                <span title="Won the Pod" className="shrink-0">
                  <Trophy size={13} color="#ffc63a" />
                </span>
              )}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}

export function QuickRevealCard({
  card,
  realIndex,
  guessed,
}: {
  card: ArtifactCard;
  realIndex: number;
  guessed: boolean;
}) {
  const wheeled = realIndex < 0;
  const outcome = revealOutcome(realIndex, -1);
  const unguessedFill = wheeled ? CALL_FILL.right : CALL_FILL.neutral;
  return (
    <div
      className={cn(
        "relative [container-type:inline-size]",
        CARD_RADIUS,
        guessed && outcome === "missed" && "animate-missShake",
        !guessed && !wheeled && "opacity-70",
      )}
    >
      <CardImage card={card} className={CARD_RADIUS} />
      {guessed ? (
        <CallChip yourIndex={-1} realIndex={realIndex} outcome={outcome} style={{}} />
      ) : (
        <ChipRow>
          <ChipFrame className={cn("animate-stamp", RESULT_RING[wheeled ? "right" : "neutral"])}>
            <span className={cn(CALL_CHIP, unguessedFill)}>
              {wheeled ? <WordLabel>Wheeled</WordLabel> : pickLabel(realIndex)}
            </span>
          </ChipFrame>
        </ChipRow>
      )}
    </div>
  );
}

function CallChip(props: {
  yourIndex: number;
  realIndex: number;
  outcome: RevealOutcome;
  style: CSSProperties;
  still?: boolean;
}) {
  return (
    <ChipRow>
      <CallChipFace {...props} />
    </ChipRow>
  );
}

export function CallChipFace({
  yourIndex,
  realIndex,
  outcome,
  style,
  still = false,
}: {
  yourIndex: number;
  realIndex: number;
  outcome: RevealOutcome;
  style?: CSSProperties;
  still?: boolean;
}) {
  const right = outcome === "first" || outcome === "right";
  const called = yourIndex >= 0;
  const motion = (className: string) => (still ? undefined : className);
  const badgeDelay = style?.animationDelay ? `calc(${style.animationDelay} + ${BADGE_LAG_MS}ms)` : `${BADGE_LAG_MS}ms`;
  return (
    <span className="relative flex">
      <ChipFrame
        className={cn(RESULT_RING[outcome], motion(called ? "animate-chipRingFromGold" : "animate-stamp"))}
        style={style}
      >
        <span
          className={cn(
            CALL_CHIP,
            "gap-[0.18em]",
            right ? CALL_FILL.right : CALL_FILL.neutral,
            called && motion("animate-chipFillFromGold"),
          )}
          style={style}
        >
          {called ? pickLabel(yourIndex) : <WordLabel>Wheel</WordLabel>}
          {right && (
            <Check className={cn("-mt-[0.1em] size-[0.9em]", motion("animate-stamp"))} strokeWidth={4} style={style} />
          )}
        </span>
        {!right && (
          <span className={cn("flex items-stretch overflow-hidden", motion("animate-chipExtend"))} style={style}>
            <span className="grid place-items-center bg-[#1a120b] px-[0.12em] text-[#f6c95e]">
              <ArrowRight className="size-[0.8em]" strokeWidth={3} />
            </span>
            <span className={cn(CALL_CHIP, CALL_FILL[outcome])}>
              {realIndex < 0 ? <WordLabel>Wheeled</WordLabel> : pickLabel(realIndex)}
            </span>
          </span>
        )}
      </ChipFrame>
      {outcome === "first" && (
        <span
          className={cn(
            "absolute -top-[1em] -right-[0.75em] border-2 border-[#1a120b] bg-[#f6c95e] px-[0.28em] pt-[0.12em]",
            "font-display text-[0.82em] leading-none text-[#1a120b] shadow-[2px_2px_0_#05070a]",
            !still && "animate-badgePop",
          )}
          style={still ? undefined : { animationDelay: badgeDelay }}
        >
          +{FIRST_PICK_POINTS}
        </span>
      )}
    </span>
  );
}

function ChipRow({ children }: { children: ReactNode }) {
  return (
    <span
      className={cn(
        "pointer-events-none absolute inset-x-[4%] bottom-[45.5%] flex justify-center",
        "text-[max(12px,8.5cqw)]",
      )}
    >
      {children}
    </span>
  );
}

function ChipFrame({ className, style, children }: { className?: string; style?: CSSProperties; children: ReactNode }) {
  return (
    <span
      className={cn(
        "flex shrink-0 items-stretch border-[3px] border-[#1a120b]",
        "shadow-[0_0_0_1px_#f6c95e,2px_2px_0_1px_#05070a]",
        className,
      )}
      style={style}
    >
      {children}
    </span>
  );
}

function WordLabel({ children }: { children: ReactNode }) {
  return <span className="relative left-[0.07em]">{children}</span>;
}

function pickLabel(index: number): ReactNode {
  return <PickText pick={index + 1} />;
}

export function PickText({ pick }: { pick: number }) {
  return (
    <span>
      {pick}
      <span className={SUFFIX}>{ordinalSuffix(pick)}</span>
      {pick === 1 && "\u00a0Pick"}
    </span>
  );
}

export function ResultChip({
  yourIndex,
  outcome,
  className,
  style,
}: {
  yourIndex: number;
  outcome: RevealOutcome;
  className?: string;
  style?: CSSProperties;
}) {
  const fill = CALL_FILL[outcome];
  return (
    <span className={cn("flex border-2 border-[#1a120b]", RESULT_RING[outcome], className)} style={style}>
      <span
        className={cn(
          "flex-1 px-1 pt-1 pb-0.5 text-center font-display leading-none",
          "[@media(max-height:760px)]:lg:pt-0.5 [@media(max-height:760px)]:lg:pb-0",
          fill,
        )}
      >
        {yourIndex >= 0 ? ordinal(yourIndex + 1) : <WordLabel>Wheel</WordLabel>}
      </span>
    </span>
  );
}

const SUFFIX = "text-[0.72em]";

export function revealOutcome(realIndex: number, yourIndex: number): RevealOutcome {
  const wheeled = realIndex < 0;
  const leftOut = yourIndex < 0;
  if (realIndex === 0 && yourIndex === 0) {
    return "first";
  }
  if ((wheeled && leftOut) || realIndex === yourIndex) {
    return "right";
  }
  if (wheeled !== leftOut || realIndex === 0 || yourIndex === 0) {
    return "missed";
  }
  return "neutral";
}

export interface CardOpening {
  index: number;
  openedAt: number;
  underlay: ArtifactCard | "skeleton" | "empty";
}

export function CrossfadeImage({ card, opening }: { card: ArtifactCard; opening: CardOpening }) {
  const [loadedAt, setLoadedAt] = useState<number | null>(null);
  const revealAt = opening.openedAt + useWaveDelay(opening.index);
  const waitMs = loadedAt == null ? 0 : Math.max(0, revealAt - loadedAt);
  return (
    <div className="relative">
      <OpeningUnderlay underlay={opening.underlay} />
      <div
        className={cn("absolute inset-0 transition-opacity duration-300 ease-out", loadedAt == null && "opacity-0")}
        style={{ transitionDelay: `${waitMs}ms` }}
      >
        <CardImage card={card} className={CARD_RADIUS} onLoad={() => setLoadedAt(performance.now())} />
      </div>
    </div>
  );
}

function OpeningUnderlay({ underlay }: { underlay: CardOpening["underlay"] }) {
  if (underlay === "skeleton") {
    return <PulseCard />;
  }
  if (underlay === "empty") {
    return <span className="block aspect-[488/680]" />;
  }
  return <CardImage card={underlay} className={CARD_RADIUS} />;
}

function useWaveDelay(index: number): number {
  const { waveSteps } = useContext(PackShapeContext);
  return (waveSteps[index] ?? index) * WAVE_STEP_MS;
}

function snakeWaveSteps(columns: number, cardCount: number): number[] {
  const steps: number[] = [];
  for (let index = 0; index < cardCount; index++) {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const rowLength = Math.min(columns, cardCount - row * columns);
    const stepInRow = row % 2 === 0 ? column : rowLength - 1 - column;
    steps.push(row * columns + stepInRow);
  }
  return steps;
}

function smallScreenColumns(): number {
  return window.matchMedia("(min-width: 640px)").matches ? 5 : 3;
}

function usePackFit(ref: RefObject<HTMLDivElement>, cardCount: number): PackFit {
  const [fit, setFit] = useState<PackFit>(() => ({ columns: smallScreenColumns(), width: null }));
  useLayoutEffect(() => {
    const layout = ref.current?.parentElement;
    if (!layout) {
      return;
    }
    const measure = () => {
      if (window.innerWidth < 1024) {
        setFit({ columns: smallScreenColumns(), width: null });
        return;
      }
      const width = layout.clientWidth - SIDEBAR_MIN_PX - LAYOUT_GAP_PX;
      const height = window.innerHeight - CHROME_HEIGHT_PX;
      setFit(bestPackFit(cardCount, width, height));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(layout);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [ref, cardCount]);
  return fit;
}

function bestPackFit(cardCount: number, width: number, height: number): PackFit {
  let best: PackFit = { columns: 5, width: 0 };
  let bestCard = 0;
  for (let columns = 3; columns <= 8; columns++) {
    const rows = Math.ceil(cardCount / columns);
    const byWidth = (width - (columns - 1) * CARD_GAP_PX) / columns;
    const byHeight = ((height - (rows - 1) * CARD_GAP_PX) / rows) * CARD_ASPECT;
    const card = Math.floor(Math.min(byWidth, byHeight));
    if (card > bestCard) {
      bestCard = card;
      best = { columns, width: columns * card + (columns - 1) * CARD_GAP_PX };
    }
  }
  return best;
}

export function CardZoom({ card, onClose }: { card: ArtifactCard | null; onClose: () => void }) {
  useEffect(() => {
    if (!card) {
      return;
    }
    const close = () => onClose();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", close, true);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", close, true);
      window.removeEventListener("scroll", close, true);
    };
  }, [card, onClose]);
  if (!card) {
    return null;
  }
  return (
    <div className="pointer-events-none fixed inset-0 z-50 grid place-items-center bg-bg/60 animate-fadeIn">
      <div className="w-[min(80vw,46vh)] animate-dealIn drop-shadow-[0_20px_40px_rgba(0,0,0,0.7)]">
        <CardImage card={card} className={CARD_RADIUS} />
      </div>
    </div>
  );
}

function useCardGesture({
  onTap,
  onDragOut,
  onZoom,
}: {
  onTap: () => void;
  onDragOut: (event: ReactPointerEvent) => void;
  onZoom: () => void;
}) {
  const start = useRef<{ x: number; y: number } | null>(null);
  const pressTimer = useRef<number | null>(null);
  const suppressClick = useRef(false);

  const clearPress = () => {
    if (pressTimer.current != null) {
      window.clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
  };

  return {
    onPointerDown: (e: ReactPointerEvent) => {
      if (e.button !== 0) {
        return;
      }
      start.current = { x: e.clientX, y: e.clientY };
      suppressClick.current = false;
      if (e.pointerType !== "mouse") {
        pressTimer.current = window.setTimeout(() => {
          suppressClick.current = true;
          onZoom();
        }, LONG_PRESS_MS);
      }
    },
    onPointerMove: (e: ReactPointerEvent) => {
      if (!start.current) {
        return;
      }
      const moved = Math.hypot(e.clientX - start.current.x, e.clientY - start.current.y);
      if (moved < DRAG_THRESHOLD_PX) {
        return;
      }
      clearPress();
      if (e.pointerType === "mouse") {
        suppressClick.current = true;
        start.current = null;
        onDragOut(e);
      } else {
        start.current = null;
      }
    },
    onPointerUp: () => {
      clearPress();
      start.current = null;
    },
    onPointerCancel: () => {
      clearPress();
      start.current = null;
    },
    onClick: () => {
      if (suppressClick.current) {
        suppressClick.current = false;
        return;
      }
      onTap();
    },
    onContextMenu: (e: ReactMouseEvent) => {
      e.preventDefault();
      clearPress();
      onZoom();
    },
  };
}
