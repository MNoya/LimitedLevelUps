import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { cn } from "../../../lib/utils";
import { cardImageSources, type CardImages } from "../../../data/cardImages";
import {
  resolveTierList,
  tierColor,
  TREND_COLOR,
  trendGlyphStack,
  useTierList,
  type TierCard,
} from "../../../data/tierList";
import type { ArtifactCard } from "../../../types/leaderboard";

// The draft's main set, a fallback for cards that carry no recorded set of their own (e.g. `soa`
// Mystical Archive within an SOS draft).
const ReviewSetContext = createContext<string | null>(null);
export const ReviewSetProvider = ReviewSetContext.Provider;

// The set image maps + ready flag, resolved in bulk by the viewer.
const CardImageMapContext = createContext<CardImages>({ images: new Map(), ready: false });
export const CardImageMapProvider = CardImageMapContext.Provider;
export const useCardImageMapContext = () => useContext(CardImageMapContext);

function useCardImageSources(card: ArtifactCard): string[] {
  const reviewSet = useContext(ReviewSetContext);
  const cardImages = useCardImageMapContext();
  const set = card.s ?? reviewSet;
  return useMemo(() => cardImageSources(card.n, set, cardImages), [card.n, set, cardImages]);
}

// Walk the src candidates: start at the first, and on load error advance to the next. Resetting when the
// candidate list changes re-tries from the top for a re-keyed card.
export function useFallbackImage(sources: string[]): { src: string | null; onError: () => void } {
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [sources]);
  return { src: sources[index] ?? null, onError: () => setIndex((i) => i + 1) };
}

export function CardImage({ card, className }: { card: ArtifactCard; className?: string }) {
  const openPreview = useContext(CardPreviewContext);
  const { src, onError } = useFallbackImage(useCardImageSources(card));
  const onContextMenu = openPreview
    ? (e: React.MouseEvent) => {
        e.preventDefault();
        openPreview(card);
      }
    : undefined;
  if (!src) {
    return <div onContextMenu={onContextMenu} className={cn("aspect-[488/680] bg-surface2", className)} />;
  }
  return (
    <img
      key={src}
      src={src}
      alt={card.n ?? ""}
      loading="lazy"
      draggable={false}
      onError={onError}
      onContextMenu={onContextMenu}
      className={cn("block aspect-[488/680] w-full object-cover", className)}
    />
  );
}

// A fanned column of overlapping cards where only a `reveal`-px sliver of each covered card shows.
// Hovering that sliver lifts the card to the front; the lifted card's body is click-through so it
// never traps the cursor over the cards beneath it — moving down the sliver strip walks the fan.
export function StackColumn({
  count,
  reveal,
  width,
  className,
  cardClassName,
  glowIndexes = [],
  cardAt,
  renderCard,
}: {
  count: number;
  reveal: number;
  width?: number;
  className?: string;
  cardClassName?: string;
  glowIndexes?: number[];
  cardAt?: (i: number) => ArtifactCard | undefined;
  renderCard: (i: number) => React.ReactNode;
}) {
  const openPreview = useContext(CardPreviewContext);
  const [raised, setRaised] = useState<number | null>(null);
  if (count <= 0) {
    return null;
  }
  const style = width != null ? { width } : undefined;
  const onContextMenu = (i: number) => (e: React.MouseEvent) => {
    const card = cardAt?.(i);
    if (card && openPreview) {
      e.preventDefault();
      openPreview(card);
    }
  };
  return (
    <div className={cn("relative [display:flow-root]", className)} style={style}>
      {Array.from({ length: count }, (_, i) => {
        const isLast = i === count - 1;
        const isGlow = glowIndexes.includes(i);
        const z = raised === i ? 30 : isGlow ? 10 : undefined;
        const hover = {
          onMouseEnter: () => setRaised(i),
          onMouseLeave: () => setRaised((r) => (r === i ? null : r)),
          onContextMenu: onContextMenu(i),
        };
        if (isLast) {
          return (
            <div
              key={i}
              className={cn("group relative", cardClassName, isGlow && "review-last-pick")}
              style={{ marginTop: (count - 1) * reveal, zIndex: z }}
              {...hover}
            >
              {renderCard(i)}
            </div>
          );
        }
        return (
          <div
            key={i}
            className="group absolute inset-x-0"
            style={{ top: i * reveal, height: reveal, zIndex: z }}
            {...hover}
          >
            <div className={cn("pointer-events-none absolute inset-x-0 top-0", cardClassName, isGlow && "review-last-pick")}>
              {renderCard(i)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Draftmancer-style right-click preview: right-clicking any review card slides a card image in from
// the right edge of the viewport, with the card's Limited grade if the set has a tier list.
const CardPreviewContext = createContext<((card: ArtifactCard) => void) | null>(null);

export function CardPreviewProvider({ setCode, children }: { setCode: string; children: React.ReactNode }) {
  const grades = useReviewGrades(setCode);
  const [preview, setPreview] = useState<ArtifactCard | null>(null);

  const openPreview = useMemo(() => (card: ArtifactCard) => setPreview(card), []);

  useEffect(() => {
    if (!preview) {
      return;
    }
    const close = () => setPreview(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
      }
    };
    const onPointerDown = (e: PointerEvent) => {
      if (e.button === 0) {
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointerDown, true);
    };
  }, [preview]);

  const grade = preview ? grades.get(normalizeCardName(preview.n)) : undefined;
  return (
    <CardPreviewContext.Provider value={openPreview}>
      {children}
      {preview && <CardPreviewOverlay card={preview} grade={grade} />}
    </CardPreviewContext.Provider>
  );
}

const normalizeCardName = (name: string | null | undefined) => (name ?? "").trim().toLowerCase();

function useReviewGrades(setCode: string): Map<string, TierCard> {
  const resolved = resolveTierList(setCode);
  const { data } = useTierList(resolved.effectiveUid, resolved.graders);
  return useMemo(() => {
    const byName = new Map<string, TierCard>();
    for (const card of data ?? []) {
      byName.set(normalizeCardName(card.name), card);
    }
    return byName;
  }, [data]);
}

function CardPreviewOverlay({ card, grade }: { card: ArtifactCard; grade: TierCard | undefined }) {
  const { src, onError } = useFallbackImage(useCardImageSources(card));
  return (
    <div className="pointer-events-none fixed right-10 top-1/2 z-[70] -translate-y-1/2">
      <div className="relative" style={{ animation: "card-preview-in-right 180ms ease-out" }}>
        {src ? (
          <img
            key={src}
            src={src}
            alt={card.n ?? ""}
            draggable={false}
            onError={onError}
            className="h-[54vh] max-h-[500px] w-auto rounded-[4.5%/3.2%] shadow-2xl outline outline-1 -outline-offset-1 outline-white/20"
          />
        ) : (
          <div className="flex h-[54vh] max-h-[500px] w-[39vh] max-w-[360px] items-center justify-center rounded-xl bg-surface2 p-6 shadow-2xl">
            <span className="font-body text-sm text-subtle">{card.n}</span>
          </div>
        )}
        {grade && <GradeBadge card={grade} />}
      </div>
    </div>
  );
}

function GradeBadge({ card }: { card: TierCard }) {
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
      <div className="flex items-center gap-2.5 rounded-lg bg-black/80 px-3 py-2 backdrop-blur-sm">
        <span className="flex flex-col text-[12px] font-semibold uppercase leading-none tracking-[0.1em] text-white">
          <span>Tier</span>
          <span>List</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="font-display text-[26px] leading-none" style={{ color: tierColor(card.tier) }}>
            {card.tier}
          </span>
          {card.trend && (
            <span className="flex flex-col items-center" style={{ color: TREND_COLOR[card.trend] }}>
              {trendGlyphStack(card).map((char, i, stack) => (
                <span key={i} className={cn("text-[11px] leading-none", i > 0 && "-mt-[5px]")} style={{ zIndex: stack.length - i }}>
                  {char}
                </span>
              ))}
            </span>
          )}
        </span>
      </div>
    </div>
  );
}
