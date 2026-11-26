import { useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";
import { useDraggable } from "@dnd-kit/core";
import { EyeOff } from "lucide-react";

import { cn } from "../../lib/utils";
import { entryCount, type PoolCard, type PoolEntry } from "../../data/dailySealed";
import { cardsFitPileKey, type Pile, type PileZone, type Row } from "../../data/dailySealedLayout";
import { CardFace, CopiesBadge, DimmedVeil, RatingBadge, stackReveal, type CardActions } from "./cards";
import { MARK_BLOCK_CLASS } from "./markStyle";
import { stackedCardShadow } from "../pod/review/ReviewCard";
import { PileSymbol } from "./PileSymbol";
import { chipClass, SURFACE_BUTTON } from "../pod/review/reviewControls";
import { CARD_INDEX_ATTR, DROP_ZONE_ATTR, PILE_ATTR, PILE_CARDS_ATTR, PILE_ROW_ATTR } from "./pileHitTest";

export const PILE_GAP = 6;
const GLIDE_MS = 150;
const CARD_RATIO = 680 / 488;

export const PileBoard = ({
  zone,
  setCode,
  rows,
  cards,
  width,
  visible,
  actions,
  dragging,
  basics = null,
  readOnly = false,
  pileHeader,
  dividerBefore,
}: {
  zone: PileZone;
  setCode: string;
  rows: Row[];
  cards: PoolCard[];
  width: number;
  visible: Set<number> | null;
  actions: CardActions;
  dragging: number[] | null;
  basics?: { row: number; pileKey: string; entries: PoolEntry[]; trailing?: boolean; before?: number } | null;
  readOnly?: boolean;
  pileHeader?: (pile: Pile, row: number) => ReactNode;
  dividerBefore?: string;
}) => {
  const basicsFor = (rowIndex: number, pileKey: string) =>
    basics && basics.row === rowIndex && basics.pileKey === pileKey ? basics.entries : [];
  const needsBasicsColumn = (rowIndex: number) =>
    !!basics && basics.entries.length > 0 && basics.row === rowIndex && !rows[rowIndex]?.some((pile) => pile.key === basics.pileKey);
  const basicsColumn = (rowIndex: number) =>
    basics && (
      <PileColumn
        zone={zone}
        setCode={setCode}
        row={rowIndex}
        pileIndex={null}
        pile={{ key: "land", label: "land", cards: [] }}
        cards={cards}
        width={width}
        visible={visible}
        actions={actions}
        dragging={dragging}
        draggable={!readOnly}
        basics={basics.entries}
      />
    );
  return (
    <div className="flex select-none flex-col gap-3">
      {rows.map((row, rowIndex) => (
        <div key={rowIndex} {...{ [PILE_ROW_ATTR]: rowIndex }} className="flex flex-col gap-1">
          <div className="flex min-h-12 items-start" style={{ gap: PILE_GAP }}>
            {needsBasicsColumn(rowIndex) && basics && basics.before === undefined && !basics.trailing && basicsColumn(rowIndex)}
            {row.map((pile, pileIndex) => [
              pile.key === dividerBefore && <NoncreatureDivider key="divider" />,
              needsBasicsColumn(rowIndex) && basics?.before === pileIndex && (
                <span key="basics" className="contents">
                  {basicsColumn(rowIndex)}
                </span>
              ),
              <PileColumn
                key={`${pile.key}-${pileIndex}`}
                zone={zone}
                setCode={setCode}
                row={rowIndex}
                pileIndex={pileIndex}
                pile={pile}
                cards={cards}
                width={width}
                visible={visible}
                actions={actions}
                dragging={dragging}
                draggable={!readOnly}
                basics={basicsFor(rowIndex, pile.key)}
                header={pileHeader?.(pile, rowIndex)}
              />,
            ])}
            {needsBasicsColumn(rowIndex) &&
              basics &&
              (basics.before !== undefined ? basics.before >= row.length : basics.trailing) &&
              basicsColumn(rowIndex)}
          </div>
        </div>
      ))}
    </div>
  );
};

const NoncreatureDivider = () => (
  <div className="flex shrink-0 self-stretch px-2">
    <span className="w-px flex-1 bg-border2" />
  </div>
);

const PileColumn = ({
  zone,
  setCode,
  row,
  pileIndex,
  pile,
  cards,
  width,
  visible,
  actions,
  dragging,
  draggable,
  basics,
  header,
}: {
  zone: PileZone;
  setCode: string;
  row: number;
  pileIndex: number | null;
  pile: Pile;
  cards: PoolCard[];
  width: number;
  visible: Set<number> | null;
  actions: CardActions;
  dragging: number[] | null;
  draggable: boolean;
  basics: PoolEntry[];
  header?: ReactNode;
}) => {
  const shown = visible ? pile.cards.filter((index) => visible.has(index)) : pile.cards;
  const pileCards = [...pile.cards.map((index) => cards[index]), ...basics.map((entry) => entry.card)];
  const cardsRef = useRef<HTMLDivElement>(null);
  useGlide(cardsRef, dragging !== null);
  const reveal = stackReveal(width, false);
  const stripOf = (index: number) => stackReveal(width, (actions.ratingFor?.(cards[index]) ?? null) !== null);
  const cardHeight = Math.round(width * CARD_RATIO);
  const heightAt = (position: number) =>
    position === shown.length + basics.length - 1 ? cardHeight : stripOf(shown[position]);
  return (
    <div
      {...(pileIndex === null ? {} : { [PILE_ATTR]: pileIndex })}
      className="flex shrink-0 flex-col gap-1"
      style={{ width }}
    >
      {header !== undefined ? (
        <div className="flex h-6 items-center justify-center">{header}</div>
      ) : (
      <PileHeader
        zone={zone}
        setCode={setCode}
        row={row}
        pileIndex={pileIndex ?? -1}
        pileKey={pile.key}
        indexes={shown}
        extraCount={entryCount(basics)}
        showSymbol={cardsFitPileKey(pile.key, pileCards)}
        draggable={draggable && (shown.length > 0 || (pileIndex === null && basics.length > 0))}
      />
      )}
      <div
        ref={cardsRef}
        {...{ [PILE_CARDS_ATTR]: "", "data-reveal": reveal }}
        className="relative"
        style={{ minHeight: reveal * 2 }}
      >
        {shown.map((index, position) => (
          <PiledCard
            key={index}
            entry={{ index, card: cards[index] }}
            height={heightAt(position)}
            strip={stripOf(index)}
            cardHeight={cardHeight}
            actions={actions}
            draggable={draggable}
            dragActive={dragging !== null}
            faded={dragging?.includes(index) ?? false}
          />
        ))}
        {actions.marked &&
          markedRuns(shown, (index) => actions.marked?.(cards[index]) ?? false, heightAt).map((run) => (
            <span
              key={run.top}
              className={cn("pointer-events-none absolute z-20", MARK_BLOCK_CLASS)}
              style={{ top: run.top, height: run.height + 2, borderRadius: width * 0.0475 }}
            />
          ))}
        {basics.map((entry, position) => (
          <BasicPiledCard
            key={entry.index}
            entry={entry}
            height={position === basics.length - 1 ? cardHeight : reveal}
            cardHeight={cardHeight}
            onRemove={actions.onPick}
            dragActive={dragging !== null}
          />
        ))}
      </div>
    </div>
  );
};

const PileHeader = ({
  zone,
  setCode,
  row,
  pileIndex,
  pileKey,
  indexes,
  extraCount = 0,
  showSymbol,
  draggable,
}: {
  zone: PileZone;
  setCode: string;
  row: number;
  pileIndex: number;
  pileKey: string;
  indexes: number[];
  extraCount?: number;
  showSymbol: boolean;
  draggable: boolean;
}) => {
  const count = indexes.length + extraCount;
  const { attributes, listeners, setNodeRef } = useDraggable({
    id: `pilehead|${zone}|${row}|${pileIndex}`,
    data: { indexes, basics: pileIndex === -1 },
    disabled: !draggable,
  });
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      title={draggable ? "Drag to move this pile" : undefined}
      className={cn(
        "grid h-6 grid-cols-[1fr_auto_1fr] items-center font-num text-[14px] text-text",
        draggable && "cursor-grab rounded hover:bg-surface2",
      )}
    >
      {count > 0 && (
        <>
          <span />
          <span>{count}</span>
          <span className="flex pl-1.5">{showSymbol && <PileSymbol pileKey={pileKey} setCode={setCode} />}</span>
        </>
      )}
    </div>
  );
};

const BasicPiledCard = ({
  entry,
  height,
  cardHeight,
  onRemove,
  dragActive,
}: {
  entry: PoolEntry;
  height: number;
  cardHeight: number;
  onRemove: (entry: PoolEntry) => void;
  dragActive: boolean;
}) => (
  <div
    className={cn("relative cursor-pointer", !dragActive && "group hover:z-30")}
    style={{ height }}
    onClick={() => onRemove(entry)}
  >
    <div className="pointer-events-none absolute inset-x-0 top-0" style={{ height: cardHeight }}>
      <CardFace card={entry.card} style={{ height: cardHeight }} className={stackedCardShadow(cardHeight / CARD_RATIO)} />
      {entry.copies !== undefined && <CopiesBadge copies={entry.copies} cardWidth={cardHeight / CARD_RATIO} />}
    </div>
  </div>
);

const PiledCard = ({
  entry,
  height,
  strip,
  cardHeight,
  actions,
  draggable,
  dragActive,
  faded,
}: {
  entry: PoolEntry;
  height: number;
  strip: number;
  cardHeight: number;
  actions: CardActions;
  draggable: boolean;
  dragActive: boolean;
  faded: boolean;
}) => {
  const drag = useDraggable({ id: `drag|${entry.index}`, data: { indexes: [entry.index] }, disabled: !draggable });
  const rating = actions.ratingFor?.(entry.card) ?? null;
  return (
    <div
      ref={drag.setNodeRef}
      {...drag.attributes}
      {...drag.listeners}
      {...{ [CARD_INDEX_ATTR]: entry.index, "data-strip": strip }}
      className={cn(
        "relative cursor-pointer",
        !dragActive && "group hover:z-30",
        faded && "opacity-30",
      )}
      style={{ height }}
      onClick={() => actions.onPick(entry)}
      onContextMenu={(event) => {
        event.preventDefault();
        actions.onPreview(entry);
      }}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0" style={{ height: cardHeight }}>
        <CardFace
          card={entry.card}
          style={{ height: cardHeight }}
          className={stackedCardShadow(cardHeight / CARD_RATIO)}
        />
        {rating !== null && (
          <RatingBadge value={rating} cardWidth={cardHeight / CARD_RATIO} text={actions.ratingText?.(entry.card)} />
        )}
        {actions.dimmed?.(entry.card) && <DimmedVeil />}
      </div>
    </div>
  );
};

export const HiddenToggle = ({
  count,
  open,
  onToggle,
  hovered,
}: {
  count: number;
  open: boolean;
  onToggle: () => void;
  hovered: boolean;
}) => (
  <button
    type="button"
    {...{ [DROP_ZONE_ATTR]: "hidden" }}
    onClick={onToggle}
    aria-pressed={open}
    title="Drag cards here to hide them"
    className={cn(
      "flex h-8 items-center gap-2 px-2.5 text-[12px] uppercase tracking-[0.12em]",
      chipClass(open),
      hovered && "border-green/60 bg-green/15 text-green",
    )}
  >
    <EyeOff size={14} />
    Hidden
    <span className="font-num text-[13px]">{count}</span>
  </button>
);

export const HiddenPanel = ({
  hidden,
  cards,
  width,
  cardWidth,
  actions,
  dragging,
  hovered,
  onClear,
  onResize,
}: {
  hidden: number[];
  cards: PoolCard[];
  width: number;
  cardWidth: number;
  actions: CardActions;
  dragging: number[] | null;
  hovered: boolean;
  onClear: () => void;
  onResize: (width: number) => void;
}) => {
  const pileWidth = Math.min(cardWidth, width - 16);
  const cardsRef = useRef<HTMLDivElement>(null);
  useGlide(cardsRef, dragging !== null);
  const reveal = stackReveal(pileWidth, false);
  const stripOf = (index: number) => stackReveal(pileWidth, (actions.ratingFor?.(cards[index]) ?? null) !== null);
  const cardHeight = Math.round(pileWidth * CARD_RATIO);
  const startResize = (event: React.PointerEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    const onMove = (move: PointerEvent) => onResize(startWidth + startX - move.clientX);
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };
  return (
    <div className="relative flex shrink-0" style={{ width }}>
      <div
        onPointerDown={startResize}
        role="separator"
        aria-orientation="vertical"
        className="w-1.5 shrink-0 cursor-col-resize touch-none border-l border-border hover:bg-green/40"
        aria-label="Resize the Hidden panel"
      />
      <div
        {...{ [DROP_ZONE_ATTR]: "hidden" }}
        className={cn("flex min-w-0 flex-1 flex-col transition-colors", hovered && "bg-green/5")}
      >
        <div className="flex h-9 shrink-0 items-center gap-2 px-2">
          <span className="font-display text-[14px] tracking-[0.18em] text-subtle">HIDDEN</span>
          <span className="font-num text-[14px] text-subtle">{hidden.length}</span>
          {hidden.length > 0 && (
            <button type="button" onClick={onClear} className={cn(SURFACE_BUTTON, "ml-auto h-7 px-2")}>
              Clear
            </button>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          <div
            ref={cardsRef}
            {...{ [PILE_CARDS_ATTR]: "", "data-reveal": reveal }}
            style={{ width: pileWidth, minHeight: cardHeight }}
            className={cn("relative", hidden.length === 0 && "rounded border border-dashed border-border2")}
          >
            {hidden.length === 0 && (
              <div
                className="flex items-center justify-center px-2 text-center text-[12px] text-subtle"
                style={{ height: cardHeight }}
              >
                Drag cards here to hide them
              </div>
            )}
            {hidden.map((index, position) => (
              <PiledCard
                key={index}
                entry={{ index, card: cards[index] }}
                height={position === hidden.length - 1 ? cardHeight : stripOf(index)}
                strip={stripOf(index)}
                cardHeight={cardHeight}
                actions={actions}
                draggable
                dragActive={dragging !== null}
                faded={dragging?.includes(index) ?? false}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const useGlide = (container: RefObject<HTMLDivElement | null>, active: boolean) => {
  const tops = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const list = container.current;
    if (!list) {
      return;
    }
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const next = new Map<string, number>();
    for (const card of list.querySelectorAll<HTMLElement>(`[${CARD_INDEX_ATTR}]`)) {
      const key = card.getAttribute(CARD_INDEX_ATTR) ?? "";
      const top = card.offsetTop;
      const before = tops.current.get(key);
      next.set(key, top);
      if (!active || still || before === undefined || before === top) {
        continue;
      }
      const from = before + currentShiftY(card) - top;
      for (const running of card.getAnimations()) {
        running.cancel();
      }
      card.animate([{ transform: `translateY(${from}px)` }, { transform: "translateY(0)" }], {
        duration: GLIDE_MS,
        easing: "ease-out",
      });
    }
    tops.current = next;
  });
};

const currentShiftY = (card: HTMLElement) => {
  const transform = getComputedStyle(card).transform;
  return transform === "none" ? 0 : new DOMMatrixReadOnly(transform).m42;
};

const markedRuns = (indexes: number[], isMarked: (index: number) => boolean, heightAt: (position: number) => number) => {
  const runs: { top: number; height: number }[] = [];
  let top = 0;
  let open: { top: number; height: number } | null = null;
  indexes.forEach((index, position) => {
    const height = heightAt(position);
    if (isMarked(index)) {
      if (open) {
        open.height += height;
      } else {
        open = { top, height };
        runs.push(open);
      }
    } else {
      open = null;
    }
    top += height;
  });
  return runs;
};
