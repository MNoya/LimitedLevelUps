import { useEffect, useMemo, useState, type MouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { Check, ChevronLeft, ChevronRight, Copy, X, ZoomIn, ZoomOut } from "lucide-react";
import { ArrowRight, GiRoundTable, ImageIcon, LuScrollText, SiDiscord, TbCards } from "../Icons";
import { ChamferedButton } from "../ChamferedButton";
import { Pips } from "../ManaPips";
import { Record } from "../Record";
import { cn } from "../../lib/utils";
import { CardImageMapProvider, StackColumn, useCardImageMapContext, useFallbackImage } from "./review/ReviewCard";
import { cardImageSources, useCardImageMap, type CardImages } from "../../data/cardImages";
import { useIsMobile } from "../../lib/use-is-mobile";
import { useResolvedDeckUrl } from "../../data/refresh-deck-url";
import type { Mainboard } from "../../types/leaderboard";

export const BREAKDOWN_CAPTION = "Seats, logs & replays";

export interface DeckLike {
  eventId?: string;
  displayName: string;
  participantDisplayName?: string;
  deckColors: string | null;
  deckScreenshotUrl: string | null;
  deckScreenshotCaption?: string | null;
  // Original public post that created a self-reported deck; surfaced as a "View on Discord" link
  deckSourceUrl?: string | null;
  mainboard?: Mainboard | null;
  record?: string | null;
  // Self-reported trophies refresh their Discord CDN screenshot by message ref instead of pod event
  screenshotChannelId?: string | null;
  screenshotMessageId?: string | null;
}

export type DeckTab = "screenshot" | "decklist";

interface Props {
  participant: DeckLike;
  initialTab?: DeckTab;
  breakdownHref?: string;
  hideDraftLog?: boolean;
  draftLogHref?: string | null;
  // A whole-draft image map warmed upstream; when passed the Card Pool reuses it instead of re-fetching its subset
  cardImages?: CardImages;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}

export function DeckScreenshotModal({ participant, initialTab = "screenshot", breakdownHref, hideDraftLog = false, draftLogHref, cardImages, onClose, onPrev, onNext }: Props) {
  const isMobile = useIsMobile();
  const navigate = useNavigate();

  const hasScreenshot = participant.deckScreenshotUrl !== null;
  const recordWins = Number((participant.record ?? "").split("-")[0] || 0);
  const recordLosses = Number((participant.record ?? "").split("-")[1] || 0);
  const hasRecord = participant.record != null && recordWins + recordLosses > 0;
  const hasDecklist = (participant.mainboard?.cards.length ?? 0) > 0;
  const deckKey = `${participant.eventId ?? ""}::${participant.participantDisplayName ?? participant.displayName}`;
  const [tab, setTab] = useState<DeckTab>(initialTab);
  const effectiveTab: DeckTab =
    hasScreenshot && hasDecklist ? tab : hasDecklist ? "decklist" : "screenshot";
  const showPanelToggle = hasScreenshot && hasDecklist;
  const showDraftLogTab = !hideDraftLog;
  const hasTabs = showPanelToggle || showDraftLogTab;
  const hasSourceLink = !!participant.deckSourceUrl;
  const panelHasControls = hasTabs || !!onPrev || !!onNext;
  const showTabBar = panelHasControls || hasSourceLink;

  const { url: resolvedUrl, resolving: isResolving } = useResolvedDeckUrl(participant);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const [zoomed, setZoomed] = useState(true);

  useEffect(() => {
    setZoomed(true);
  }, [participant.deckScreenshotUrl]);

  useEffect(() => {
    setImgLoaded(false);
    setImgFailed(false);
    if (!resolvedUrl) return;
    const preloader = new Image();
    preloader.onload = () => setImgLoaded(true);
    preloader.onerror = () => setImgFailed(true);
    preloader.src = resolvedUrl;
  }, [resolvedUrl]);

  const showSkeleton = isResolving || (resolvedUrl !== null && !imgLoaded && !imgFailed);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowLeft" && onPrev) {
        e.preventDefault();
        onPrev();
      } else if (e.key === "ArrowRight" && onNext) {
        e.preventDefault();
        onNext();
      }
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose, onPrev, onNext]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col items-center bg-black/80 backdrop-blur-sm animate-fadeIn px-[4px] md:px-6 pt-28 pb-6 lg:pt-28 lg:pb-8"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`${participant.displayName}'s deck`}
    >
      <div
        className="relative bg-surface border border-border w-full max-w-[1400px] h-[70vh] shrink-0 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3 lg:gap-6 pl-9 pr-5 py-3 border-b border-border shrink-0">
          <Pips colors={participant.deckColors ?? ""} size={18} />
          <span
            className="font-display text-text truncate flex-1 text-center lg:text-left"
            style={{ fontSize: 26, lineHeight: 1, letterSpacing: "0.04em", fontFamily: "'Bebas Neue', sans-serif", paddingTop: 4 }}
          >
            {participant.displayName}
          </span>
          {hasRecord && (
            <Record wins={recordWins} losses={recordLosses} className="mono text-[20px] shrink-0" />
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-muted hover:text-text transition-colors p-1 bg-transparent border-0 cursor-pointer shrink-0"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-hidden">
          <div key={deckKey} className="h-full animate-fadeIn">
          {effectiveTab === "decklist" && participant.mainboard ? (
            <DecklistView mainboard={participant.mainboard} warmedImages={cardImages} />
          ) : showSkeleton ? (
            <div className="h-full p-4 md:p-5">
              <div className="w-full h-full bg-surface2 animate-pulse" />
            </div>
          ) : imgFailed ? (
            <div className="h-full flex items-center justify-center px-5 text-center text-muted font-body">
              Deck screenshot failed to load
            </div>
          ) : resolvedUrl ? (
            isMobile ? (
              <div className="relative h-full">
                {zoomed ? (
                  <div className="h-full overflow-x-auto overflow-y-hidden themed-scrollbar">
                    <img
                      src={resolvedUrl}
                      alt={`${participant.displayName} deck screenshot`}
                      className="block h-full w-auto max-w-none select-none"
                      draggable={false}
                    />
                  </div>
                ) : (
                  <div className="h-full flex items-center justify-center overflow-hidden">
                    <img
                      src={resolvedUrl}
                      alt={`${participant.displayName} deck screenshot`}
                      className="block max-h-full max-w-full w-auto h-auto select-none"
                      draggable={false}
                    />
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => setZoomed((z) => !z)}
                  aria-label={zoomed ? "Fit deck to screen" : "Zoom deck"}
                  className="absolute left-2 bottom-2 z-10 inline-flex items-center gap-1.5 rounded bg-bg/85 border border-border text-text px-2.5 py-1.5 font-display tracking-[0.14em] text-[11px] cursor-pointer backdrop-blur-sm"
                >
                  {zoomed ? <ZoomOut size={13} /> : <ZoomIn size={13} />}
                  {zoomed ? "ZOOM OUT" : "ZOOM IN"}
                </button>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center overflow-hidden px-4 py-6">
                <img
                  src={resolvedUrl}
                  alt={`${participant.displayName} deck screenshot`}
                  className="block max-h-full max-w-full w-auto h-auto select-none"
                  draggable={false}
                />
              </div>
            )
          ) : (
            <div className="h-full flex items-center justify-center px-5 text-center text-muted font-body">
              No deck screenshot available
            </div>
          )}
          </div>
        </div>

        {breakdownHref && (
          <Link to={breakdownHref} className="hidden lg:block no-underline border-t border-border shrink-0">
            <div className="flex items-center justify-between gap-4 px-4 py-3 bg-surface hover:bg-green/5 transition-colors cursor-pointer">
              <div className="flex flex-1 items-center gap-3 min-w-0 pl-5">
                {participant.deckScreenshotCaption && (
                  <span className="text-muted text-[15px] font-body italic leading-snug min-w-0 truncate">
                    {participant.deckScreenshotCaption}
                  </span>
                )}
                {hasDecklist && <CopyDeckButton mainboard={participant.mainboard!} className="ml-auto" />}
              </div>
              <div className="flex items-center gap-4 shrink-0">
                <span className="text-muted text-[13px] font-body">
                  {BREAKDOWN_CAPTION}
                </span>
                <ChamferedButton>
                  <span className="inline-flex items-center gap-2">
                    <GiRoundTable size={30} className="-my-[6px]" />
                    VIEW BREAKDOWN
                     <ArrowRight size={14} />
                  </span>
                </ChamferedButton>
              </div>
            </div>
          </Link>
        )}
        {(participant.deckScreenshotCaption || hasDecklist) && (
          <div
            className={cn(
              "flex items-center gap-3 px-4 py-3 lg:pl-9 lg:pr-5 lg:py-4 border-t border-border shrink-0 bg-surface",
              breakdownHref && "lg:hidden",
            )}
          >
            {participant.deckScreenshotCaption && (
              <span className="text-muted text-[15px] font-body italic leading-snug min-w-0">
                {participant.deckScreenshotCaption}
              </span>
            )}
            {hasDecklist && <CopyDeckButton mainboard={participant.mainboard!} className="ml-auto" />}
          </div>
        )}
      </div>
      <div className="flex-1 min-h-0 w-full max-w-[1400px] flex flex-col items-center justify-center gap-10 px-4 md:px-0">
        {showTabBar && (
        <div
          onClick={(e) => e.stopPropagation()}
          className={cn(
            "shrink-0 flex items-center rounded-2xl bg-surface border border-border shadow-lg px-3 py-2 lg:px-4",
            hasTabs
              ? "w-full lg:w-auto justify-between gap-2 lg:gap-4"
              : "justify-center gap-2 lg:gap-3",
          )}
        >
          {onPrev ? <PanelChevron side="left" onClick={onPrev} /> : hasTabs ? <span className="w-10 shrink-0" /> : null}
          <div className="flex items-center gap-1.5">
            {hasSourceLink && (
              <a
                href={participant.deckSourceUrl!}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-full border border-border bg-surface2 text-muted hover:text-text px-4 py-2.5 font-display tracking-[0.14em] no-underline transition-colors"
                style={{ fontSize: 14 }}
              >
                <SiDiscord size={16} />
                VIEW ON DISCORD
              </a>
            )}
            {showPanelToggle && (
              <PanelTab
                active={effectiveTab === "screenshot"}
                onClick={() => setTab("screenshot")}
                icon={<ImageIcon size={16} />}
              >
                IMAGE
              </PanelTab>
            )}
            {showPanelToggle && (
              <PanelTab
                active={effectiveTab === "decklist"}
                onClick={() => setTab("decklist")}
                icon={<TbCards size={17} />}
              >
                <span className="lg:hidden">POOL</span>
                <span className="hidden lg:inline">CARD POOL</span>
              </PanelTab>
            )}
            {!hideDraftLog && (
              <PanelTab
                disabled={!draftLogHref}
                onClick={draftLogHref ? () => navigate(draftLogHref) : undefined}
                icon={<LuScrollText size={16} />}
              >
                <span className="lg:hidden">LOG</span>
                <span className="hidden lg:inline">DRAFT LOG</span>
              </PanelTab>
            )}
          </div>
          {onNext ? <PanelChevron side="right" onClick={onNext} /> : hasTabs ? <span className="w-10 shrink-0" /> : null}
        </div>
        )}
        {breakdownHref && (
          <Link
            to={breakdownHref}
            onClick={(e) => e.stopPropagation()}
            aria-label="View breakdown"
            className="lg:hidden self-end inline-flex items-center gap-1.5 pr-1 text-green hover:text-green/80 no-underline font-display tracking-[0.18em] leading-none"
            style={{ fontSize: 13 }}
          >
            VIEW BREAKDOWN
            <ArrowRight size={13} />
          </Link>
        )}
      </div>
    </div>,
    document.body,
  );
}

function CopyDeckButton({ mainboard, className }: { mainboard: Mainboard; className?: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(arenaDeckText(mainboard));
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      aria-label="Copy deck to clipboard"
      className={cn(
        "shrink-0 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface2 px-3 py-1.5 font-display tracking-[0.14em] leading-none text-subtle hover:text-text hover:border-green/50 transition-colors cursor-pointer outline-none focus:outline-none focus-visible:outline-none",
        className,
      )}
      style={{ fontSize: 13 }}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
      {copied ? "COPIED" : "COPY DECK"}
    </button>
  );
}

function arenaDeckText(mainboard: Mainboard): string {
  const lines = ["Deck", ...mainboard.cards.map((card) => arenaCardLine(card, mainboard.set))];
  if (mainboard.sideboard.length > 0) {
    lines.push("", "Sideboard", ...mainboard.sideboard.map((card) => arenaCardLine(card, mainboard.set)));
  }
  return lines.join("\n");
}

function arenaCardLine(card: DeckCard, deckSet: string | null): string {
  const set = card.set ?? deckSet;
  const line = `${card.count ?? 1} ${card.name}`;
  if (!set || !card.cn) {
    return line;
  }
  return `${line} (${set.toUpperCase()}) ${card.cn}`;
}

function PanelChevron({ side, onClick }: { side: "left" | "right"; onClick: () => void }) {
  const Chevron = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      aria-label={side === "left" ? "Previous deck" : "Next deck"}
      className="shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-full bg-surface2 border border-border text-muted hover:text-text hover:border-border2 transition-colors cursor-pointer outline-none focus:outline-none focus-visible:outline-none"
    >
      <Chevron size={22} strokeWidth={2.25} />
    </button>
  );
}

function PanelTab({
  active = false,
  onClick,
  disabled = false,
  icon,
  children,
}: {
  active?: boolean;
  onClick?: () => void;
  disabled?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-2 lg:px-4 lg:py-2.5 font-display tracking-[0.14em] leading-none transition-colors",
        "outline-none focus:outline-none focus-visible:outline-none",
        disabled
          ? "bg-surface2 text-subtle border-border opacity-50 cursor-not-allowed"
          : active
            ? "bg-green/15 text-green border-green/50 cursor-pointer"
            : "bg-surface2 text-muted border-border hover:text-text cursor-pointer",
      )}
      style={{ fontSize: 14 }}
    >
      <span className="relative inline-flex items-center justify-center">
        {icon}
        {disabled && (
          <span
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 h-[1.5px] w-[150%] -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-full bg-current"
          />
        )}
      </span>
      {children}
    </button>
  );
}

type DeckCard = Mainboard["cards"][number];

const STRIP_H = 30;
const BADGE_H = 28;
const COL_MIN = 132;
const COL_MAX = 220;
const SIDEBOARD_WIDTH = 168;

// true groups copies into one card with a ×N badge (17lands style); false renders every copy as its
// own card. Kept as a constant so both treatments are easy to compare.
const GROUP_DUPLICATE_CARDS = false;

function expandDuplicates(cards: DeckCard[]): DeckCard[] {
  if (GROUP_DUPLICATE_CARDS) {
    return cards;
  }
  return cards.flatMap((card) => Array.from({ length: card.count ?? 1 }, () => ({ ...card, count: 1 })));
}

const COLOR_RANK: Record<string, number> = { W: 0, U: 1, B: 2, R: 3, G: 4 };

function isLand(type: string | null): boolean {
  return /land/i.test(type ?? "");
}

function colorSortKey(colors: string[]): number {
  if (colors.length === 0) return 7;
  if (colors.length > 1) return 5;
  return COLOR_RANK[colors[0]] ?? 6;
}

function byColorThenName(a: DeckCard, b: DeckCard): number {
  return colorSortKey(a.colors ?? []) - colorSortKey(b.colors ?? []) || a.name.localeCompare(b.name);
}

function DecklistView({ mainboard, warmedImages }: { mainboard: Mainboard; warmedImages?: CardImages }) {
  const [showSide, setShowSide] = useState(true);
  const imageItems = useMemo(
    () =>
      warmedImages ? [] : [...mainboard.cards, ...mainboard.sideboard].map((c) => ({ name: c.name, set: c.set ?? mainboard.set })),
    [mainboard, warmedImages],
  );
  const ownImages = useCardImageMap(imageItems);
  const cardImages = warmedImages ?? ownImages;
  const { mvPiles, lands, side } = useMemo(() => {
    const landCards: DeckCard[] = [];
    const byCmc = new Map<number, DeckCard[]>();
    for (const card of expandDuplicates(mainboard.cards)) {
      if (isLand(card.type)) {
        landCards.push(card);
        continue;
      }
      const cmc = card.cmc ?? 0;
      const pile = byCmc.get(cmc);
      if (pile) {
        pile.push(card);
      } else {
        byCmc.set(cmc, [card]);
      }
    }
    const piles = [...byCmc.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([cmc, cards]) => ({ cmc, cards: cards.slice().sort(byColorThenName) }));
    return {
      mvPiles: piles,
      lands: landCards.slice().sort(byColorThenName),
      side: expandDuplicates(mainboard.sideboard).sort(byColorThenName),
    };
  }, [mainboard]);
  const hasSide = side.length > 0;

  return (
    <CardImageMapProvider value={cardImages}>
    <div className="relative h-full flex min-h-0">
      <div className="relative flex-1 min-w-0 overflow-auto themed-scrollbar px-4 md:px-5 py-5">
        <div className="flex gap-2 md:gap-3 items-start">
          {mvPiles.map((pile) => (
            <Pile key={pile.cmc} cards={pile.cards} deckSet={mainboard.set} />
          ))}
          {lands.length > 0 && <Pile cards={lands} deckSet={mainboard.set} />}
        </div>
      </div>
      {hasSide && !showSide && (
        <button
          type="button"
          onClick={() => setShowSide(true)}
          className="absolute top-3 right-3 z-10 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface2 px-3 py-1.5 font-display tracking-[0.14em] text-subtle hover:text-text hover:border-green/50 transition-colors cursor-pointer"
          style={{ fontSize: 13 }}
        >
          <ChevronLeft size={15} />
          SIDEBOARD {side.length}
        </button>
      )}
      {hasSide && showSide && (
        <aside className="shrink-0 flex flex-col min-h-0 border-l border-border bg-surface/60" style={{ width: SIDEBOARD_WIDTH }}>
          <button
            type="button"
            onClick={() => setShowSide(false)}
            className="flex items-center gap-2 px-3 py-2.5 border-b border-border font-display tracking-[0.16em] text-text hover:text-green transition-colors cursor-pointer"
            style={{ fontSize: 15 }}
          >
            <span>SIDEBOARD</span>
            <span className="ml-auto tabular-nums">{side.length}</span>
            <ChevronRight size={18} />
          </button>
          <div className="flex-1 overflow-auto themed-scrollbar px-3 py-3">
            <Pile cards={side} deckSet={mainboard.set} />
          </div>
        </aside>
      )}
    </div>
    </CardImageMapProvider>
  );
}

const CARD_CLASS =
  "w-full overflow-hidden rounded-[4.5%/3.2%] [outline-style:solid] outline-1 -outline-offset-1 outline-white/10 shadow-[0_-2px_6px_rgba(0,0,0,0.6)] transition-[outline-color] group-hover:outline-white/50 hover:outline-white/50";

// Cards fan top-to-bottom with each one absolutely overlapping the previous, so only a revealed sliver
// of the upper cards shows and their bottom edge is covered — the bottom card sits in normal flow and
// gives the column its height. Hovering a sliver lifts that card to the front.
function Pile({ cards, deckSet }: { cards: DeckCard[]; deckSet: string | null }) {
  if (cards.length === 0) {
    return null;
  }
  return (
    <div className="flex-1" style={{ minWidth: COL_MIN, maxWidth: COL_MAX }}>
      <StackColumn
        count={cards.length}
        reveal={STRIP_H}
        cardClassName={CARD_CLASS}
        renderCard={(i) => <PileCard card={cards[i]} deckSet={deckSet} />}
      />
    </div>
  );
}

function PileCard({ card, deckSet }: { card: DeckCard; deckSet: string | null }) {
  const imageMap = useCardImageMapContext();
  const set = card.set ?? deckSet;
  const sources = useMemo(() => cardImageSources(card.name, set, imageMap), [card.name, set, imageMap]);
  const { src, onError } = useFallbackImage(sources);
  const count = card.count ?? 1;
  return (
    <>
      {src ? (
        <img
          key={src}
          src={src}
          alt={card.name}
          loading="lazy"
          onError={onError}
          className="block w-full h-auto"
          draggable={false}
        />
      ) : imageMap.ready ? (
        <div className="w-full aspect-[488/680] bg-surface2 flex items-start p-2">
          <span className="font-body text-subtle leading-tight" style={{ fontSize: 12 }}>{card.name}</span>
        </div>
      ) : (
        <div className="w-full aspect-[488/680] bg-surface2 animate-pulse" />
      )}
      {count > 1 && <CountBadge n={count} onStrip={false} />}
    </>
  );
}

// On a revealed strip the badge sits centered in the visible sliver; on the fully shown bottom card it
// pins to the top-right corner so it reads as a count chip instead of floating over the card art.
function CountBadge({ n, onStrip }: { n: number; onStrip: boolean }) {
  return (
    <span
      className="absolute right-1.5 inline-flex items-center justify-center bg-black/85 text-white font-display tabular-nums rounded px-2 leading-none"
      style={{ fontSize: 17, height: BADGE_H, top: onStrip ? (STRIP_H - BADGE_H) / 2 : 6, letterSpacing: "0.04em" }}
    >
      ×{n}
    </span>
  );
}
