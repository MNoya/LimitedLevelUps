import { useEffect, useState, type ReactNode } from "react";
import { Maximize2 } from "lucide-react";

import { Pips } from "../../ManaPips";
import { cn } from "../../../lib/utils";
import type { TrophyMageDeck } from "../../../data/trophyMage";
import { DARK_PIXEL_BUTTON, PIXEL_HEADING } from "../pixelStyles";
import { LoadingLabel } from "../GameChrome";
import { SpriteStrip, TROPHY_SPRITE } from "./SpriteStrip";
import { useDeckImage } from "./useDeckImage";

export type DeckFrame = "idle" | "picked" | "trophy" | "crowned";

export function DeckCard({
  deck,
  name,
  eventId,
  frame,
  footer,
  onLook,
  onReady,
  className,
  imageClassName,
  footerEnd,
  onBarClick,
  banner,
}: {
  deck: TrophyMageDeck;
  name: string;
  eventId: string;
  frame: DeckFrame;
  footer: ReactNode;
  onLook: () => void;
  onReady: () => void;
  className?: string;
  imageClassName?: string;
  footerEnd?: ReactNode;
  onBarClick?: () => void;
  banner?: ReactNode;
}) {
  const { url, resolving } = useDeckImage(deck, eventId);
  const [failed, setFailed] = useState(false);
  const [painted, setPainted] = useState(false);
  const shown = url && !failed;

  useEffect(() => {
    if (!resolving && !url) {
      onReady();
    }
  }, [resolving, url, onReady]);

  return (
    <div
      data-deck-key={deck.key}
      className={cn(
        "relative flex min-h-0 min-w-0 flex-col border-[3px] border-[color:var(--px-ink)]",
        "shadow-[inset_0_0_0_2px_var(--px-well-rim),5px_5px_0_#05070a] transition-[box-shadow] duration-300",
        frame === "picked" && "border-[color:var(--px-accent)]",
        frame === "trophy" && "border-[#f6c95e]",
        frame === "crowned" && "border-[#f6c95e] shadow-[0_0_24px_4px_rgba(246,201,94,0.45),5px_5px_0_#05070a]",
        className,
      )}
    >
      <button
        type="button"
        aria-label={`Look at ${name}`}
        onClick={onLook}
        disabled={!shown}
        className={cn(
          "peer/image relative min-h-0 flex-1 cursor-zoom-in overflow-hidden",
          "bg-[radial-gradient(ellipse_at_50%_20%,rgba(30,60,115,0.1),rgba(8,14,32,0.35)_75%)]",
          imageClassName,
        )}
      >
        {(!shown || !painted) && (
          <span className="absolute inset-0 grid place-items-center">
            {resolving || shown ? (
              <LoadingLabel label="Loading Deck" className="text-xl" />
            ) : (
              <span className={cn("text-xl", PIXEL_HEADING)}>Deck Screenshot Missing</span>
            )}
          </span>
        )}
        {shown && (
          <img
            src={url}
            alt={name}
            draggable={false}
            onLoad={() => {
              setPainted(true);
              onReady();
            }}
            onError={() => {
              setFailed(true);
              onReady();
            }}
            className="absolute inset-0 size-full select-none object-contain lg:object-cover"
          />
        )}
        {frame === "crowned" && <TrophyBurst />}
      </button>
      <div
        onClick={(event) => {
          if (onBarClick && !(event.target as HTMLElement).closest("button, a")) {
            onBarClick();
          }
        }}
        className={cn(
          "group/bar h-11 shrink-0 items-center gap-2 border-t-2 border-[color:var(--px-well-rim)] px-2 pb-[2px]",
          "lg:h-14 lg:px-3",
          "bg-[radial-gradient(ellipse_at_50%_20%,rgba(30,60,115,0.1),rgba(8,14,32,0.35)_75%)]",
          "grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]",
          onBarClick && "cursor-pointer",
        )}
      >
        <span className="flex justify-center">{deck.deckColors && <Pips colors={deck.deckColors} size={18} />}</span>
        <div className="flex min-w-[194px] items-center justify-center gap-1.5 lg:min-w-[242px] 2xl:min-w-[338px]">
          {footer}
        </div>
        <span className="flex shrink-0 items-center justify-end gap-2">
          {footerEnd}
          {shown && (
            <button
              type="button"
              aria-label={`Look at ${name}`}
              tabIndex={-1}
              onClick={onLook}
              className={cn(DARK_PIXEL_BUTTON, "size-8 shrink-0 hover:text-[color:var(--px-accent)] lg:hidden")}
            >
              <Maximize2 size={15} strokeWidth={2.5} />
            </button>
          )}
        </span>
      </div>
      {banner && (
        <span
          className={cn(
            "pointer-events-none absolute bottom-[3.25rem] left-1/2 flex h-12 -translate-x-1/2 items-center",
            "lg:bottom-[4.25rem]",
          )}
        >
          {banner}
        </span>
      )}
      {shown && (
        <button
          type="button"
          aria-label={`Look at ${name}`}
          tabIndex={-1}
          onClick={onLook}
          className={cn(
            DARK_PIXEL_BUTTON,
            "absolute right-3 bottom-[4.25rem] size-12 hover:text-[color:var(--px-accent)] max-lg:hidden",
            "peer-hover/image:-translate-y-0.5 peer-hover/image:text-[color:var(--px-accent)]",
            "peer-hover/image:shadow-[6px_7px_0_#05070a] peer-hover/image:brightness-110",
          )}
        >
          <Maximize2 size={22} strokeWidth={2.5} />
        </button>
      )}
    </div>
  );
}

function TrophyBurst() {
  return (
    <span
      className="pointer-events-none absolute inset-0 grid place-items-center overflow-hidden animate-fadeOut"
      style={{ animationDelay: "1100ms", animationDuration: "400ms" }}
    >
      <span
        className={cn(
          "absolute size-[120%] animate-fadeIn opacity-50",
          "bg-[repeating-conic-gradient(from_0deg,rgba(246,201,94,0.35)_0deg_10deg,transparent_10deg_30deg)]",
          "[mask-image:radial-gradient(circle,black_10%,transparent_55%)]",
        )}
      />
      <span className="relative animate-stamp drop-shadow-[5px_5px_0_#05070a]" style={{ animationDelay: "80ms" }}>
        <SpriteStrip sheet={TROPHY_SPRITE} scale={5} restMs={1200} />
      </span>
    </span>
  );
}
