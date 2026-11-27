import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { DndContext, DragOverlay } from "@dnd-kit/core";

import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";
import { cardImageSources, useCardImageMap, type CardImages } from "../../data/cardImages";
import { EMPTY_BASICS, type PoolCard, type PoolEntry } from "../../data/dailySealed";
import type { DeckPool, Mainboard, MainboardCard } from "../../types/leaderboard";
import { CardPreview, PHONE_PILE_WIDTH, type CardActions } from "../dailySealed/cards";
import { fittedCardWidth } from "../dailySealed/cardWidth";
import { useWidth } from "../dailySealed/elementSize";
import { Pane } from "../dailySealed/panels";
import { PileDragGhost, usePileDrag } from "../dailySealed/pileDrag";
import { ListPanel, listPanelWidth, PileBoard } from "../dailySealed/piles";
import { PreviewButton } from "../dailySealed/shared";
import { useBuilder, type Builder, type BuildSeed } from "../dailySealed/useBuilder";

export const DeckPoolBoard = ({
  pool,
  warmedImages,
  onDeckChange,
  floatingAction,
  showGrid,
}: {
  pool: DeckPool;
  warmedImages?: CardImages;
  onDeckChange?: (mainPositions: number[]) => void;
  floatingAction?: ReactNode;
  showGrid: boolean;
}) => {
  const isMobile = useIsMobile();
  const editable = onDeckChange !== undefined;
  const imageItems = useMemo(
    () => (warmedImages ? [] : pool.cards.map((card) => ({ name: card.name, set: card.set ?? pool.set }))),
    [pool, warmedImages],
  );
  const ownImages = useCardImageMap(imageItems);
  const { cards, seed } = useDeckPool(pool, warmedImages ?? ownImages);
  const builder = useBuilder(cards, null, seed);
  const paneRef = useRef<HTMLDivElement>(null);
  const widestRow = Math.max(1, ...builder.layout.deck.map((row) => row.length));
  const paneWidth = useWidth(paneRef);
  const sideboardColumn = 1;
  const fittedWidth = isMobile ? PHONE_PILE_WIDTH : fittedCardWidth(paneWidth, widestRow + sideboardColumn);
  const { dragging, ghost, overZone, cardWidth, contextProps } = usePileDrag(builder, fittedWidth, isMobile);
  const sideWidth = listPanelWidth(cardWidth);
  const gridShown = showGrid || dragging !== null;
  const [preview, setPreview] = useState<PoolEntry | null>(null);

  const deckPositions = builder.deck.map((entry) => entry.index).sort((a, b) => a - b);
  const deckSignature = deckPositions.join(",");
  useEffect(() => {
    onDeckChange?.(deckPositions);
  }, [deckSignature]);

  const actions = cardActions(editable, isMobile, builder, setPreview);

  return (
    <DndContext {...contextProps}>
      <div ref={paneRef} className="flex h-full min-h-0 flex-col">
        <Pane
          zone="deck"
          className="min-h-0 flex-1"
          title={<h2 className="font-display text-[15px] tracking-[0.18em]">DECK</h2>}
          count={builder.deck.length}
          extra={
            <div
              className="-mr-3 flex h-10 items-center gap-2 border-l border-border pl-3"
              style={{ width: sideWidth }}
            >
              <h2 className="font-display text-[15px] tracking-[0.18em]">SIDEBOARD</h2>
              <span className="font-num text-[14px] text-subtle">{builder.hidden.length}</span>
            </div>
          }
          flush
        >
          <div className="relative flex min-h-0 min-w-0 flex-1">
            <div
              className={cn(
                "min-h-0 min-w-0 flex-1 overflow-auto px-2 py-2 transition-colors",
                overZone === "deck" && "bg-green/5",
              )}
              style={gridShown ? DOT_GRID : undefined}
            >
              <PileBoard
                zone="deck"
                setCode={pool.set ?? ""}
                rows={builder.layout.deck}
                cards={cards}
                width={cardWidth}
                visible={null}
                actions={actions}
                dragging={dragging}
                readOnly={!editable}
                headers={false}
              />
            </div>
            {floatingAction && <div className="absolute bottom-4 right-4 z-40">{floatingAction}</div>}
          </div>
          <div className="flex" style={gridShown ? DOT_GRID : undefined}>
            <ListPanel
              emptyText={editable ? "Drag cards here to sideboard them" : "No sideboard"}
              indexes={builder.hidden.map((entry) => entry.index)}
              cards={cards}
              width={sideWidth}
              cardWidth={cardWidth}
              actions={actions}
              dragging={dragging}
              hovered={overZone === "hidden"}
              draggable={editable}
              scrollbar={false}
            />
          </div>
        </Pane>
      </div>
      <DragOverlay dropAnimation={null}>
        {ghost && <PileDragGhost ghost={ghost} cards={cards} cardWidth={cardWidth} />}
      </DragOverlay>
      {preview && (
        <CardPreview entry={preview} onClose={() => setPreview(null)}>
          {editable && (
            <PreviewButton
              onClick={() => {
                moveAcross(builder, preview);
                setPreview(null);
              }}
            >
              {builder.zoneOf(preview.index) === "deck" ? "Move to Sideboard" : "Add to Deck"}
            </PreviewButton>
          )}
        </CardPreview>
      )}
    </DndContext>
  );
};

const DOT_GRID: React.CSSProperties = {
  backgroundImage: "radial-gradient(rgba(46, 232, 92, 0.35) 1.2px, transparent 1.2px)",
  backgroundSize: "18px 18px",
};

const cardActions = (
  editable: boolean,
  isMobile: boolean,
  builder: Builder,
  openPreview: (entry: PoolEntry) => void,
): CardActions => {
  if (!editable) {
    return { onPick: openPreview, onPreview: openPreview };
  }
  if (isMobile) {
    return { onPick: openPreview, onPreview: () => undefined };
  }
  return { onPick: (entry) => moveAcross(builder, entry), onPreview: openPreview };
};

const moveAcross = (builder: Builder, entry: PoolEntry) =>
  builder.move([entry.index], builder.zoneOf(entry.index) === "deck" ? "hidden" : "deck");

const useDeckPool = (pool: DeckPool, imageMap: CardImages): { cards: PoolCard[]; seed: BuildSeed } => {
  const cards = useMemo(() => pool.cards.map((card) => toPoolCard(card, pool.set, imageMap)), [pool, imageMap]);
  const seed = useMemo(() => {
    const inMain = new Set(pool.main);
    const byManaThenName = (a: number, b: number) =>
      (pool.cards[a].cmc ?? 0) - (pool.cards[b].cmc ?? 0) || pool.cards[a].name.localeCompare(pool.cards[b].name);
    const hidden = pool.cards.map((_, position) => position).filter((position) => !inMain.has(position));
    return { main: pool.main, hidden: hidden.sort(byManaThenName), basics: EMPTY_BASICS };
  }, [pool]);
  return { cards, seed };
};

export const poolFromMainboard = (mainboard: Mainboard): DeckPool => {
  const main = expandCopies(mainboard.cards);
  const cards = [...main, ...expandCopies(mainboard.sideboard)];
  return { set: mainboard.set, cards, main: main.map((_, position) => position) };
};

const expandCopies = (cards: MainboardCard[]) =>
  cards.flatMap((card) => Array.from({ length: card.count ?? 1 }, () => card));

const toPoolCard = (card: MainboardCard, deckSet: string | null, imageMap: CardImages): PoolCard => ({
  name: card.name,
  cmc: card.cmc ?? 0,
  identity: (card.colors ?? []).join(""),
  cost: "",
  image: cardImageSources(card.name, card.set ?? deckSet, imageMap)[0] ?? "",
  back: null,
  rarity: "",
  types: (card.type ?? "").split(/\s+/).filter(Boolean),
});
