import {
  createContext,
  Fragment,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { LuScrollText, Maximize2, Minimize2, Play, RefreshCw } from "./Icons";
import { GradeLabel } from "./TierGuide";
import { ModalNavButton } from "./ModalNavButton";
import { Tooltip } from "./Tooltip";
import { cardSlug } from "../lib/cardSlug";
import { OPENED_IN_APP, useCloseModal } from "../lib/modal-history";
import { cn } from "../lib/utils";
import { useSetReviewMention, useTranscript } from "../data/hooks";
import { cardDiscussion, type SetReviewMention } from "../data/transcript";
import { isImageLoaded, markImageLoaded, preloadImage, useImageReveal } from "../lib/imageReveal";
import { SPEAKER_LANES, TEXT_OUTLINE } from "../lib/text-styles";
import { speakerTurns } from "../lib/transcriptText";
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
  setCode,
  uid,
  graders,
  comparison = false,
  filters,
  hideArt,
  stickyTop,
}: {
  setCode: string;
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
        <MobileTiers setCode={setCode} byKey={byKey} filters={filters} hideArt={hideArt} />
      ) : (
        <DesktopGrid setCode={setCode} byKey={byKey} filters={filters} hideArt={hideArt} stickyTop={stickyTop} />
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
  setCode,
  byKey,
  filters,
  hideArt,
  stickyTop,
}: {
  setCode: string;
  byKey: Map<string, TierCard[]>;
  filters: TierFilters;
  hideArt: boolean;
  stickyTop: number;
}) {
  const filtering = hasActiveFilters(filters);
  const pager = useCardPager(setCode, byKey, filters);
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
  setCode,
  byKey,
  filters,
  hideArt,
}: {
  setCode: string;
  byKey: Map<string, TierCard[]>;
  filters: TierFilters;
  hideArt: boolean;
}) {
  const filtering = hasActiveFilters(filters);
  const pager = useCardPager(setCode, byKey, filters);
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
function useCardPager(setCode: string, byKey: Map<string, TierCard[]>, filters: TierFilters) {
  const { card: cardParam } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const visibleCards = useMemo(() => {
    const cards: TierCard[] = [];
    for (const bucket of byKey.values()) {
      for (const card of bucket) {
        if (!isCardFilteredOut(card, filters)) cards.push(card);
      }
    }
    return cards.sort(comparePagerOrder);
  }, [byKey, filters]);
  const selectedIndex = cardParam ? visibleCards.findIndex((card) => cardSlug(card.name) === cardParam) : -1;
  const setPath = `/tier-list/${setCode}`;
  const closeCard = useCloseModal(setPath);
  const cardPath = (card: TierCard) => `${setPath}/${cardSlug(card.name)}${location.search}`;
  return {
    visibleCards,
    selectedIndex,
    selectedCard: selectedIndex === -1 ? null : visibleCards[selectedIndex],
    open: (cardId: number) => {
      const card = visibleCards.find((candidate) => candidate.card_id === cardId);
      if (card) {
        navigate(cardPath(card), { state: OPENED_IN_APP });
      }
    },
    close: closeCard,
    stepTo: (index: number) => navigate(cardPath(visibleCards[index]), { replace: true, state: location.state }),
  };
}

function CardPagerModal({ pager }: { pager: ReturnType<typeof useCardPager> }) {
  const { selectedCard, selectedIndex, visibleCards, close, stepTo } = pager;
  if (!selectedCard) return null;
  return createPortal(
    <CardModal
      card={selectedCard}
      linkReview
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
  centerY: number;
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
  return { left, top, onRight, centerY };
}

export function PreviewShell({ anchor, children }: { anchor: PreviewAnchor; children: React.ReactNode }) {
  const g = PREVIEW_GAP;
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardHeight, setCardHeight] = useState(0);
  useLayoutEffect(() => {
    setCardHeight(cardRef.current?.offsetHeight ?? 0);
  }, [anchor, children]);

  const arrowTop = anchor.centerY - anchor.top;
  const arrowVisible = cardHeight > 0 && arrowTop >= 14 && arrowTop <= cardHeight - 14;
  const triangle = anchor.onRight ? `M${g} 0 L0 11 L${g} 22 Z` : `M0 0 L${g} 11 L0 22 Z`;
  const triangleInner = anchor.onRight
    ? `M${g} 1.4 L1.6 11 L${g} 20.6 Z`
    : `M0 1.4 L${g - 1.6} 11 L0 20.6 Z`;
  return (
    <div className="pointer-events-none fixed z-[100]" style={{ left: anchor.left, top: anchor.top, width: PREVIEW_W }}>
      {arrowVisible && (
        <svg
          width={g}
          height="22"
          viewBox={`0 0 ${g} 22`}
          className="absolute z-10"
          style={{ top: arrowTop - 11, ...(anchor.onRight ? { left: -(g - 1) } : { right: -(g - 1) }) }}
        >
          <path d={triangle} fill="#fff" fillOpacity="0.6" />
          <path d={triangleInner} fill={PREVIEW_MAT} />
        </svg>
      )}
      <div
        ref={cardRef}
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
  linkReview = false,
  onClose,
  onPrev,
  onNext,
  position,
  neighborUrls = [],
}: {
  card: TierCard;
  linkReview?: boolean;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  position?: string;
  neighborUrls?: string[];
}) {
  const [flipped, setFlipped] = useState(false);
  const [displayed, setDisplayed] = useState(card);
  const [views, setViews] = usePersistedReviewViews(linkReview);
  const [renderedViews, setRenderedViews] = useState(views);
  const mountedRef = useRef(false);
  useEffect(() => {
    mountedRef.current = true;
  }, []);
  const wide = !useIsMobile(1024);
  const flippable = Boolean(card.url_back);
  const { setIndexed, mention } = useSetReviewMention(card.expansion, card.name);

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
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        (document.activeElement as HTMLElement | null)?.blur();
      }
      if (e.key === "ArrowLeft") onPrev?.();
      else if (e.key === "ArrowRight") onNext?.();
      else if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onPrev, onNext, onClose]);

  const mobileView = singleReviewView(views);
  const toggleView = (view: ReviewView) => {
    const next = wide ? { ...views, [view]: !views[view] } : { ...NO_REVIEW_VIEWS, [view]: mobileView !== view };
    setViews(next);
    revealViews(next);
  };
  const revealViews = (shown: ReviewViews) =>
    setRenderedViews((prev) => ({ transcript: prev.transcript || shown.transcript, video: prev.video || shown.video }));
  const hideRenderedView = (view: ReviewView) => setRenderedViews((prev) => ({ ...prev, [view]: false }));
  const found = Boolean(mention);
  const lastMention = useRef(mention);
  if (mention) {
    lastMention.current = mention;
  }
  const panelMention = lastMention.current;
  const viewPressed = (view: ReviewView) => found && (wide ? views[view] : mobileView === view);
  const reviewToggle = (view: ReviewView, showTip: string, hideTip: string) => ({
    pressed: viewPressed(view),
    disabled: !found,
    tooltip: found ? (viewPressed(view) ? hideTip : showTip) : "Card not found in the Set Review",
    onClick: () => toggleView(view),
  });
  const transcriptToggle = reviewToggle("transcript", "Read about this card", "Hide the transcript");
  const videoToggle = reviewToggle("video", "Jump to this card in the video", "Hide the video");
  const reviewShown = setIndexed && found && (views.transcript || views.video);
  const panelOpen = wide && reviewShown;
  const mobilePanel = !wide && reviewShown;

  useEffect(() => {
    if (panelOpen) {
      revealViews(views);
    }
  }, [panelOpen]);
  const [fullScreen, setFullScreen] = usePersistedFullScreen();
  const enlarged = panelOpen && fullScreen;
  const panelSpan = "calc(var(--panel-w) + 16px)";
  const modalSizes = {
    "--card-w": enlarged ? "min(calc((90dvh - 150px) / 1.4), 34vw)" : "320px",
    "--panel-w": enlarged ? "calc(90vw - var(--card-w) - 16px)" : "min(520px, calc(50vw - 200px))",
  } as React.CSSProperties;
  const sideTranscript = renderedViews.transcript;
  const cappedVideo = cn(enlarged && sideTranscript && "mx-auto w-full max-w-[calc(55dvh*16/9)]");

  return (
    <div
      className={cn(
        "fixed inset-0 z-[200] flex items-start justify-center overflow-y-auto bg-black/70",
        "transition-[padding] duration-300 ease-out",
        mobilePanel && "p-3",
        !mobilePanel && (enlarged ? "p-6 pt-[5dvh]" : "p-6 pt-[max(24px,calc((100dvh-620px)/2))]"),
      )}
      style={modalSizes}
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <div
        className={cn(
          "flex w-full shrink-0 flex-col items-center transition-[transform,max-width] duration-300 ease-out",
          mobilePanel && "h-full max-w-[480px]",
          !mobilePanel && (wide ? "max-w-[var(--card-w)]" : "max-w-[320px]"),
        )}
        style={{ transform: panelOpen ? `translateX(calc(${panelSpan} / -2))` : undefined }}
      >
        <div
          className={cn(
            "relative w-full shrink-0 rounded-xl border border-white/15 p-[6px] shadow-2xl sm:border-white/60",
            !wide && "max-w-[320px]",
          )}
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
              mobilePanel && "hidden",
            )}
          >
            <ModalNavButton dir="prev" srLabel="Previous card" onClick={onPrev} />
            {position && (
              <span className="font-num text-[12px] tracking-[0.1em] text-white/70">
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
          {panelOpen && (
            <div className="absolute left-full top-full flex justify-end pt-4" style={{ width: panelSpan }}>
              <ModalActionButton
                tooltip={fullScreen ? "Use compact size" : "Use the full screen"}
                onClick={() => setFullScreen(!fullScreen)}
              >
                {fullScreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
                {fullScreen ? "Collapse" : "Expand"}
              </ModalActionButton>
            </div>
          )}
          {wide && (
            <div
              className={cn(
                "absolute -top-px left-full flex max-h-[calc(100%+2px)] justify-end overflow-hidden",
                "transition-[width] duration-300 ease-out",
              )}
              style={{ width: panelOpen ? panelSpan : 0 }}
              onTransitionEnd={(e) => {
                if (e.target === e.currentTarget && !panelOpen) {
                  setRenderedViews(NO_REVIEW_VIEWS);
                }
              }}
            >
              {setIndexed && panelMention && (
                <div className="flex w-[var(--panel-w)] shrink-0 flex-col transition-[width] duration-300 ease-out">
                  {renderedViews.video && (
                    <Collapse
                      open={views.video}
                      animateIn={mountedRef.current}
                      onClosed={() => hideRenderedView("video")}
                      className="shrink-0"
                    >
                      <div className="pb-3">
                        <ReviewBox className={cappedVideo}>
                          <SetReviewVideo mention={panelMention} />
                        </ReviewBox>
                      </div>
                    </Collapse>
                  )}
                  {sideTranscript && (
                    <Collapse
                      open={views.transcript}
                      animateIn={mountedRef.current}
                      onClosed={() => hideRenderedView("transcript")}
                      className="min-h-0"
                    >
                      <ReviewBox className="min-h-0">
                        <ReviewPanel view="transcript" mention={panelMention} cardName={card.name} />
                      </ReviewBox>
                    </Collapse>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        {(flippable || setIndexed) && !mobilePanel && (
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            {flippable && (
              <ModalActionButton onClick={() => setFlipped((prev) => !prev)}>
                <RefreshCw size={15} />
                Turn Over
              </ModalActionButton>
            )}
            {setIndexed && (
              <>
                <ModalActionButton {...transcriptToggle}>
                  <LuScrollText size={15} />
                  Transcript
                </ModalActionButton>
                <ModalActionButton {...videoToggle}>
                  <Play size={15} />
                  Video
                </ModalActionButton>
              </>
            )}
          </div>
        )}
        {mobilePanel && (
          <Collapse
            open
            animateIn={mountedRef.current}
            className={cn("w-full", mobileView === "transcript" && "min-h-0 flex-1")}
          >
            <div
              className={cn(
                "mt-3 flex min-h-0 w-full flex-col overflow-hidden rounded-lg border border-white/40 shadow-2xl",
                mobileView === "transcript" && "flex-1",
              )}
              style={{ backgroundColor: PREVIEW_MAT }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex shrink-0 items-center gap-2 border-b border-white/15 p-2">
                <ModalNavButton dir="prev" srLabel="Previous card" onClick={onPrev} />
                <ModalActionButton compact grow {...transcriptToggle}>
                  <LuScrollText size={15} />
                  Transcript
                </ModalActionButton>
                <ModalActionButton compact grow {...videoToggle}>
                  <Play size={15} />
                  Video
                </ModalActionButton>
                {flippable && (
                  <ModalActionButton compact onClick={() => setFlipped((prev) => !prev)}>
                    <RefreshCw size={15} />
                  </ModalActionButton>
                )}
                <ModalNavButton dir="next" srLabel="Next card" onClick={onNext} />
              </div>
              <div className="flex min-h-0 flex-1 flex-col p-3">
                {mobileView && mention && (
                  <ReviewPanel view={mobileView} mention={mention} cardName={card.name} />
                )}
              </div>
            </div>
          </Collapse>
        )}
      </div>
    </div>
  );
}

type ReviewView = "transcript" | "video";
type ReviewViews = Record<ReviewView, boolean>;

const NO_REVIEW_VIEWS: ReviewViews = { transcript: false, video: false };

function usePersistedReviewViews(linkReview: boolean): [ReviewViews, (next: ReviewViews) => void] {
  const storageKey = "tierCardReviewPanel";
  const [searchParams, setSearchParams] = useSearchParams();
  const linkedReview = searchParams.get("review");
  const [views, setViews] = useState<ReviewViews>(() => {
    const linked = linkReview && linkedReview !== null ? decodeReviewViews(linkedReview) : null;
    return linked ?? decodeReviewViews(window.localStorage.getItem(storageKey) ?? "");
  });
  const encoded = encodeReviewViews(views);

  useEffect(() => {
    if (!linkReview || (linkedReview ?? "") === encoded) {
      return;
    }
    const params = new URLSearchParams(searchParams);
    if (encoded) {
      params.set("review", encoded);
    } else {
      params.delete("review");
    }
    setSearchParams(params, { replace: true });
  }, [linkReview, linkedReview, encoded]);

  const update = (next: ReviewViews) => {
    setViews(next);
    window.localStorage.setItem(storageKey, encodeReviewViews(next));
  };
  return [views, update];
}

function usePersistedFullScreen(): [boolean, (next: boolean) => void] {
  const storageKey = "tierCardReviewFullScreen";
  const [fullScreen, setFullScreen] = useState(() => window.localStorage.getItem(storageKey) === "1");
  const update = (next: boolean) => {
    setFullScreen(next);
    window.localStorage.setItem(storageKey, next ? "1" : "0");
  };
  return [fullScreen, update];
}

function singleReviewView(views: ReviewViews): ReviewView | null {
  if (views.transcript) {
    return "transcript";
  }
  return views.video ? "video" : null;
}

function encodeReviewViews(views: ReviewViews): string {
  if (views.transcript && views.video) {
    return "both";
  }
  if (views.transcript) {
    return "transcript";
  }
  return views.video ? "video" : "";
}

function decodeReviewViews(value: string): ReviewViews {
  return { transcript: value === "transcript" || value === "both", video: value === "video" || value === "both" };
}

function Collapse({
  open,
  animateIn,
  onClosed,
  className,
  children,
}: {
  open: boolean;
  animateIn: boolean;
  onClosed?: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(open && !animateIn);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => setExpanded(open));
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  return (
    <div
      className={cn("grid transition-[grid-template-rows] duration-300 ease-out", className)}
      style={{ gridTemplateRows: expanded ? "minmax(0, 1fr)" : "minmax(0, 0fr)" }}
      onTransitionEnd={(e) => {
        if (e.target === e.currentTarget && !open) {
          onClosed?.();
        }
      }}
    >
      <div className="flex min-h-0 flex-col overflow-hidden">{children}</div>
    </div>
  );
}

function ReviewBox({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-xl border border-white/15 p-3 shadow-2xl sm:border-white/60",
        className,
      )}
      style={{ backgroundColor: PREVIEW_MAT }}
    >
      {children}
    </div>
  );
}

function ModalActionButton({
  onClick,
  pressed,
  compact,
  grow,
  disabled = false,
  tooltip,
  children,
}: {
  onClick: () => void;
  pressed?: boolean;
  compact?: boolean;
  grow?: boolean;
  disabled?: boolean;
  tooltip?: string;
  children: React.ReactNode;
}) {
  const toggle = pressed !== undefined;
  const button = (
    <button
      type="button"
      aria-pressed={pressed}
      aria-disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        if (!disabled) {
          onClick();
        }
      }}
      className={cn(
        "flex items-center gap-2 rounded-lg border text-[13px] font-medium text-text shadow-lg",
        compact ? "px-3 py-1.5" : "px-4 py-2",
        grow && "flex-1 justify-center",
        "transition-colors",
        !toggle && "border-white/40 hover:bg-white/10",
        toggle && !disabled && "hover:border-green hover:text-green",
        disabled && "cursor-not-allowed opacity-40",
        toggle && (pressed ? "border-white/80" : "border-white/40"),
      )}
      style={{ backgroundColor: pressed ? PREVIEW_TAB : PREVIEW_MAT }}
    >
      {children}
    </button>
  );
  if (!tooltip) {
    return button;
  }
  return (
    <Tooltip label={tooltip} side="top" className="z-[250]">
      {button}
    </Tooltip>
  );
}

function ReviewPanel({
  view,
  mention,
  cardName,
}: {
  view: ReviewView;
  mention: SetReviewMention;
  cardName: string;
}) {
  if (view === "video") {
    return <SetReviewVideo mention={mention} />;
  }
  return <SetReviewTranscript mention={mention} cardName={cardName} />;
}

function SetReviewVideo({ mention }: { mention: SetReviewMention }) {
  const playerRef = useRef<HTMLIFrameElement>(null);
  const [origin] = useState(mention);
  const cuedRef = useRef(mention);
  const playingRef = useRef(false);

  const command = (func: string, args: unknown[] = []) =>
    playerRef.current?.contentWindow?.postMessage(
      JSON.stringify({ event: "command", func, args }),
      "https://www.youtube.com",
    );

  useEffect(() => {
    const listen = () =>
      playerRef.current?.contentWindow?.postMessage(
        JSON.stringify({ event: "listening", id: 1, channel: "widget" }),
        "https://www.youtube.com",
      );
    const timers = [500, 1200, 2500].map((delay) => window.setTimeout(listen, delay));
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== "https://www.youtube.com" || event.source !== playerRef.current?.contentWindow) {
        return;
      }
      try {
        const data = JSON.parse(event.data);
        if (data.event === "infoDelivery" && typeof data.info?.playerState === "number") {
          playingRef.current = data.info.playerState === 1 || data.info.playerState === 3;
        }
      } catch {
        return;
      }
    };
    window.addEventListener("message", onMessage);
    return () => {
      timers.forEach(window.clearTimeout);
      window.removeEventListener("message", onMessage);
    };
  }, [origin]);

  useEffect(() => {
    const current = cuedRef.current;
    cuedRef.current = mention;
    if (current.youtubeId === mention.youtubeId && current.t === mention.t) {
      return;
    }
    const target = { videoId: mention.youtubeId, startSeconds: mention.t };
    if (!playingRef.current) {
      command("cueVideoById", [target]);
    } else if (current.youtubeId === mention.youtubeId) {
      command("seekTo", [mention.t, true]);
    } else {
      command("loadVideoById", [target]);
    }
  }, [mention]);

  const params = `start=${origin.t}&autoplay=1&playsinline=1&rel=0&cc_load_policy=0&enablejsapi=1`;
  return (
    <div className="relative aspect-video w-full shrink-0 overflow-hidden rounded-lg bg-black">
      <iframe
        ref={playerRef}
        src={`https://www.youtube.com/embed/${origin.youtubeId}?${params}`}
        title={origin.title}
        className="absolute inset-0 h-full w-full"
        allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
        allowFullScreen
      />
    </div>
  );
}

function SetReviewTranscript({ mention, cardName }: { mention: SetReviewMention; cardName: string }) {
  const { transcript } = useTranscript(mention.youtubeId);
  if (!transcript) {
    return <div className="h-24 shrink-0 animate-pulse rounded bg-white/5" />;
  }
  const discussion = cardDiscussion(transcript, mention.segmentIndex, cardName);
  const turns = speakerTurns(transcript.slice(0, mention.segmentIndex), discussion);
  return (
    <div className="min-h-0 space-y-3 overflow-y-auto pr-1 text-[14px] leading-snug text-text">
      {turns.map((turn, index) => (
        <div key={index} className={cn("space-y-2 border-l-2 pl-3", SPEAKER_LANES[turn.lane].border)}>
          {turn.paragraphs.map((text, paragraphIndex) => (
            <p key={paragraphIndex}>{text}</p>
          ))}
        </div>
      ))}
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

