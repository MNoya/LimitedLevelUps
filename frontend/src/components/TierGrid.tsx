import { createContext, Fragment, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { RefreshCw } from "./Icons";
import { GradeLabel } from "./TierGuide";
import { ModalNavButton } from "./ModalNavButton";
import { cn } from "../lib/utils";
import { isImageLoaded, markImageLoaded, preloadImage, useImageReveal } from "../lib/imageReveal";
import { TEXT_OUTLINE } from "../lib/text-styles";
import { useIsMobile } from "../lib/use-is-mobile";
import {
  cardFlags,
  columnOf,
  COLUMN_CODES,
  COLUMN_NAMES,
  hasActiveFilters,
  inclusionRank,
  isCardFilteredOut,
  tierColor,
  TIER_ORDER,
  TREND_COLOR,
  TREND_LABEL,
  trendGlyphStack,
  useTierList,
  type Grader,
  type TierCard,
  type TierFilters,
} from "../data/tierList";

const RARITY_ACCENT: Record<string, string> = {
  C: "#ffffff",
  U: "#707883",
  R: "#a58e4a",
  M: "#bf4427",
};

const COLUMN_MS: Record<string, string> = {
  W: "w",
  U: "u",
  B: "b",
  R: "r",
  G: "g",
  M: "multicolor",
  C: "c",
};

// Multicolor renders as mana-font's gold duotone glyph (no cost disc), matching untapped.gg.
export function columnPipClass(code: string): string {
  if (code === "M") return "ms ms-multicolor ms-duo ms-duo-color ms-grad";
  return `ms ms-cost ms-${COLUMN_MS[code]}`;
}

// When a set has no consensus list, the grid is built from grader lists alone: the popup
// compares each grader's grade instead of showing a single consensus grade.
const ComparisonContext = createContext(false);

export function TierGrid({
  uid,
  graders,
  comparison = false,
  filters,
  hideArt,
  stickyTop,
}: {
  uid: string;
  graders: Grader[];
  comparison?: boolean;
  filters: TierFilters;
  hideArt: boolean;
  stickyTop: number;
}) {
  const { data, isLoading, isError } = useTierList(uid, graders);
  const isMobile = useIsMobile();

  if (isLoading || !data) {
    if (isError) {
      return (
        <div className="border border-border bg-surface py-16 text-center text-muted text-[14px]">
          Couldn't load this tier list.
        </div>
      );
    }
    return <TierGridSkeleton isMobile={isMobile} stickyTop={stickyTop} />;
  }

  const byKey = new Map<string, TierCard[]>();
  for (const card of data) {
    const key = `${columnOf(card.color)}|${card.tier}`;
    const bucket = byKey.get(key);
    if (bucket) {
      bucket.push(card);
    } else {
      byKey.set(key, [card]);
    }
  }
  for (const bucket of byKey.values()) {
    bucket.sort((a, b) => {
      const ra = inclusionRank(a.inclusion_type);
      const rb = inclusionRank(b.inclusion_type);
      if (ra !== rb) return ra - rb;
      const sa = a.sort_key ?? Number.MAX_SAFE_INTEGER;
      const sb = b.sort_key ?? Number.MAX_SAFE_INTEGER;
      return sa - sb || a.name.localeCompare(b.name);
    });
  }

  return (
    <ComparisonContext.Provider value={comparison}>
      {isMobile ? (
        <MobileTiers byKey={byKey} filters={filters} hideArt={hideArt} />
      ) : (
        <DesktopGrid byKey={byKey} filters={filters} hideArt={hideArt} stickyTop={stickyTop} />
      )}
    </ComparisonContext.Provider>
  );
}

const SKELETON_TIERS = ["A", "B", "C", "D", "F", "SB"];

// Deterministic 0–3 bars per cell so the skeleton mimics a populated grid without flicker.
const skeletonBarCount = (row: number, col: number) => (row * 3 + col * 2) % 4;

function TierGridSkeleton({
  isMobile,
  stickyTop,
}: {
  isMobile: boolean;
  stickyTop: number;
}) {
  if (isMobile) {
    return (
      <div className="flex flex-col gap-[5px]">
        {SKELETON_TIERS.map((tier, row) => (
          <div key={tier} className="border border-border bg-surface">
            <div className="bg-bg border-b border-border py-1.5 text-center font-display text-[18px] leading-none text-muted">
              {tier}
            </div>
            <div
              className="border-l-4 border-border"
              style={{ borderLeftColor: tierColor(tier) }}
            >
              {[0, 1, 2].map((col, idx) => (
                <div
                  key={col}
                  className={cn("flex", idx > 0 && "border-t border-border")}
                >
                  <div className="w-[44px] shrink-0 flex items-center justify-center">
                    <span className="h-4 w-4 rounded-full bg-surface2 animate-pulse" />
                  </div>
                  <div className="grid min-w-0 flex-1 grid-cols-1 min-[450px]:grid-cols-2 gap-1 px-1 py-2">
                    {Array.from({ length: skeletonBarCount(row, col) + 1 }).map(
                      (_, i) => (
                        <SkeletonBar key={i} />
                      ),
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  const headerCell = {
    position: "sticky",
    top: stickyTop,
    zIndex: 10,
  } as const;

  return (
    <div className="border-x border-b border-border bg-bg">
      <div
        className="grid"
        style={{ gridTemplateColumns: "48px repeat(7, minmax(0, 1fr))" }}
      >
        <div className="border-t border-b border-border bg-bg" style={headerCell} />
        {COLUMN_CODES.map((code) => (
          <div
            key={code}
            className="border-t border-b border-border bg-bg flex items-center justify-center py-2"
            style={headerCell}
          >
            <span className="h-4 w-4 rounded-full bg-surface2 animate-pulse" />
          </div>
        ))}
      </div>
      <div
        className="grid"
        style={{ gridTemplateColumns: "48px repeat(7, minmax(0, 1fr))", rowGap: 2 }}
      >
        {SKELETON_TIERS.map((tier, row) => (
          <Fragment key={tier}>
            <div
              className="border-l-4 border-border bg-bg flex items-center justify-center font-display text-[20px] leading-none text-muted"
              style={{ borderLeftColor: tierColor(tier) }}
            >
              {tier}
            </div>
            {COLUMN_CODES.map((code, col) => (
              <div
                key={code}
                className="bg-surface p-1 flex flex-col gap-1 min-h-[26px]"
              >
                {Array.from({ length: skeletonBarCount(row, col) }).map((_, i) => (
                  <SkeletonBar key={i} />
                ))}
              </div>
            ))}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function SkeletonBar() {
  return (
    <div className="min-h-[28px] rounded-[5px] border-l-4 border-border2 bg-surface2 animate-pulse" />
  );
}

function DesktopGrid({
  byKey,
  filters,
  hideArt,
  stickyTop,
}: {
  byKey: Map<string, TierCard[]>;
  filters: TierFilters;
  hideArt: boolean;
  stickyTop: number;
}) {
  const filtering = hasActiveFilters(filters);
  const pager = useCardPager(byKey, filters);
  const columnHasHit = (code: string) => {
    if (!filtering) return true;
    return TIER_ORDER.some((tier) =>
      (byKey.get(`${code}|${tier}`) ?? []).some(
        (card) => !isCardFilteredOut(card, filters),
      ),
    );
  };
  const headerCell = {
    position: "sticky",
    top: stickyTop,
    zIndex: 10,
  } as const;
  const tierHasAnyCard = (tier: string) =>
    COLUMN_CODES.some(
      (code) => (byKey.get(`${code}|${tier}`) ?? []).length > 0,
    );
  const tiers = TIER_ORDER.filter(
    (tier) => tier !== "TBD" || tierHasAnyCard(tier),
  );

  return (
    <div className="border-x border-b border-border bg-bg">
      <div
        className="grid"
        style={{ gridTemplateColumns: "48px repeat(7, minmax(0, 1fr))" }}
      >
        <div
          className="border-t border-b border-border bg-bg"
          style={headerCell}
        />
        {COLUMN_CODES.map((code) => (
          <div
            key={code}
            title={COLUMN_NAMES[code]}
            className="border-t border-b border-border bg-bg flex items-center justify-center py-2"
            style={headerCell}
          >
            <i
              className={cn(
                columnPipClass(code),
                "transition-opacity",
                !columnHasHit(code) && "opacity-20",
              )}
              style={{
                fontSize: code === "M" ? 21 : 14,
                filter: columnHasHit(code) ? undefined : "grayscale(1)",
              }}
              aria-label={COLUMN_NAMES[code]}
            />
          </div>
        ))}
      </div>
      <div
        className="grid"
        style={{ gridTemplateColumns: "48px repeat(7, minmax(0, 1fr))", rowGap: 2 }}
      >
        {tiers.map((tier) => (
          <Fragment key={tier}>
            <GradeLabel
              tier={tier}
              className="border-l-4 border-border bg-bg flex items-center justify-center font-display text-[20px] leading-none text-text"
              style={{ borderLeftColor: tierColor(tier) }}
            />
            {COLUMN_CODES.map((code) => {
              const bucket = byKey.get(`${code}|${tier}`) ?? [];
              return (
                <div
                  key={code}
                  className="bg-surface px-1 py-2 flex flex-col gap-1 min-h-[26px]"
                >
                  {bucket
                    .filter((card) => !isCardFilteredOut(card, filters))
                    .map((card) => (
                      <CardBar
                        key={card.card_id}
                        card={card}
                        mobile={false}
                        hideArt={hideArt}
                        onOpen={() => pager.open(card.card_id)}
                      />
                    ))}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
      <CardPagerModal pager={pager} />
    </div>
  );
}

function MobileTiers({
  byKey,
  filters,
  hideArt,
}: {
  byKey: Map<string, TierCard[]>;
  filters: TierFilters;
  hideArt: boolean;
}) {
  const filtering = hasActiveFilters(filters);
  const pager = useCardPager(byKey, filters);
  const visibleTiers = TIER_ORDER.map((tier) => ({
    tier,
    colors: COLUMN_CODES.filter((code) => {
      const bucket = byKey.get(`${code}|${tier}`) ?? [];
      if (bucket.length === 0) return false;
      return filtering
        ? bucket.some((card) => !isCardFilteredOut(card, filters))
        : true;
    }),
  })).filter((t) => t.colors.length > 0);

  return (
    <div className="flex flex-col gap-[5px]">
      {visibleTiers.map(({ tier, colors }) => (
        <div key={tier} className="border border-border bg-surface">
          <GradeLabel
            tier={tier}
            className="w-full bg-bg border-b border-border py-1.5 text-center font-display text-[18px] leading-none text-text"
          />
          <div
            className="border-l-4 border-border"
            style={{ borderLeftColor: tierColor(tier) }}
          >
            {colors.map((code, idx) => (
              <div
                key={code}
                className={cn("flex", idx > 0 && "border-t border-border")}
              >
                <div className="w-[44px] shrink-0 flex items-center justify-center">
                  <i
                    className={columnPipClass(code)}
                    style={{ fontSize: code === "M" ? 24 : 16 }}
                    aria-label={COLUMN_NAMES[code]}
                  />
                </div>
                <div className="grid min-w-0 flex-1 grid-cols-1 min-[450px]:grid-cols-2 gap-1 px-1 py-2">
                  {(byKey.get(`${code}|${tier}`) ?? [])
                    .filter((card) => !isCardFilteredOut(card, filters))
                    .map((card) => (
                      <CardBar
                        key={card.card_id}
                        card={card}
                        mobile
                        hideArt={hideArt}
                        onOpen={() => pager.open(card.card_id)}
                      />
                    ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      <CardPagerModal pager={pager} />
    </div>
  );
}

const COLUMN_INDEX: Record<string, number> = Object.fromEntries(COLUMN_CODES.map((code, i) => [code, i]));

// Pager walks the whole main set first, then bonus/source-material reprints, each
// block by color column (W→U→B→R→G→multi→colorless), then keeps each expansion's
// block contiguous, then printed number. Expansion matters because a merged list
// reuses collector numbers across sets. Alt-art "PROMO-12" sorts last.
export function comparePagerOrder(a: TierCard, b: TierCard): number {
  const ia = inclusionRank(a.inclusion_type);
  const ib = inclusionRank(b.inclusion_type);
  if (ia !== ib) return ia - ib;
  const da = COLUMN_INDEX[columnOf(a.color)] ?? COLUMN_CODES.length;
  const db = COLUMN_INDEX[columnOf(b.color)] ?? COLUMN_CODES.length;
  if (da !== db) return da - db;
  if (a.expansion !== b.expansion) return a.expansion.localeCompare(b.expansion);
  const ca = parseCollectorNumber(a.collector_number);
  const cb = parseCollectorNumber(b.collector_number);
  if (ca.altRank !== cb.altRank) return ca.altRank - cb.altRank;
  if (ca.base !== cb.base) return ca.base - cb.base;
  return ca.suffix.localeCompare(cb.suffix);
}

function parseCollectorNumber(num?: string | null) {
  if (!num) return { base: 0, suffix: "", altRank: 0 };
  const alt = num.match(/^([A-Za-z]+)-(\d+)$/);
  if (alt) return { base: parseInt(alt[2], 10), suffix: "", altRank: 1 };
  const norm = num.match(/^(\d+)([A-Za-z]*)$/);
  return { base: parseInt(norm?.[1] ?? "0", 10), suffix: (norm?.[2] ?? "").toUpperCase(), altRank: 0 };
}

// Click-to-open card modal with Prev/Next over the visible cards, in pager order.
// Selecting a card filtered out of view collapses to no selection, closing the modal.
function useCardPager(byKey: Map<string, TierCard[]>, filters: TierFilters) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const visibleCards = useMemo(() => {
    const cards: TierCard[] = [];
    for (const bucket of byKey.values()) {
      for (const card of bucket) {
        if (!isCardFilteredOut(card, filters)) cards.push(card);
      }
    }
    return cards.sort(comparePagerOrder);
  }, [byKey, filters]);
  const selectedIndex = visibleCards.findIndex((card) => card.card_id === selectedId);
  return {
    visibleCards,
    selectedIndex,
    selectedCard: selectedIndex === -1 ? null : visibleCards[selectedIndex],
    open: (cardId: number) => setSelectedId(cardId),
    close: () => setSelectedId(null),
    stepTo: (index: number) => setSelectedId(visibleCards[index].card_id),
  };
}

function CardPagerModal({ pager }: { pager: ReturnType<typeof useCardPager> }) {
  const { selectedCard, selectedIndex, visibleCards, close, stepTo } = pager;
  if (!selectedCard) return null;
  return createPortal(
    <CardModal
      card={selectedCard}
      onClose={close}
      onPrev={selectedIndex > 0 ? () => stepTo(selectedIndex - 1) : undefined}
      onNext={selectedIndex < visibleCards.length - 1 ? () => stepTo(selectedIndex + 1) : undefined}
      position={`${selectedIndex + 1} / ${visibleCards.length}`}
      neighborUrls={neighborCardUrls(visibleCards, selectedIndex)}
    />,
    document.body,
  );
}

export const PREVIEW_W = 260;
export const PREVIEW_RATIO = 1.4;
export const PREVIEW_GAP = 12;
export const PREVIEW_EXTRAS_H = 60;
const PREVIEW_MAT = "#161b26";
const PREVIEW_TAB = "#232c3d";

export interface PreviewAnchor {
  left: number;
  top: number;
  onRight: boolean;
  arrowTop: number;
}


// Anchors a preview beside the hovered element, flipped to whichever side has room and clamped
// vertically. Shared so every card hover on the site lands in the same place with the same chrome.
export function previewAnchorFor(el: HTMLElement, previewH = PREVIEW_W * PREVIEW_RATIO + PREVIEW_EXTRAS_H): PreviewAnchor {
  const rect = el.getBoundingClientRect();
  const centerY = rect.top + rect.height / 2;
  const top = Math.min(
    Math.max(centerY - previewH / 2, 8),
    Math.max(window.innerHeight - previewH - 8, 8),
  );
  const onRight = rect.right + PREVIEW_GAP + PREVIEW_W <= window.innerWidth - 8;
  const left = onRight ? rect.right + PREVIEW_GAP : rect.left - PREVIEW_GAP - PREVIEW_W;
  const arrowTop = Math.min(Math.max(centerY - top, 14), previewH - 14);
  return { left, top, onRight, arrowTop };
}

export function PreviewShell({ anchor, children }: { anchor: PreviewAnchor; children: React.ReactNode }) {
  const g = PREVIEW_GAP;
  const triangle = anchor.onRight ? `M${g} 0 L0 11 L${g} 22 Z` : `M0 0 L${g} 11 L0 22 Z`;
  const triangleInner = anchor.onRight
    ? `M${g} 1.4 L1.6 11 L${g} 20.6 Z`
    : `M0 1.4 L${g - 1.6} 11 L0 20.6 Z`;
  return (
    <div className="pointer-events-none fixed z-[100]" style={{ left: anchor.left, top: anchor.top, width: PREVIEW_W }}>
      <svg
        width={g}
        height="22"
        viewBox={`0 0 ${g} 22`}
        className="absolute z-10"
        style={{ top: anchor.arrowTop - 11, ...(anchor.onRight ? { left: -(g - 1) } : { right: -(g - 1) }) }}
      >
        <path d={triangle} fill="#fff" fillOpacity="0.6" />
        <path d={triangleInner} fill={PREVIEW_MAT} />
      </svg>
      <div
        className="relative flex flex-col rounded-xl border border-white/60 p-[6px] shadow-2xl"
        style={{ backgroundColor: PREVIEW_MAT }}
      >
        {children}
      </div>
    </div>
  );
}

function CardBar({
  card,
  mobile,
  hideArt = false,
  onOpen,
}: {
  card: TierCard;
  mobile: boolean;
  hideArt?: boolean;
  onOpen?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const hovering = useRef(false);
  const [anchor, setAnchor] = useState<PreviewAnchor | null>(null);
  const [artLoaded, setArtLoaded] = useState(false);
  const accent = RARITY_ACCENT[card.rarity] ?? RARITY_ACCENT.C;
  const art = card.url.replace("/large/", "/art_crop/");
  const badges = `${card.comment ? "💬" : ""}${cardFlags(card).map((flag) => flag.glyph).join("")}`;
  const trendLabel = card.trend
    ? `${TREND_LABEL[card.trend]}${card.trend_from ? ` (${card.trend_from} → ${card.tier})` : ""}`
    : "";

  const enterPreview = () => {
    hovering.current = true;
    preloadImage(card.url, () => {
      const el = ref.current;
      if (hovering.current && el) {
        setAnchor(previewAnchorFor(el));
      }
    });
  };

  const leavePreview = () => {
    hovering.current = false;
    setAnchor(null);
  };

  return (
    <div
      ref={ref}
      onMouseEnter={mobile ? undefined : enterPreview}
      onMouseLeave={mobile ? undefined : leavePreview}
      onClick={() => {
        setAnchor(null);
        onOpen?.();
      }}
      className="relative min-[450px]:max-w-[300px] cursor-pointer rounded-[5px] border-l-4"
      style={{ borderLeftColor: accent }}
    >
      <div className="relative min-h-[28px] overflow-hidden rounded-r-[5px] bg-surface2">
        {!hideArt && (
          <>
            <img
              src={art}
              alt=""
              loading="lazy"
              decoding="async"
              onLoad={() => setArtLoaded(true)}
              className={cn(
                "absolute inset-0 h-full w-full object-cover transition-opacity duration-300",
                artLoaded ? "opacity-100" : "opacity-0",
              )}
              style={{ objectPosition: "center 22%" }}
            />
            <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/55 to-black/30" />
          </>
        )}
        <div className="relative flex min-h-[28px] items-center justify-between gap-1 px-2 py-0.5">
          <span className="flex min-w-0 flex-1 items-center gap-1">
            {card.trend && (
              <span
                className={cn(
                  "flex shrink-0 flex-col items-center",
                  TEXT_OUTLINE,
                )}
                style={{ color: TREND_COLOR[card.trend] }}
                title={trendLabel}
                aria-label={trendLabel}
              >
                {trendGlyphStack(card).map((char, i, stack) => (
                  <span
                    key={i}
                    className={cn(
                      "relative text-[13px] leading-none",
                      i > 0 && "-mt-[6px]",
                    )}
                    style={{ zIndex: stack.length - i }}
                  >
                    {char}
                  </span>
                ))}
              </span>
            )}
            <span
              className={cn(
                "min-w-0 line-clamp-2 text-[13px] font-medium leading-tight text-white",
                TEXT_OUTLINE,
              )}
            >
              {card.name}
            </span>
          </span>
          {badges && (
            <span className="shrink-0 text-[14px] leading-none">{badges}</span>
          )}
        </div>
      </div>
      {anchor &&
        createPortal(
          <CardPreview card={card} anchor={anchor} />,
          document.body,
        )}
    </div>
  );
}

function GradesPanel({ card }: { card: TierCard }) {
  const comparison = useContext(ComparisonContext);
  const graders = (card.graders ?? []).filter((grade) => grade.tier !== "TBD");
  if (comparison && graders.length > 0) {
    return (
      <div className="flex items-stretch px-3 py-2.5">
        {graders.map((grade) => (
          <GradeCell key={grade.name} caption={grade.name} tier={grade.tier} />
        ))}
      </div>
    );
  }
  return (
    <div className="flex items-stretch px-3 py-2.5">
      <GradeCell caption="Set review" tier={card.trend_from ?? card.tier} />
      {card.trend ? (
        <GradeCell caption="Updated" tier={card.tier} trendCard={card} />
      ) : (
        graders.length > 0 && (
          <span className="grid flex-1 grid-cols-[auto_auto] content-center items-center justify-center gap-x-4 gap-y-1.5">
            {graders.map((grade) => (
              <Fragment key={grade.name}>
                <span
                  className={cn(
                    "text-[13px] font-semibold leading-none text-white",
                    TEXT_OUTLINE,
                  )}
                >
                  {grade.name}
                </span>
                <span
                  className={cn(
                    "justify-self-start font-display text-[17px] leading-none",
                    TEXT_OUTLINE,
                  )}
                  style={{ color: tierColor(grade.tier) }}
                >
                  {grade.tier}
                </span>
              </Fragment>
            ))}
          </span>
        )
      )}
    </div>
  );
}

function GradeCell({
  caption,
  tier,
  trendCard,
}: {
  caption: string;
  tier: string;
  trendCard?: TierCard;
}) {
  const stack = trendCard?.trend ? trendGlyphStack(trendCard) : [];
  return (
    <span className="flex flex-1 flex-col items-center gap-2">
      <span
        className={cn(
          "text-[12px] font-semibold uppercase tracking-[0.1em] leading-none text-white",
          TEXT_OUTLINE,
        )}
      >
        {caption}
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className={cn("font-display text-[26px] leading-none", TEXT_OUTLINE)}
          style={{ color: tierColor(tier) }}
        >
          {tier}
        </span>
        {trendCard?.trend && (
          <span
            className={cn("flex flex-col items-center", TEXT_OUTLINE)}
            style={{ color: TREND_COLOR[trendCard.trend] }}
          >
            {stack.map((char, i, arr) => (
              <span
                key={i}
                className={cn("text-[11px] leading-none", i > 0 && "-mt-[5px]")}
                style={{ zIndex: arr.length - i }}
              >
                {char}
              </span>
            ))}
          </span>
        )}
      </span>
    </span>
  );
}

// Tabs clip to the panel's top edge instead of taking a row, so a flagged card's
// panel is the same height as every other card's.
function CardFlagTabs({ card }: { card: TierCard }) {
  const flags = cardFlags(card);
  if (flags.length === 0) {
    return null;
  }
  return (
    <div className="absolute -top-[9px] left-1/2 flex -translate-x-1/2 gap-1.5">
      {flags.map((flag) => (
        <span
          key={flag.key}
          className="flex items-center gap-1.5 whitespace-nowrap rounded-full border border-white/60 py-[3px] pl-2 pr-2.5 text-[10px] font-bold uppercase leading-none tracking-[0.08em] text-white"
          style={{ backgroundColor: PREVIEW_TAB }}
        >
          <span className="text-[11px] leading-none tracking-normal">{flag.glyph}</span>
          {flag.label}
        </span>
      ))}
    </div>
  );
}

export function CardPreview({
  card,
  anchor,
}: {
  card: TierCard;
  anchor: PreviewAnchor;
}) {
  return (
    <PreviewShell anchor={anchor}>
      <CardFlagTabs card={card} />
      <GradesPanel card={card} />
      <CardImage src={card.url} alt="" />
      {card.comment && (
        <p className="whitespace-pre-line px-3 py-2.5 text-center text-[14px] leading-snug text-text">
          {card.comment}
        </p>
      )}
    </PreviewShell>
  );
}

export function neighborCardUrls(cards: TierCard[], index: number): string[] {
  const urls: string[] = [];
  for (const neighbor of [cards[index - 1], cards[index + 1]]) {
    if (neighbor) {
      urls.push(neighbor.url);
      if (neighbor.url_back) {
        urls.push(neighbor.url_back);
      }
    }
  }
  return urls;
}

export function CardModal({
  card,
  onClose,
  onPrev,
  onNext,
  position,
  neighborUrls = [],
}: {
  card: TierCard;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  position?: string;
  neighborUrls?: string[];
}) {
  const [flipped, setFlipped] = useState(false);
  const [displayed, setDisplayed] = useState(card);
  const flippable = Boolean(card.url_back);

  useEffect(() => {
    setFlipped(false);
    if (card.url_back) {
      setDisplayed(card);
    }
  }, [card.card_id]);

  const neighborKey = neighborUrls.join("|");
  useEffect(() => {
    for (const url of neighborKey ? neighborKey.split("|") : []) {
      preloadImage(url);
    }
  }, [neighborKey]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") onPrev?.();
      else if (e.key === "ArrowRight") onNext?.();
      else if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onPrev, onNext, onClose]);

  return (
    <div
      className="fixed inset-0 z-[200] flex items-start justify-center bg-black/70 p-6 pt-[max(24px,calc((100dvh-620px)/2))]"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <div className="flex w-full max-w-[320px] flex-col items-center">
        <div
          className="relative w-full rounded-xl border border-white/15 p-[6px] shadow-2xl sm:border-white/60"
          style={{ backgroundColor: PREVIEW_MAT }}
          onClick={(e) => e.stopPropagation()}
        >
          <CardFlagTabs card={displayed} />
          <GradesPanel card={displayed} />
          {flippable ? (
            <FlipCardImage front={card.url} back={card.url_back!} name={card.name} flipped={flipped} />
          ) : (
            <CardImage src={card.url} alt={card.name} onShown={() => setDisplayed(card)} />
          )}
          <div
            className={cn(
              "flex items-center justify-between px-3 py-3.5",
              !displayed.comment && "-mb-[6px]",
            )}
          >
            <ModalNavButton dir="prev" srLabel="Previous card" onClick={onPrev} />
            {position && (
              <span className="mono text-[12px] tracking-[0.1em] text-white/70">
                {position}
              </span>
            )}
            <ModalNavButton dir="next" srLabel="Next card" onClick={onNext} />
          </div>
          {displayed.comment && (
            <p className="-mx-[6px] -mb-[6px] whitespace-pre-line border-t border-white/15 px-3 py-3.5 text-center text-[14px] leading-snug text-text sm:border-white/60">
              {displayed.comment}
            </p>
          )}
        </div>
        {flippable && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setFlipped((prev) => !prev);
            }}
            className="mt-4 flex items-center gap-2 rounded-lg border border-white/40 px-4 py-2 text-[13px] font-medium text-text shadow-lg transition-colors hover:bg-white/10"
            style={{ backgroundColor: PREVIEW_MAT }}
          >
            <RefreshCw size={15} />
            Turn Over
          </button>
        )}
      </div>
    </div>
  );
}

function FlipCardImage({
  front,
  back,
  name,
  flipped,
}: {
  front: string;
  back: string;
  name: string;
  flipped: boolean;
}) {
  const { loaded: frontLoaded, instant, onLoad } = useImageReveal(front);

  return (
    <div className="w-full [perspective:1200px]">
      <div
        className="relative w-full transition-transform duration-700 [transform-style:preserve-3d] [-webkit-transform-style:preserve-3d]"
        style={{
          aspectRatio: "28 / 39",
          transform: flipped ? "rotateY(180deg)" : undefined,
        }}
      >
        {!frontLoaded && (
          <div className={cn("absolute inset-0 animate-pulse bg-surface2 [backface-visibility:hidden]", CARD_CORNER)} />
        )}
        <img
          src={front}
          alt={name}
          decoding="async"
          onLoad={onLoad}
          onError={onLoad}
          className={cn(
            "absolute inset-0 h-full w-full object-cover [backface-visibility:hidden] [-webkit-backface-visibility:hidden]",
            !instant && "transition-opacity duration-300",
            CARD_CORNER,
            CARD_EDGE,
            frontLoaded ? "opacity-100" : "opacity-0",
          )}
        />
        <img
          src={back}
          alt=""
          decoding="async"
          className={cn(
            "absolute inset-0 h-full w-full object-cover [backface-visibility:hidden] [-webkit-backface-visibility:hidden] [transform:rotateY(180deg)]",
            CARD_CORNER,
            CARD_EDGE,
          )}
        />
      </div>
    </div>
  );
}

const CARD_CORNER = "rounded-[4.5%/3.2%]";
const CARD_EDGE = "outline outline-1 -outline-offset-1 outline-white/10";

function CardImage({
  src,
  alt,
  onShown,
}: {
  src: string;
  alt: string;
  onShown?: () => void;
}) {
  const [layers, setLayers] = useState(() => [{ key: 0, src }]);
  const keyRef = useRef(0);

  useEffect(() => {
    setLayers((prev) => {
      if (prev[prev.length - 1].src === src) {
        return prev;
      }
      keyRef.current += 1;
      return [...prev, { key: keyRef.current, src }];
    });
  }, [src]);

  const settle = (key: number, layerSrc: string) => {
    setLayers((prev) => {
      const idx = prev.findIndex((layer) => layer.key === key);
      return idx <= 0 ? prev : prev.slice(idx);
    });
    if (layerSrc === src) {
      onShown?.();
    }
  };

  return (
    <div
      className={cn("relative w-full overflow-hidden", CARD_CORNER, CARD_EDGE)}
      style={{ aspectRatio: "488 / 680" }}
    >
      {layers.map((layer, i) => (
        <CardImageLayer
          key={layer.key}
          src={layer.src}
          alt={alt}
          base={i === 0}
          onSettled={() => settle(layer.key, layer.src)}
        />
      ))}
    </div>
  );
}

function CardImageLayer({
  src,
  alt,
  base,
  onSettled,
}: {
  src: string;
  alt: string;
  base: boolean;
  onSettled: () => void;
}) {
  const ref = useRef<HTMLImageElement>(null);
  const settled = useRef(onSettled);
  settled.current = onSettled;
  const [ready, setReady] = useState(false);
  const [instant, setInstant] = useState(false);

  useLayoutEffect(() => {
    const cached = isImageLoaded(src);
    setReady(cached);
    setInstant(cached);
    if (cached) {
      const img = ref.current;
      const settle = () => settled.current();
      if (img) {
        img.decode().then(settle, settle);
      } else {
        settle();
      }
    }
  }, [src, base]);

  const reveal = () => {
    markImageLoaded(src);
    setReady(true);
  };

  return (
    <>
      {base && !ready && <div className="absolute inset-0 animate-pulse bg-surface2" />}
      <img
        ref={ref}
        src={src}
        alt={alt}
        decoding="async"
        onLoad={reveal}
        onError={reveal}
        onAnimationEnd={() => settled.current()}
        className={cn(
          "absolute inset-0 h-full w-full object-cover",
          !ready && "opacity-0",
          ready && instant && "opacity-100",
          ready && !instant && "animate-fadeIn",
        )}
      />
    </>
  );
}

