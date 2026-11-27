import { useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";
import { useDraggable } from "@dnd-kit/core";
import { EyeOff } from "lucide-react";

import { prefersReducedMotion } from "../../lib/reduced-motion";
import { cn } from "../../lib/utils";
import { entryCount, type PoolCard, type PoolEntry } from "../../data/dailySealed";
import { cardsFitPileKey, type Pile, type PileZone, type Row } from "../../data/dailySealedLayout";
import { CARD_RATIO, CardFace, CopiesBadge, DimmedVeil, RatingBadge, stackReveal, type CardActions } from "./cards";
import { MARK_BLOCK_CLASS } from "./markStyle";
import { stackedCardShadow } from "../pod/review/ReviewCard";
import { PileSymbol } from "./PileSymbol";
import { chipClass, SURFACE_BUTTON } from "../pod/review/reviewControls";
import { useWidth } from "./elementSize";
import { CARD_INDEX_ATTR, DROP_ZONE_ATTR, PILE_ATTR, PILE_CARDS_ATTR, PILE_ROW_ATTR } from "./pileHitTest";

export const PILE_GAP = 6;
const GLIDE_MS = 150;

export const PileBoard = ({
  zone,
  setCode,
  rows,
  cards,
  width,
  visible,
  actions,
  dragging,
  draggingLands = false,
  basics = null,
  readOnly = false,
  headers = true,
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
  draggingLands?: boolean;
  basics?: { row: number; pileKey: string; entries: PoolEntry[]; at: number } | null;
  readOnly?: boolean;
  headers?: boolean;
  pileHeader?: (pile: Pile, row: number) => ReactNode;
  dividerBefore?: string;
}) => {
  const isBasicsPile = (rowIndex: number, pileKey: string) =>
    !!basics && basics.row === rowIndex && basics.pileKey === pileKey;
  const basicsFor = (rowIndex: number, pileKey: string) =>
    basics && isBasicsPile(rowIndex, pileKey) ? basics.entries : [];
  const needsBasicsColumn = (rowIndex: number) =>
    !!basics &&
    basics.entries.length > 0 &&
    basics.row === rowIndex &&
    !rows[rowIndex]?.some((pile) => pile.key === basics.pileKey);
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
        faded={draggingLands}
      />
    );
  return (
    <div className="flex select-none flex-col gap-3">
      {rows.map((row, rowIndex) => (
        <div key={rowIndex} {...{ [PILE_ROW_ATTR]: rowIndex }} className="flex flex-col gap-1">
          <div className="flex min-h-12 items-start" style={{ gap: PILE_GAP }}>
            {row.map((pile, pileIndex) => [
              pile.key === dividerBefore && <NoncreatureDivider key="divider" />,
              needsBasicsColumn(rowIndex) && basics?.at === pileIndex && (
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
                landsPile={isBasicsPile(rowIndex, pile.key)}
                faded={draggingLands && isBasicsPile(rowIndex, pile.key)}
                headed={headers}
                header={pileHeader?.(pile, rowIndex)}
              />,
            ])}
            {needsBasicsColumn(rowIndex) && basics && basics.at >= row.length && basicsColumn(rowIndex)}
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
  landsPile = false,
  faded = false,
  headed = true,
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
  landsPile?: boolean;
  faded?: boolean;
  headed?: boolean;
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
      {!headed ? null : header !== undefined ? (
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
          landsPile={landsPile}
          showSymbol={cardsFitPileKey(pile.key, pileCards)}
          draggable={draggable && shown.length + basics.length > 0}
        />
      )}
      <div
        ref={cardsRef}
        {...{ [PILE_CARDS_ATTR]: "", "data-reveal": reveal }}
        className={cn("relative", faded && "opacity-30")}
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
  landsPile,
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
  landsPile: boolean;
  showSymbol: boolean;
  draggable: boolean;
}) => {
  const count = indexes.length + extraCount;
  const { attributes, listeners, setNodeRef } = useDraggable({
    id: `pilehead|${zone}|${row}|${pileIndex}`,
    data: {
      indexes,
      pileHeader: true,
      basics: pileIndex === -1,
      landsPile: landsPile ? { row, pile: pileIndex } : null,
    },
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
      <CardFace
        card={entry.card}
        style={{ height: cardHeight }}
        className={stackedCardShadow(cardHeight / CARD_RATIO)}
      />
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
      className={cn("relative cursor-pointer", !dragActive && "group hover:z-30", faded && "opacity-30")}
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

const LIST_PADDING = 8;

export const listPanelWidth = (cardWidth: number) => cardWidth + LIST_PADDING * 2 + 1;

export const ListPanel = ({
  title,
  emptyText,
  indexes,
  cards,
  width,
  cardWidth,
  actions,
  dragging,
  hovered,
  draggable = true,
  scrollbar = true,
  onClear,
  onResize,
}: {
  title?: string;
  emptyText: string;
  indexes: number[];
  cards: PoolCard[];
  width: number;
  cardWidth: number;
  actions: CardActions;
  dragging: number[] | null;
  hovered: boolean;
  draggable?: boolean;
  scrollbar?: boolean;
  onClear?: () => void;
  onResize?: (width: number) => void;
}) => {
  const listRef = useRef<HTMLDivElement>(null);
  const listWidth = useWidth(listRef);
  const pileWidth = Math.max(0, Math.min(cardWidth, (listWidth || width) - LIST_PADDING * 2));
  const cardsRef = useRef<HTMLDivElement>(null);
  useGlide(cardsRef, dragging !== null);
  const reveal = stackReveal(pileWidth, false);
  const stripOf = (index: number) => stackReveal(pileWidth, (actions.ratingFor?.(cards[index]) ?? null) !== null);
  const cardHeight = Math.round(pileWidth * CARD_RATIO);
  return (
    <div
      className={cn(
        "relative flex shrink-0 transition-colors",
        !onResize && "border-l border-border",
        hovered && "bg-green/5",
      )}
      style={{ width }}
    >
      {onResize && <ResizeHandle title={title ?? "list"} width={width} onResize={onResize} />}
      <div {...{ [DROP_ZONE_ATTR]: "hidden" }} className="flex min-w-0 flex-1 flex-col">
        {title && (
          <div className="flex h-9 shrink-0 items-center gap-2 px-2">
            <span className="font-display text-[14px] tracking-[0.18em] text-subtle">{title}</span>
            <span className="font-num text-[14px] text-subtle">{indexes.length}</span>
            {onClear && indexes.length > 0 && (
              <button type="button" onClick={onClear} className={cn(SURFACE_BUTTON, "ml-auto h-7 px-2")}>
                Clear
              </button>
            )}
          </div>
        )}
        <div
          ref={listRef}
          className={cn(
            "min-h-0 flex-1 overflow-y-auto overflow-x-hidden pb-2",
            !scrollbar && "no-scrollbar",
            !title && "pt-2",
          )}
          style={{ paddingInline: LIST_PADDING }}
        >
          <div
            ref={cardsRef}
            {...{ [PILE_CARDS_ATTR]: "", "data-reveal": reveal }}
            style={{ width: pileWidth, minHeight: cardHeight }}
            className={cn("relative", indexes.length === 0 && "rounded border border-dashed border-border2")}
          >
            {indexes.length === 0 && (
              <div
                className="flex items-center justify-center px-2 text-center text-[12px] text-subtle"
                style={{ height: cardHeight }}
              >
                {emptyText}
              </div>
            )}
            {indexes.map((index, position) => (
              <PiledCard
                key={index}
                entry={{ index, card: cards[index] }}
                height={position === indexes.length - 1 ? cardHeight : stripOf(index)}
                strip={stripOf(index)}
                cardHeight={cardHeight}
                actions={actions}
                draggable={draggable}
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

const ResizeHandle = ({
  title,
  width,
  onResize,
}: {
  title: string;
  width: number;
  onResize: (width: number) => void;
}) => {
  const startResize = (event: React.PointerEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const onMove = (move: PointerEvent) => onResize(width + startX - move.clientX);
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };
  return (
    <div
      onPointerDown={startResize}
      role="separator"
      aria-orientation="vertical"
      className="w-1.5 shrink-0 cursor-col-resize touch-none border-l border-border hover:bg-green/40"
      aria-label={`Resize the ${title} panel`}
    />
  );
};

const useGlide = (container: RefObject<HTMLDivElement | null>, active: boolean) => {
  const tops = useRef(new Map<string, number>());
  useLayoutEffect(() => {
    const list = container.current;
    if (!list) {
      return;
    }
    const still = prefersReducedMotion();
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

const markedRuns = (
  indexes: number[],
  isMarked: (index: number) => boolean,
  heightAt: (position: number) => number,
) => {
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
