import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Maximize2, Trophy, X } from "lucide-react";

import { LuScrollText } from "../../Icons";
import { Pips } from "../../ManaPips";
import { podDraftLogHref } from "../../pod/podLinks";
import { cn } from "../../../lib/utils";
import { useResolvedDeckUrl } from "../../../data/refresh-deck-url";
import { TROPHY_RECORD, type TrophyMageDeck, type TrophyRecord } from "../../../data/trophyMage";
import { useDialogKeys } from "../GameChrome";
import { DARK_PIXEL_BUTTON, HARD_TEXT_SHADOW } from "../pixelStyles";
import { CallTag, RevealChip } from "./RecordChip";
import { SpriteStrip, TROPHY_SPRITE } from "./SpriteStrip";

export interface DeckReveal {
  crowned: boolean;
  delayMs: number;
}

export function DeckTile({
  deck,
  name,
  eventId,
  eventSlug,
  call,
  reveal,
  selected = false,
  compact = false,
  onActivate,
  overlay,
  className,
}: {
  deck: TrophyMageDeck;
  name: string;
  eventId: string;
  eventSlug: string;
  call: TrophyRecord | null;
  reveal: DeckReveal | null;
  selected?: boolean;
  compact?: boolean;
  onActivate?: () => void;
  overlay?: ReactNode;
  className?: string;
}) {
  const { url, resolving } = useResolvedDeckUrl({
    deckScreenshotUrl: deck.deckScreenshotUrl,
    eventId,
    displayName: deck.displayName,
    participantDisplayName: deck.participantDisplayName,
  });
  const [enlarged, setEnlarged] = useState(false);
  const isTrophy = deck.record === TROPHY_RECORD;
  const showTrophy = reveal != null && isTrophy;
  const trophyMoment = showTrophy && reveal.crowned;
  const delayStyle = reveal ? { animationDelay: `${reveal.delayMs}ms` } : undefined;
  const interactive = onActivate != null;

  return (
    <div
      data-deck-key={deck.key}
      className={cn(
        "group/deck relative flex min-h-0 min-w-0 flex-col border-[3px] border-[color:var(--px-ink)]",
        "bg-[color:var(--px-well)] shadow-[inset_0_0_0_2px_var(--px-well-rim),5px_5px_0_#05070a]",
        "transition-[box-shadow,transform,opacity] duration-200",
        interactive && "cursor-pointer hover:shadow-[inset_0_0_0_2px_var(--px-accent),5px_5px_0_#05070a]",
        compact && !selected && "opacity-60 hover:opacity-100",
        selected && "-translate-y-1 shadow-[0_0_0_3px_var(--px-accent),5px_5px_0_#05070a]",
        trophyMoment && "animate-scoredGlow shadow-[0_0_0_4px_#f6c95e,0_0_32px_8px_rgba(246,201,94,0.55)]",
        className,
      )}
      style={trophyMoment ? delayStyle : undefined}
      onClick={interactive ? onActivate : undefined}
    >
      <div className="relative min-h-0 flex-1">
        {url ? (
          <div className={cn("absolute inset-0", !compact && "max-lg:overflow-x-auto max-lg:overscroll-x-contain")}>
            <img
              src={url}
              alt={name}
              draggable={false}
              className={cn("size-full select-none object-contain p-1", !compact && "max-lg:w-auto max-lg:max-w-none")}
            />
          </div>
        ) : (
          <div className="absolute inset-0 grid place-items-center text-base text-subtle">
            {resolving ? "Loading Deck" : "Deck Screenshot Missing"}
          </div>
        )}
        {trophyMoment && !compact && <TrophyBurst delayMs={reveal.delayMs} />}
      </div>
      {compact && (reveal || call) && (
        <span className="absolute right-1.5 bottom-1.5 text-sm lg:right-2 lg:bottom-2 lg:text-lg">
          {reveal ? (
            <RevealChip call={call} actual={deck.record} short style={delayStyle} />
          ) : (
            call && <CallTag record={call} className="animate-stamp" />
          )}
        </span>
      )}
      {deck.deckColors && (
        <span
          className={cn(
            "absolute flex items-center border-2 border-[color:var(--px-ink)]",
            "bg-[color:var(--px-panel-glass)] shadow-[2px_2px_0_#05070a]",
            compact ? "top-1.5 left-1.5 h-7 px-1" : "top-2 left-2 h-8 px-1.5",
          )}
        >
          <Pips colors={deck.deckColors} size={15} />
        </span>
      )}
      {url && !compact && (
        <button
          type="button"
          aria-label={`Enlarge ${name}`}
          onClick={(event) => {
            event.stopPropagation();
            setEnlarged(true);
          }}
          className={cn(
            "absolute right-2 bottom-2 z-10 grid size-9 place-items-center border-2 border-[color:var(--px-ink)]",
            "bg-[color:var(--px-panel-glass)] text-text shadow-[2px_2px_0_#05070a] hover:text-[color:var(--px-accent)]",
          )}
        >
          <Maximize2 size={15} strokeWidth={2.5} />
        </button>
      )}
      {showTrophy && !compact && <TrophyPlate deck={deck} eventSlug={eventSlug} delayMs={reveal.delayMs} />}
      {overlay && <div className="absolute inset-x-0 bottom-3 flex justify-center">{overlay}</div>}
      {enlarged && url && <DeckZoom src={url} alt={name} onClose={() => setEnlarged(false)} />}
    </div>
  );
}

function DeckZoom({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  useDialogKeys(true, onClose);
  return createPortal(
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-[#05070a]/85 p-3 animate-fadeIn sm:p-6"
      onClick={(event) => {
        event.stopPropagation();
        onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={alt}
    >
      <img
        src={src}
        alt={alt}
        className="max-h-full max-w-full border-[3px] border-[#05070a] object-contain shadow-[6px_6px_0_#05070a]"
      />
      <button aria-label="Close" className={cn(DARK_PIXEL_BUTTON, "game-theme-ice absolute top-4 right-4 size-10")}>
        <X size={20} />
      </button>
    </div>,
    document.body,
  );
}

function TrophyBurst({ delayMs }: { delayMs: number }) {
  return (
    <span
      className="pointer-events-none absolute inset-0 grid place-items-center overflow-hidden animate-fadeOut"
      style={{ animationDelay: `${delayMs + 2400}ms`, animationDuration: "500ms" }}
    >
      <span
        className={cn(
          "absolute size-[150%] animate-fadeIn opacity-60",
          "bg-[repeating-conic-gradient(from_0deg,rgba(246,201,94,0.35)_0deg_10deg,transparent_10deg_30deg)]",
          "[mask-image:radial-gradient(circle,black_10%,transparent_55%)]",
        )}
        style={{ animationDelay: `${delayMs}ms` }}
      />
      <span
        className="relative animate-stamp drop-shadow-[6px_6px_0_#05070a]"
        style={{ animationDelay: `${delayMs + 120}ms` }}
      >
        <SpriteStrip sheet={TROPHY_SPRITE} scale={7} restMs={1200} />
      </span>
    </span>
  );
}

function TrophyPlate({ deck, eventSlug, delayMs }: { deck: TrophyMageDeck; eventSlug: string; delayMs: number }) {
  const href = podDraftLogHref(eventSlug, { playerSlug: deck.playerSlug, seatIndex: deck.seatIndex });
  return (
    <span
      className="absolute inset-x-2 bottom-2 flex justify-center animate-fadeUpIn"
      style={{ animationDelay: `${delayMs + 200}ms` }}
    >
      <span
        className={cn(
          "flex max-w-full items-center gap-2 border-2 border-[color:var(--px-ink)] bg-[color:var(--px-panel)] px-2.5 py-1.5",
          "text-base font-semibold shadow-[3px_3px_0_#05070a]",
        )}
      >
        <Trophy size={16} className="shrink-0 text-[#f6c95e]" />
        {deck.deckColors && <Pips colors={deck.deckColors} size={15} />}
        <span className={cn("truncate text-text", HARD_TEXT_SHADOW)}>{deck.displayName}</span>
        <a
          href={href}
          target="_blank"
          rel="noopener"
          onClick={(event) => event.stopPropagation()}
          className="flex shrink-0 items-center gap-1 text-[color:var(--px-accent)] hover:underline"
        >
          <LuScrollText size={15} aria-hidden="true" />
          Draft Log
        </a>
      </span>
    </span>
  );
}
