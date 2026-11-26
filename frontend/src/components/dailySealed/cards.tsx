import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, EyeOff, X } from "lucide-react";

import { cn } from "../../lib/utils";
import { CARD_FRAME_HOVER, stackedCardShadow } from "../pod/review/ReviewCard";
import { PileSymbol } from "./PileSymbol";
import { cardsFitPileKey } from "../../data/dailySealedLayout";
import { entryCount, type CardGroup, type PoolCard, type PoolEntry } from "../../data/dailySealed";

const CARD_RATIO = 680 / 488;
export const REVEAL_RATIO = 0.155;
const RATING_ROW_RATIO = 0.085;

export const stackReveal = (width: number, rated: boolean) =>
  Math.round(width * (REVEAL_RATIO + (rated ? RATING_ROW_RATIO : 0)));
const LONG_PRESS_MS = 450;

type RatingFor = (card: PoolCard) => number | null;

export interface CardActions {
  onPick: (entry: PoolEntry) => void;
  onHide?: (entry: PoolEntry) => void;
  onPreview: (entry: PoolEntry) => void;
  ratingFor?: RatingFor;
  ratingText?: (card: PoolCard) => string;
  dimmed?: (card: PoolCard) => boolean;
  marked?: (card: PoolCard) => boolean;
}

export const ColumnRow = ({
  groups,
  setCode,
  width,
  actions,
}: {
  groups: CardGroup[];
  setCode: string;
  width: number;
  actions: CardActions;
}) => (
  <div className="flex select-none items-start gap-2.5">
    {groups.map((group) => (
      <div key={group.key} className="flex flex-col gap-1.5" style={{ width }}>
        <ColumnHeader group={group} setCode={setCode} />
        <CardStack entries={group.entries} width={width} actions={actions} />
      </div>
    ))}
  </div>
);

const ColumnHeader = ({ group, setCode }: { group: CardGroup; setCode: string }) => (
  <div className="grid h-6 grid-cols-[1fr_auto_1fr] items-center rounded font-num text-[14px] text-text">
    {group.entries.length > 0 && (
      <>
        <span />
        <span>{entryCount(group.entries)}</span>
        <span className="flex pl-1.5">
          {cardsFitPileKey(group.key, group.entries.map((entry) => entry.card)) && (
            <PileSymbol pileKey={group.key} setCode={setCode} />
          )}
        </span>
      </>
    )}
  </div>
);

const CardStack = ({ entries, width, actions }: { entries: PoolEntry[]; width: number; actions: CardActions }) => {
  const cardHeight = Math.round(width * CARD_RATIO);
  const strips = entries.map((entry) => stackReveal(width, (actions.ratingFor?.(entry.card) ?? null) !== null));
  const tops = strips.map((_, i) => strips.slice(0, i).reduce((total, strip) => total + strip, 0));
  const height = entries.length === 0 ? stackReveal(width, false) * 2 : tops[tops.length - 1] + cardHeight;
  return (
    <div
      className={cn("relative", entries.length === 0 && "rounded border border-dashed border-border2")}
      style={{ width, height }}
    >
      {entries.map((entry, i) => (
        <StackedCard
          key={entry.index}
          entry={entry}
          top={tops[i]}
          z={i}
          width={width}
          height={cardHeight}
          actions={actions}
        />
      ))}
    </div>
  );
};

const StackedCard = ({
  entry,
  top,
  z,
  width,
  height,
  actions,
}: {
  entry: PoolEntry;
  top: number;
  z: number;
  width: number;
  height: number;
  actions: CardActions;
}) => {
  const rating = actions.ratingFor?.(entry.card) ?? null;
  return (
    <div
      className="group absolute left-0 cursor-pointer hover:z-30"
      style={{ top, width, zIndex: z }}
      onClick={() => actions.onPick(entry)}
      onContextMenu={(event) => {
        event.preventDefault();
        actions.onPreview(entry);
      }}
    >
      <CardFace card={entry.card} style={{ height }} className={stackedCardShadow(width)} />
      {entry.copies !== undefined && <CopiesBadge copies={entry.copies} cardWidth={width} />}
      {rating !== null && <RatingBadge value={rating} cardWidth={width} text={actions.ratingText?.(entry.card)} />}
      {actions.dimmed?.(entry.card) && <DimmedVeil />}
      {actions.marked?.(entry.card) && <MarkedFrame />}
      {actions.onHide && (
        <button
          type="button"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            actions.onHide?.(entry);
          }}
          aria-label={`Hide ${entry.card.name}`}
          title="Hide"
          className="absolute right-1 top-[16%] hidden rounded bg-bg/85 p-1 text-subtle group-hover:block hover:text-text"
        >
          <EyeOff size={13} />
        </button>
      )}
    </div>
  );
};

export const CardFace = ({ card, className, style }: { card: PoolCard; className?: string; style?: React.CSSProperties }) => (
  <img
    src={card.image}
    alt={card.name}
    draggable={false}
    loading="lazy"
    className={cn(
      "block w-full select-none bg-surface2 [-webkit-touch-callout:none]",
      CARD_FRAME_HOVER,
      className,
    )}
    style={style}
  />
);

export const CopiesBadge = ({ copies, cardWidth }: { copies: number; cardWidth: number }) =>
  copies > 1 ? (
    <span
      className="pointer-events-none absolute font-bold leading-none text-[rgb(230,230,230)]"
      style={{
        top: cardWidth * 0.052,
        right: cardWidth * 0.06,
        fontSize: cardWidth * 0.09,
        filter: [
          `drop-shadow(0 0 ${cardWidth * 0.01}px black)`,
          `drop-shadow(0 0 ${cardWidth * 0.01}px black)`,
          `drop-shadow(0 ${cardWidth * 0.007}px ${cardWidth * 0.017}px black)`,
        ].join(" "),
      }}
    >
      x{copies}
    </span>
  ) : null;

export const RatingBadge = ({ value, cardWidth, text }: { value: number; cardWidth?: number; text?: string }) => (
  <span
    className="pointer-events-none absolute rounded-br-md bg-black/80 px-1 font-num leading-tight text-text"
    style={{
      top: "calc(10.3% + 4px)",
      left: "calc(3.5% + 9px)",
      fontSize: cardWidth ? Math.max(10, Math.round(cardWidth * 0.065)) : 11,
    }}
  >
    {text ?? `${(value * 100).toFixed(1)}%`}
  </span>
);

export const DimmedVeil = () => (
  <span className="pointer-events-none absolute inset-0 rounded-[4.75%/3.5%] bg-bg/60 group-hover:hidden" />
);

export const MarkedFrame = () => (
  <span className="pointer-events-none absolute inset-0 rounded-[4.75%/3.5%] border-2 border-green" />
);

export const StripList = ({ entries, actions }: { entries: PoolEntry[]; actions: CardActions }) => (
  <section className="flex flex-col gap-[3px]">
    {entries.map((entry) => (
      <StripButton key={entry.index} entry={entry} actions={actions} />
    ))}
  </section>
);

const StripButton = ({ entry, actions }: { entry: PoolEntry; actions: CardActions }) => {
  const pressTimer = useRef<number | null>(null);
  const pressed = useRef(false);
  const rating = actions.ratingFor?.(entry.card) ?? null;
  const cancel = () => {
    if (pressTimer.current !== null) {
      window.clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
  };
  return (
    <button
      type="button"
      className={cn("relative block select-none [-webkit-touch-callout:none]", actions.dimmed?.(entry.card) && "opacity-40")}
      onPointerDown={() => {
        pressed.current = false;
        pressTimer.current = window.setTimeout(() => {
          pressed.current = true;
          actions.onPreview(entry);
        }, LONG_PRESS_MS);
      }}
      onPointerUp={cancel}
      onPointerLeave={cancel}
      onPointerCancel={cancel}
      onContextMenu={(event) => event.preventDefault()}
      onClick={() => {
        if (!pressed.current) {
          actions.onPick(entry);
        }
      }}
    >
      <TitleStrip card={entry.card} />
      {actions.marked?.(entry.card) && <span className="pointer-events-none absolute inset-0 rounded-[3.8%/40%] border-2 border-green" />}
      {rating !== null && (
        <span className="absolute right-[15%] top-1/2 -translate-y-1/2 rounded bg-bg/90 px-1.5 font-num text-[14px] leading-[20px] text-text">
          {actions.ratingText?.(entry.card) ?? (rating * 100).toFixed(1)}
        </span>
      )}
    </button>
  );
};

const TitleStrip = ({ card }: { card: PoolCard }) => (
  <div className="relative aspect-[432/42] w-full overflow-hidden rounded-[3.8%/40%] bg-surface2">
    <div className="absolute left-[-4.98%] top-0 w-[110.1%]">
      <img
        src={card.image}
        alt={card.name}
        loading="lazy"
        draggable={false}
        className="mt-[-6.28%] block aspect-[488/680] w-full"
      />
    </div>
  </div>
);

export interface CardStep {
  prev: (() => void) | null;
  next: (() => void) | null;
}

export const CardPreview = ({
  entry,
  onClose,
  step = null,
  children,
}: {
  entry: PoolEntry;
  onClose: () => void;
  step?: CardStep | null;
  children?: ReactNode;
}) => {
  const [showBack, setShowBack] = useState(false);
  useEffect(() => setShowBack(false), [entry.index]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
      if (event.key === "ArrowLeft") {
        step?.prev?.();
      }
      if (event.key === "ArrowRight") {
        step?.next?.();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, step]);
  const image = showBack && entry.card.back ? entry.card.back : entry.card.image;
  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex select-none items-center justify-center bg-black/75 p-4 [-webkit-touch-callout:none]"
      onClick={onClose}
      onContextMenu={(event) => event.preventDefault()}
    >
      <div
        className={cn("flex flex-col items-center gap-3", step ? "max-w-[460px]" : "max-w-[360px]")}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex w-full items-center gap-2">
          {step && <StepButton label="Previous" onClick={step.prev}><ChevronLeft size={20} /></StepButton>}
          <img
            src={image}
            alt={entry.card.name}
            draggable={false}
            className="pointer-events-none min-w-0 flex-1 rounded-[4.5%/3.2%] [-webkit-touch-callout:none]"
          />
          {step && <StepButton label="Next" onClick={step.next}><ChevronRight size={20} /></StepButton>}
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          {entry.card.back && (
            <button
              type="button"
              onClick={() => setShowBack((prev) => !prev)}
              className="h-10 rounded border border-border2 bg-surface px-3 text-[13px] text-subtle"
            >
              {showBack ? "Front face" : "Back face"}
            </button>
          )}
          {children}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-10 w-10 items-center justify-center rounded border border-border2 bg-surface text-subtle"
          >
            <X size={16} />
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
};

const StepButton = ({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: (() => void) | null;
  children: ReactNode;
}) => (
  <button
    type="button"
    aria-label={label}
    onClick={onClick ?? undefined}
    disabled={!onClick}
    className={cn(
      "flex h-12 w-10 shrink-0 items-center justify-center rounded border border-border2 bg-surface text-subtle",
      "transition-colors hover:border-white/40 hover:text-text disabled:opacity-30 disabled:hover:border-border2",
    )}
  >
    {children}
  </button>
);
