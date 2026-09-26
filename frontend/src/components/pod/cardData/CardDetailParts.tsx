import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { AVATAR_CLIP, Trophy } from "../../Brand";
import { ChevronLeft, ChevronRight } from "../../Icons";
import { Pips } from "../../ManaPips";
import { Record } from "../../Record";
import { SectionLabel } from "../../SectionLabel";
import { Tooltip } from "../../Tooltip";
import { podShortName } from "../../PodRecentTrophies";
import { DeckScreenshotModal } from "../DeckScreenshotModal";
import { onPlainClick, podDeckHref, podDraftLogHref, podSeatHref } from "../podLinks";
import { CARD_FRAME } from "../review/ReviewCard";
import { RevealImage } from "../../RevealImage";
import { useCursorTooltip, type CursorTooltipBinding } from "../../CursorTooltip";
import { cn } from "../../../lib/utils";
import { cardArtSources, useCardImageMap } from "../../../data/cardImages";
import { colorsDisplayName } from "../../../data/filters";
import { mainColors } from "../../../data/utils";
import { resolveDeck } from "../../../data/draft-artifact";
import { usePodCardDecks, usePodDeckCards, usePodDraftArtifact } from "../../../data/hooks";
import {
  PICKS_PER_PACK,
  adaptPodCardDeck,
  cardSlug,
  coPlayedCards,
  sortDecksRecentFirst,
  summarizeCardDecks,
  type CoPlayedCard,
  type PodCardDeck,
  type PodCardSummary,
} from "../../../data/podCardDecks";

export interface CardDetail {
  decks: PodCardDeck[];
  summary: PodCardSummary;
  isPending: boolean;
}

export function useCardDetail(boardCode: string, cardName: string | undefined, season: string | null): CardDetail {
  const { data, isPending } = usePodCardDecks(boardCode, cardName);
  return useMemo(() => {
    const scoped = (data ?? []).filter((row) => season == null || row.season === season);
    const decks = sortDecksRecentFirst(scoped.map(adaptPodCardDeck));
    return { decks, summary: summarizeCardDecks(decks), isPending };
  }, [data, season, isPending]);
}

export function useCoPlayed(detail: CardDetail, cardName: string): { cards: CoPlayedCard[]; isPending: boolean } {
  const eventIds = useMemo(() => {
    const ids = new Set<string>();
    for (const deck of detail.decks) {
      if (deck.maindecked) {
        ids.add(deck.eventId);
      }
    }
    return [...ids].sort();
  }, [detail.decks]);
  const { data, isPending } = usePodDeckCards(eventIds);
  const cards = useMemo(() => coPlayedCards(data ?? [], detail.decks, cardName), [data, detail.decks, cardName]);
  return { cards, isPending: detail.isPending || (eventIds.length > 0 && isPending) };
}

export function cardDataHref(boardCode: string, cardName: string | null, search: string): string {
  const base = `/pods/${boardCode}/data`;
  return `${cardName ? `${base}/${cardSlug(cardName)}` : base}${search}`;
}

const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);


export function PickCurve({
  curve,
  ata,
  alsa,
  height = 84,
}: {
  curve: number[];
  ata: number | null;
  alsa: number | null;
  height?: number;
}) {
  let peak = 0;
  for (const count of curve) {
    peak = Math.max(peak, count);
  }
  return (
    <div>
      <SectionHeader title="PICK ORDER">
        <span className="flex items-center gap-3 font-mono text-[11px] whitespace-nowrap">
          {alsa != null && <span className="text-purple">ALSA {alsa.toFixed(2)}</span>}
          {ata != null && <span className="text-blue">ATA {ata.toFixed(2)}</span>}
        </span>
      </SectionHeader>
      <div
        className="relative grid items-end gap-[3px]"
        style={{ gridTemplateColumns: `repeat(${PICKS_PER_PACK}, minmax(0, 1fr))`, height }}
      >
        {curve.map((count, i) => {
          const ratio = peak > 0 ? count / peak : 0;
          const fillHeight = `${Math.max(ratio * 100, 8)}%`;
          return (
            <Tooltip key={i} label={pickTooltip(count, i + 1)} side="top">
              <div className="relative h-full bg-surface2">
                {count > 0 && (
                  <div
                    className="absolute inset-x-0 bottom-0 bg-green"
                    style={{ height: fillHeight, opacity: 0.35 + ratio * 0.65 }}
                  />
                )}
                {count > 0 && (
                  <span
                    className={cn(
                      "absolute inset-x-0 z-20 text-center font-num font-semibold text-[11px] leading-none text-white",
                      "[text-shadow:0_0_2px_#0a0c10,0_0_2px_#0a0c10,0_0_1px_#0a0c10]",
                      ratio > 0.5 && "top-1.5",
                    )}
                    style={ratio > 0.5 ? undefined : { bottom: `calc(${fillHeight} + 4px)` }}
                  >
                    {count}
                  </span>
                )}
              </div>
            </Tooltip>
          );
        })}
        <PickMarker average={alsa} className="bg-purple" />
        <PickMarker average={ata} className="bg-blue" />
      </div>
      <div
        className="mt-1 grid h-4 gap-[3px] font-num text-[10px] leading-4 text-dim text-center"
        style={{ gridTemplateColumns: `repeat(${PICKS_PER_PACK}, minmax(0, 1fr))` }}
      >
        {curve.map((_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
    </div>
  );
}

function PickMarker({ average, className }: { average: number | null; className: string }) {
  if (average == null) {
    return null;
  }
  const slotsBefore = Math.min(Math.max(average, 1), PICKS_PER_PACK) - 1;
  const gapTotal = (PICKS_PER_PACK - 1) * 3;
  const slotWidth = `((100% - ${gapTotal}px) / ${PICKS_PER_PACK})`;
  const left = `calc(${slotsBefore} * (${slotWidth} + 3px) + ${slotWidth} / 2)`;
  return (
    <span
      className={cn(
        "pointer-events-none absolute inset-y-0 z-10 w-0.5 -translate-x-1/2 shadow-[0_0_0_1px_rgba(10,12,16,0.6)]",
        className,
      )}
      style={{ left }}
      aria-hidden
    />
  );
}

function pickTooltip(count: number, pick: number): string {
  const ordinal = ordinalOf(pick);
  if (count === 0) {
    return `Never taken ${ordinal}`;
  }
  return `Taken ${ordinal} in ${count} ${count === 1 ? "draft" : "drafts"}`;
}

function ordinalOf(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

function SectionHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-1.5 flex h-6 items-center justify-between gap-3">
      <SectionLabel size={14} className="text-subtle">{title}</SectionLabel>
      {children}
    </div>
  );
}

type DeckFilter = "played" | "sideboard";

const DECK_GRID = cn(
  "grid items-center gap-x-3",
  "grid-cols-[var(--pips)_minmax(0,1fr)_40px_58px]",
  "sm:grid-cols-[var(--pips)_minmax(0,1fr)_84px_40px_58px]",
  "2xl:grid-cols-[var(--pips)_minmax(0,1fr)_84px_64px_58px]",
);

function pipsColumn(colorStrings: Array<string | null>, pipSize = 10): React.CSSProperties {
  let widest = 2;
  for (const colors of colorStrings) {
    widest = Math.max(widest, mainColors(colors).length);
  }
  return { "--pips": `${widest * (pipSize + 4)}px` } as React.CSSProperties;
}

function deckCount(n: number): string {
  return `${n} ${n === 1 ? "DECK" : "DECKS"}`;
}

export function CardDeckList({
  decks,
  isPending,
  onOpen,
  pageSize = 8,
  reserveRows = true,
  hoverTips = true,
  footerStart,
  className,
}: {
  decks: PodCardDeck[];
  isPending: boolean;
  onOpen: (deck: PodCardDeck) => void;
  pageSize?: number;
  reserveRows?: boolean;
  hoverTips?: boolean;
  footerStart?: React.ReactNode;
  className?: string;
}) {
  const deckTooltip = useCursorTooltip();
  const [filter, setFilter] = useState<DeckFilter>("played");
  const [page, setPage] = useState(0);
  const played = decks.filter((d) => d.maindecked);
  const sideboarded = decks.filter((d) => !d.maindecked);
  const rows = filter === "played" ? played : sideboarded;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const start = page * pageSize;
  const shown = rows.slice(start, start + pageSize);
  const emptyText = filter === "played" ? "NO DECKS YET" : "NO DECK HAS SIDEBOARDED IT";
  const showFilter = (next: DeckFilter) => {
    setFilter(next);
    setPage(0);
  };

  return (
    <div className={cn("flex flex-col", className)} style={pipsColumn(shown.map((d) => d.deckColors))}>
      <SectionHeader title="RECENT DECKS">
        <div className="flex items-center gap-1">
          <DeckFilterTab active={filter === "played"} onClick={() => showFilter("played")}>
            MAINDECK {isPending ? "" : played.length}
          </DeckFilterTab>
          <DeckFilterTab active={filter === "sideboard"} onClick={() => showFilter("sideboard")}>
            SIDEBOARD {isPending ? "" : sideboarded.length}
          </DeckFilterTab>
        </div>
      </SectionHeader>
      {Array.from({ length: slotCount(reserveRows, pageSize, shown.length) }, (_, i) => {
        const deck = shown[i];
        if (deck) {
          return (
            <CardDeckRow
              key={`${deck.eventId}|${deck.seat}`}
              deck={deck}
              first={i === 0}
              tooltip={hoverTips ? deckTooltip.bind("View Deck") : undefined}
              onOpen={onOpen}
            />
          );
        }
        const note = i === 0 ? (isPending ? "LOADING…" : emptyText) : null;
        return <ReservedRow key={`reserved-${i}`} first={i === 0} note={note} pulse={isPending} />;
      })}
      <div className="mt-auto flex items-center justify-end gap-2 border-t border-border pt-1.5">
        {footerStart && <div className="mr-auto">{footerStart}</div>}
        <PagerButton dir="prev" disabled={page === 0} onClick={() => setPage((p) => Math.max(p - 1, 0))} />
        <span className={cn("min-w-[40px] text-center font-num text-[13px] text-subtle", pageCount < 2 && "invisible")}>
          {page + 1} / {pageCount}
        </span>
        <PagerButton
          dir="next"
          disabled={page >= pageCount - 1}
          onClick={() => setPage((p) => Math.min(p + 1, pageCount - 1))}
        />
      </div>
      {deckTooltip.layer}
    </div>
  );
}

const DECK_ROW_H = "h-[36px]";

function slotCount(reserveRows: boolean, reserved: number, filled: number): number {
  return reserveRows ? reserved : Math.max(filled, 1);
}

function ReservedRow({
  first,
  note,
  pulse,
  height = DECK_ROW_H,
}: {
  first: boolean;
  note: string | null;
  pulse: boolean;
  height?: string;
}) {
  return (
    <div className={cn(height, "flex items-center", first ? "" : "border-t border-border/40")}>
      {note ? (
        <span className="font-mono text-[11px] text-muted">{note}</span>
      ) : pulse ? (
        <span className="h-2.5 w-2/3 bg-surface2 animate-pulse" />
      ) : null}
    </div>
  );
}

function PagerButton({ dir, disabled, onClick }: { dir: "prev" | "next"; disabled: boolean; onClick: () => void }) {
  const Chevron = dir === "prev" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={dir === "prev" ? "Previous decks" : "Next decks"}
      className="flex h-7 w-7 items-center justify-center border border-white/40 bg-surface2 text-text transition-colors hover:border-white/70 hover:bg-white/10 disabled:opacity-25 disabled:hover:border-white/40 disabled:hover:bg-surface2"
    >
      <Chevron size={15} strokeWidth={2.5} />
    </button>
  );
}

function DeckFilterTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "border px-2 py-1 font-display text-[11px] tracking-[0.14em] leading-none transition-colors",
        active ? "border-green text-green" : "border-border text-muted hover:text-text",
      )}
    >
      {children}
    </button>
  );
}

function CardDeckRow({
  deck,
  first,
  tooltip,
  onOpen,
}: {
  deck: PodCardDeck;
  first: boolean;
  tooltip?: CursorTooltipBinding;
  onOpen: (deck: PodCardDeck) => void;
}) {
  const podLabel = podShortName(deck.eventDate, deck.eventName);
  return (
    <Link
      to={podDeckHref(deck.eventSlug, deck.displayName, deck.displayName)}
      {...tooltip}
      onClick={onPlainClick(() => onOpen(deck))}
      className={cn(
        DECK_GRID,
        DECK_ROW_H,
        "group w-full -mx-1 px-1 text-left bg-transparent no-underline transition-colors hover:bg-surface2",
        first ? "" : "border-t border-border",
      )}
    >
      <PixelSnappedPips colors={mainColors(deck.deckColors)} size={10} />
      <span className="min-w-0 truncate font-display text-[15px] leading-none tracking-[0.04em]">
        {deck.displayName.toUpperCase()}
      </span>
      <span className="hidden sm:block font-mono text-[11px] text-subtle whitespace-nowrap">{podLabel}</span>
      <PickLabel pack={deck.packNum} pick={deck.pickNum} />
      <span className="flex items-center gap-1.5">
        {deck.record ? (
          <Record centered wins={deck.wins} losses={deck.losses} className="font-num text-[13px] w-full" />
        ) : (
          <span className="w-full text-center font-num text-[13px] text-dim">—</span>
        )}
        <span className="flex w-[13px] shrink-0 justify-end">
          {deck.isTrophy && <Trophy size={13} color="#ffc63a" />}
        </span>
      </span>
    </Link>
  );
}

function PixelSnappedPips({ colors, size }: { colors: string; size: number }) {
  return (
    <span className="inline-flex will-change-transform">
      <Pips colors={colors} size={size} />
    </span>
  );
}

function PickLabel({ pack, pick }: { pack: number | null; pick: number }) {
  const packPrefix = pack == null ? "" : `P${pack} `;
  return (
    <span className="font-mono text-[11px] text-muted whitespace-nowrap">
      <span className="2xl:hidden">{pack == null ? `PICK ${pick}` : `${packPrefix}P${pick}`}</span>
      <span className="hidden 2xl:inline">{`${packPrefix}PICK ${pick}`}</span>
    </span>
  );
}

export function CardColorPairs({
  summary,
  isPending,
  limit = 5,
  reserveRows = true,
}: {
  summary: PodCardSummary;
  isPending: boolean;
  limit?: number;
  reserveRows?: boolean;
}) {
  const rows = summary.colorPairs.slice(0, limit);
  return (
    <div style={pipsColumn(rows.map((pair) => pair.colors), 11)}>
      <SectionHeader title="PLAYED IN">
        {!isPending && <span className="font-mono text-[11px] text-muted">{deckCount(summary.maindecks)}</span>}
      </SectionHeader>
      <div className="border-b border-border">
        {Array.from({ length: slotCount(reserveRows, limit, rows.length) }, (_, i) => {
          const pair = rows[i];
          if (pair) {
            return <ColorPairRow key={pair.colors} pair={pair} maindecks={summary.maindecks} first={i === 0} />;
          }
          const note = i === 0 && isPending ? "LOADING…" : null;
          return <ReservedRow key={`reserved-${i}`} first={i === 0} note={note} pulse={isPending} height={COLOR_ROW_H} />;
        })}
      </div>
    </div>
  );
}

function ColorPairRow({
  pair,
  maindecks,
  first,
}: {
  pair: PodCardSummary["colorPairs"][number];
  maindecks: number;
  first: boolean;
}) {
  const share = maindecks > 0 ? pair.decks / maindecks : 0;
  return (
    <div
      className={cn(
        "grid grid-cols-[var(--pips)_minmax(0,1fr)_auto_44px] gap-x-3 items-center",
        COLOR_ROW_H,
        first ? "" : "border-t border-border",
      )}
    >
      <PixelSnappedPips colors={pair.colors} size={11} />
      <span className="relative font-display text-[14px] tracking-[0.05em] truncate">
        {colorsDisplayName(pair.colors)}
      </span>
      <span className="font-num text-[13px] text-text text-right tabular-nums whitespace-nowrap">
        {pct(share)}
        <span className="ml-1 text-[11px] text-subtle">({pair.decks})</span>
      </span>
      <Record centered wins={pair.wins} losses={pair.losses} className="font-num text-[13px] w-full" />
    </div>
  );
}

const COLOR_ROW_H = "h-[36px]";

export function CoPlayedCards({
  cards,
  isPending,
  boardCode,
  search,
  maindecks,
  limit = 6,
  columns = 3,
  reserveRows = true,
}: {
  cards: CoPlayedCard[];
  isPending: boolean;
  boardCode: string;
  search: string;
  maindecks: number;
  limit?: number;
  columns?: number;
  reserveRows?: boolean;
}) {
  const shown = cards.slice(0, limit);
  const images = useCardImageMap(shown);
  return (
    <div className="flex h-full flex-col">
      <SectionHeader title="PLAYED TOGETHER" />
      <div
        className="grid flex-1 auto-rows-fr gap-x-3"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: slotCount(reserveRows, limit, shown.length) }, (_, i) => {
          const card = shown[i];
          if (!card) {
            const note = i === 0 ? (isPending ? "LOADING…" : "NOTHING YET") : null;
            return (
              <div key={`reserved-${i}`} className="flex min-h-10 items-center">
                {note && <span className="font-mono text-[11px] text-muted">{note}</span>}
              </div>
            );
          }
          const share = maindecks > 0 ? Math.round((card.decks / maindecks) * 100) : null;
          return (
            <Link
              key={card.name}
              to={cardDataHref(boardCode, card.name, search)}
              className="group flex min-h-10 min-w-0 items-center gap-2.5 py-0.5 no-underline text-inherit"
            >
              <span
                className="relative flex min-h-9 w-[60px] shrink-0 self-stretch bg-white/25"
                style={{ clipPath: AVATAR_CLIP }}
              >
                <RevealImage
                  sources={cardArtSources(card.name, card.set, images)}
                  alt={card.name}
                  className="absolute inset-px"
                  style={{ clipPath: AVATAR_CLIP }}
                />
              </span>
              <span className="relative min-w-0">
                <span className="block truncate font-display text-[16px] leading-tight tracking-[0.03em] transition-colors group-hover:text-green">
                  {card.name.split("//")[0].trim()}
                </span>
                {share != null && (
                  <span className="absolute left-0 top-full font-num text-[11px] leading-none text-muted">{share}%</span>
                )}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export function CardDeckModal({
  deck,
  onClose,
  onPrev,
  onNext,
}: {
  deck: PodCardDeck;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  const { data: artifact } = usePodDraftArtifact(deck.eventId);
  const mainboard = useMemo(() => (artifact ? resolveDeck(artifact, deck.seat) : null), [artifact, deck.seat]);
  const seat = { playerSlug: deck.playerSlug, seatIndex: deck.seat };
  return (
    <DeckScreenshotModal
      participant={{
        eventId: deck.eventId,
        displayName: deck.displayName,
        participantDisplayName: deck.participantDisplayName,
        deckColors: deck.deckColors,
        deckScreenshotUrl: deck.deckScreenshotUrl,
        deckScreenshotCaption: deck.deckScreenshotCaption,
        mainboard,
        record: deck.record,
      }}
      breakdownHref={podSeatHref(deck.eventSlug, deck.displayName)}
      draftLogHref={artifact ? podDraftLogHref(deck.eventSlug, seat) : null}
      onClose={onClose}
      onPrev={onPrev}
      onNext={onNext}
    />
  );
}

export function useDeckCycler(decks: PodCardDeck[]) {
  const [open, setOpen] = useState<PodCardDeck | null>(null);
  const played = decks.filter((d) => d.maindecked === (open?.maindecked ?? true));
  const index = open ? played.findIndex((d) => d.eventId === open.eventId && d.seat === open.seat) : -1;
  const step = (dir: number) => {
    if (index < 0 || played.length === 0) {
      return;
    }
    setOpen(played[(index + dir + played.length) % played.length]);
  };
  const modal = open ? (
    <CardDeckModal
      deck={open}
      onClose={() => setOpen(null)}
      onPrev={played.length > 1 ? () => step(-1) : undefined}
      onNext={played.length > 1 ? () => step(1) : undefined}
    />
  ) : null;
  return { openDeck: setOpen, deckOpen: open != null, modal };
}

export function CardArt({ sources, name }: { sources: string[]; name: string }) {
  return <RevealImage sources={sources} alt={name} className="h-9 w-12 max-w-full shrink-0" style={{ clipPath: AVATAR_CLIP }} />;
}

export function CardImageStack({ sources }: { sources: string[] }) {
  return (
    <RevealImage sources={sources} className={`w-full ${CARD_FRAME}`} style={{ aspectRatio: "488 / 680" }} />
  );
}
