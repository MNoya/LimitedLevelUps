import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { ModalNavButton } from "./ModalNavButton";
import { Pips } from "./ManaPips";
import { CardImage, CardImageMapProvider, CardPreviewProvider, StackColumn } from "./pod/review/ReviewCard";
import { useCardImageMap } from "../data/cardImages";
import { skeletonLayout, type Skeleton } from "../data/skeletons";
import { useIsMobile } from "../lib/use-is-mobile";
import { cn } from "../lib/utils";
import type { ArtifactCard } from "../types/leaderboard";

const CARD_WIDTH = 180;
const REVEAL = 31;
const MOBILE_REVEAL = 28;
const CARD_CLASS =
  "overflow-hidden rounded-[4.5%/3.2%] [outline-style:solid] outline-1 -outline-offset-1 outline-white/10 shadow-[0_-2px_6px_rgba(0,0,0,0.6)] transition-[outline-color] group-hover:outline-white/50 hover:outline-white/50";

export function SkeletonsModal({
  skeletons,
  setCode,
  onClose,
}: {
  skeletons: Skeleton[];
  setCode: string;
  onClose: () => void;
}) {
  const isMobile = useIsMobile();
  const [index, setIndex] = useState(0);
  const skeleton = skeletons[index];
  const images = useCardImageMap(
    skeletons.flatMap((s) => [...s.cards, ...s.splitCards].map((c) => ({ name: c.n, set: c.s }))),
  );

  const { columns, splitColumns } = skeletonLayout(skeleton);
  const hasSplit = skeleton.splitCards.length > 0;
  const step = (by: number) => () => setIndex((i) => (i + by + skeletons.length) % skeletons.length);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        // Stepping the pairs owns the arrows here; the default would scroll the panel under them
        e.preventDefault();
        const by = e.key === "ArrowLeft" ? -1 : 1;
        setIndex((i) => (i + by + skeletons.length) % skeletons.length);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, skeletons.length]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col items-center bg-black/80 backdrop-blur-sm animate-fadeIn px-[4px] md:px-6 pt-8 md:pt-10 pb-6 md:pb-8"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Archetype skeletons"
    >
      <CardImageMapProvider value={images}>
        <CardPreviewProvider setCode={setCode}>
          <div className="flex min-h-0 w-full max-w-[1400px] flex-1 flex-col">
            <div
              className="relative flex min-h-0 flex-1 flex-col border border-border bg-surface"
              onClick={(e) => e.stopPropagation()}
            >
              <header className="flex shrink-0 items-center gap-3 border-b border-border px-3 py-2.5 md:gap-4 md:px-4 md:py-3">
                <div className="flex flex-1 items-center justify-center gap-2 md:gap-3">
                  <Pips colors={skeleton.colors} size={isMobile ? 15 : 20} />
                  <span className="font-display text-[16px] leading-none tracking-[0.14em] text-text md:text-[24px]">
                    ARCHETYPE SKELETON
                  </span>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Close"
                  className="shrink-0 cursor-pointer border-0 bg-transparent p-1 text-muted transition-colors hover:text-text"
                >
                  <X size={18} />
                </button>
              </header>

              <div className="themed-scrollbar min-h-0 flex-1 overflow-auto py-4 md:py-5">
                <div className="mx-auto w-fit min-w-full px-2 md:px-4">
                  <ColumnGrid columns={columns} isMobile={isMobile} />
                  {hasSplit && (
                    <>
                      <div className="my-4 border-t border-border2 md:my-5" />
                      <ColumnGrid columns={splitColumns} isMobile={isMobile} />
                    </>
                  )}
                </div>
              </div>
            </div>

            <PairStepper
              skeletons={skeletons}
              index={index}
              showArrows={!isMobile}
              onPick={setIndex}
              onPrev={step(-1)}
              onNext={step(1)}
            />
          </div>
        </CardPreviewProvider>
      </CardImageMapProvider>
    </div>,
    document.body,
  );
}

function ColumnGrid({ columns, isMobile }: { columns: ArtifactCard[][]; isMobile: boolean }) {
  if (isMobile) {
    const filled = columns.filter((column) => column.length > 0);
    return (
      <div className="grid grid-cols-2 items-start gap-x-2 gap-y-5">
        {filled.map((column, i) => (
          <SkeletonColumn key={i} cards={column} reveal={MOBILE_REVEAL} />
        ))}
      </div>
    );
  }
  return (
    <div
      className="mx-auto grid w-fit items-start gap-x-3"
      style={{ gridTemplateColumns: `repeat(${columns.length}, ${CARD_WIDTH}px)` }}
    >
      {columns.map((column, i) => (
        <SkeletonColumn key={i} cards={column} reveal={REVEAL} />
      ))}
    </div>
  );
}

function SkeletonColumn({ cards, reveal }: { cards: ArtifactCard[]; reveal: number }) {
  if (cards.length === 0) {
    return <div />;
  }
  return (
    <StackColumn
      count={cards.length}
      reveal={reveal}
      cardClassName={CARD_CLASS}
      cardAt={(i) => cards[i]}
      tapToPreview
      renderCard={(i) => <CardImage card={cards[i]} />}
    />
  );
}

function PairStepper({
  skeletons,
  index,
  showArrows,
  onPick,
  onPrev,
  onNext,
}: {
  skeletons: Skeleton[];
  index: number;
  showArrows: boolean;
  onPick: (index: number) => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div
      onClick={(e) => e.stopPropagation()}
      className="mt-4 flex w-full shrink-0 items-center gap-2 self-center rounded-2xl border border-border bg-surface px-2 py-2 shadow-lg md:mt-8 md:w-auto md:gap-3 md:px-3"
    >
      {showArrows && <ModalNavButton dir="prev" srLabel="Previous color pair" onClick={onPrev} />}
      <div className="flex min-w-0 flex-1 items-center justify-center gap-1.5 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden md:gap-2">
        {skeletons.map((skeleton, i) => (
          <button
            key={skeleton.colors}
            type="button"
            onClick={() => onPick(i)}
            aria-label={skeleton.colors}
            aria-current={i === index}
            className={cn(
              "flex h-9 flex-1 cursor-pointer items-center justify-center rounded-full border px-2 transition-colors md:h-10 md:flex-none md:shrink-0 md:px-3",
              i === index ? "border-green/50 bg-green/15" : "border-border bg-surface2 hover:border-border2",
            )}
          >
            <Pips colors={skeleton.colors} size={14} />
          </button>
        ))}
      </div>
      {showArrows && <ModalNavButton dir="next" srLabel="Next color pair" onClick={onNext} />}
    </div>
  );
}
