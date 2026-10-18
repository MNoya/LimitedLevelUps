import { useEffect, useRef, useState, type MouseEvent, type ReactNode, type TouchEvent, type WheelEvent } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

import { Pips } from "../../ManaPips";
import { cn } from "../../../lib/utils";
import type { TrophyMageDeck } from "../../../data/trophyMage";
import { DARK_PIXEL_BUTTON, PIXEL_HEADING } from "../pixelStyles";
import { useDeckImage } from "./useDeckImage";

export function DeckViewer({
  decks,
  index,
  eventId,
  footerFor,
  action,
  onPickKey,
  onPrimary,
  onIndex,
  onClose,
}: {
  decks: TrophyMageDeck[];
  index: number;
  eventId: string;
  footerFor: (deck: TrophyMageDeck) => ReactNode;
  action: ReactNode;
  onPickKey: (key: string) => void;
  onPrimary: () => void;
  onIndex: (index: number) => void;
  onClose: () => void;
}) {
  const deck = decks[index];
  const [zoomed, setZoomed] = useState(() => window.matchMedia("(max-width: 1023px)").matches);
  const step = (delta: number) => onIndex((index + delta + decks.length) % decks.length);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        onClose();
      } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        step(event.key === "ArrowLeft" ? -1 : 1);
      } else if (!event.repeat && !document.activeElement?.matches("button:focus-visible")) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onPrimary();
        } else {
          onPickKey(event.key);
        }
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  return createPortal(
    <div
      className="draft-game game-theme-ice fixed top-0 left-0 z-50 flex h-[100dvh] w-screen flex-col bg-[#05070a]"
      role="dialog"
      aria-modal="true"
      aria-label={`Deck ${index + 1} of ${decks.length}`}
    >
      <div className="relative flex min-h-0 flex-1 flex-col">
        <button
          onClick={onClose}
          aria-label="Close"
          className={cn(DARK_PIXEL_BUTTON, "absolute top-3 right-3 z-10 size-11 lg:top-5 lg:right-5 lg:size-14")}
        >
          <X size={26} strokeWidth={3} />
        </button>
        <ViewerImage
          key={deck.key}
          deck={deck}
          eventId={eventId}
          name={`Deck ${index + 1}`}
          zoomed={zoomed}
          onZoom={setZoomed}
          onSwipe={step}
          onClose={onClose}
        />
        {zoomed && (
          <span className="pointer-events-none absolute inset-y-0 right-0 w-12 bg-gradient-to-l from-[#05070a] lg:hidden" />
        )}
      </div>
      <div
        className={cn(
          "grid shrink-0 gap-2 border-t-2 border-[color:var(--px-well-rim)] bg-[color:var(--px-panel)] px-3 py-2.5",
          "sm:px-5 lg:grid-cols-[1fr_auto_1fr] lg:items-center lg:gap-6 lg:py-4",
        )}
      >
        <div className="flex items-center justify-center gap-5">
          <span className={cn("text-xl lg:text-2xl", PIXEL_HEADING)}>
            Deck {index + 1} of {decks.length}
          </span>
          {deck.deckColors && <Pips colors={deck.deckColors} size={20} />}
        </div>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => step(-1)}
            aria-label="Previous Deck"
            className={cn(DARK_PIXEL_BUTTON, "size-11 shrink-0 lg:size-14")}
          >
            <ChevronLeft size={22} strokeWidth={3} />
          </button>
          <div
            className={cn(
              "flex min-w-0 items-center justify-center gap-2 text-xl max-lg:flex-1 lg:gap-3",
              "lg:[&_button]:h-14 lg:[&_button]:min-w-24 lg:[&_button]:text-3xl",
            )}
          >
            {footerFor(deck)}
          </div>
          <button
            onClick={() => step(1)}
            aria-label="Next Deck"
            className={cn(DARK_PIXEL_BUTTON, "size-11 shrink-0 lg:size-14")}
          >
            <ChevronRight size={22} strokeWidth={3} />
          </button>
        </div>
        <div className="flex lg:justify-self-start lg:pl-4 [&>button]:w-full [&>button]:py-2.5 lg:[&>button]:h-14 lg:[&>button]:w-auto lg:[&>button]:min-w-64">
          {action}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function ViewerImage({
  deck,
  eventId,
  name,
  zoomed,
  onZoom,
  onSwipe,
  onClose,
}: {
  deck: TrophyMageDeck;
  eventId: string;
  name: string;
  zoomed: boolean;
  onZoom: (zoomed: boolean) => void;
  onSwipe: (delta: number) => void;
  onClose: () => void;
}) {
  const { url } = useDeckImage(deck, eventId);
  const scroller = useRef<HTMLDivElement>(null);
  const focus = useRef<{ x: number; y: number } | null>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);

  useEffect(() => {
    const box = scroller.current;
    if (!zoomed || !box || !focus.current) {
      return;
    }
    box.scrollLeft = focus.current.x * box.scrollWidth - box.clientWidth / 2;
    box.scrollTop = focus.current.y * box.scrollHeight - box.clientHeight / 2;
  }, [zoomed]);

  const toggleZoom = (event: MouseEvent<HTMLImageElement>) => {
    if (drag.current?.moved) {
      drag.current = null;
      return;
    }
    if (window.matchMedia("(min-width: 1024px)").matches) {
      onClose();
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    focus.current = { x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height };
    onZoom(!zoomed);
  };
  const onMouseDown = (event: MouseEvent) => {
    const box = scroller.current;
    if (zoomed && box) {
      drag.current = { x: event.clientX, y: event.clientY, left: box.scrollLeft, top: box.scrollTop, moved: false };
    }
  };
  const onMouseMove = (event: MouseEvent) => {
    const start = drag.current;
    const box = scroller.current;
    if (!start || !box || event.buttons !== 1) {
      return;
    }
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    start.moved ||= Math.abs(dx) + Math.abs(dy) > 4;
    box.scrollLeft = start.left - dx;
    box.scrollTop = start.top - dy;
  };
  const onWheel = (event: WheelEvent<HTMLDivElement>) => {
    const box = event.currentTarget;
    const atVerticalEnd =
      event.deltaY > 0 ? box.scrollTop + box.clientHeight >= box.scrollHeight - 1 : box.scrollTop <= 0;
    if (zoomed && atVerticalEnd && Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
      box.scrollLeft += event.deltaY;
    }
  };
  const onTouchStart = (event: TouchEvent) => {
    touchStart.current = { x: event.touches[0].clientX, y: event.touches[0].clientY };
  };
  const onTouchEnd = (event: TouchEvent) => {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start || zoomed) {
      return;
    }
    const dx = event.changedTouches[0].clientX - start.x;
    const dy = event.changedTouches[0].clientY - start.y;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
      onSwipe(dx < 0 ? 1 : -1);
    }
  };

  return (
    <div
      ref={scroller}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onWheel={onWheel}
      className={cn(
        "themed-scrollbar relative min-h-0 flex-1",
        zoomed ? "flex overflow-auto max-lg:items-center" : "overflow-hidden",
      )}
    >
      {url ? (
        <img
          src={url}
          alt={name}
          onClick={toggleZoom}
          draggable={false}
          className={cn(
            "select-none",
            zoomed
              ? "h-[85%] w-auto max-w-none shrink-0 cursor-grab active:cursor-grabbing"
              : "absolute inset-0 size-full cursor-zoom-in object-contain p-2 sm:p-4 lg:cursor-zoom-out",
          )}
        />
      ) : (
        <span className="absolute inset-0 grid place-items-center text-lg text-subtle">Loading Deck</span>
      )}
    </div>
  );
}
