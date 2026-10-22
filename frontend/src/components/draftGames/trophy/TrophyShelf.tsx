import { useState, type CSSProperties, type ReactNode } from "react";

import { cn } from "../../../lib/utils";
import { setShortLabel, shortDayLabel } from "../../../data/draftGames";
import { SetGlyph } from "../../Brand";
import { Trophy } from "lucide-react";

import { DailyCountdown } from "../GameChrome";
import { CONTINUE_ACTION, ENDLESS_ACTION, RESULTS_ACTION } from "../gameDay";
import { DARK_PIXEL_BUTTON, HARD_TEXT_SHADOW, PIXEL_HEADING, PIXEL_TAG } from "../pixelStyles";
import {
  DailyPlayButton,
  HelpButton,
  NEXT_PODS_LABEL,
  ResponsiveTitle,
  SetPicker,
  type DaySlot,
  type IntroData,
} from "./introParts";
import { CLEAN_TROPHY_SPRITE, PixelFrame, SpriteStrip } from "./SpriteStrip";

const SHELF_HEADING = "Today's Showcase";

export function TrophyShowcase({ data }: { data: IntroData }) {
  const [playHovered, setPlayHovered] = useState(false);
  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-[1100px] flex-col items-center pb-4 text-center",
        "max-sm:flex-1 max-sm:pb-0 [@media(max-height:760px)]:pb-0",
      )}
    >
      <ResponsiveTitle />
      <div
        className={cn(
          "mt-7 flex w-full flex-col items-center gap-6 sm:mt-8",
          "[@media(max-height:760px)]:sm:mt-3 [@media(max-height:760px)]:gap-2.5",
          "max-sm:mt-3 max-sm:flex-1 max-sm:justify-evenly max-sm:gap-2.5",
        )}
      >
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
          <span className={cn(PIXEL_TAG, "max-sm:hidden")}>Pod Draft</span>
          <span className={cn("text-2xl font-bold text-text max-sm:text-lg", HARD_TEXT_SHADOW)}>
            Can you guess which decks trophied?
          </span>
        </div>
        <div className="relative flex w-full max-w-[760px] flex-col gap-3 max-sm:gap-2">
          <h2
            className={cn(
              "font-display text-3xl leading-none text-text max-sm:text-2xl [@media(max-height:760px)]:text-2xl",
              HARD_TEXT_SHADOW,
            )}
          >
            <span className={cn("mr-3 text-[0.8em]", PIXEL_HEADING)}>{data.dayLabel}</span>
            {SHELF_HEADING}
          </h2>
          <ShelfCase slots={data.slots} size="large" onRound={data.onRound} lifted={playHovered && !data.dayDone} />
          {data.dayDone && (
            <DailyCountdown
              label={NEXT_PODS_LABEL}
              className="absolute top-full right-0 mt-4 text-base max-sm:mt-3 [&>span]:text-lg"
            />
          )}
        </div>
        <div
          className="grid w-full grid-cols-[1fr_auto_1fr] items-center gap-3"
          onPointerOver={(event) => setPlayHovered((event.target as HTMLElement).closest("[data-play]") != null)}
          onPointerLeave={() => setPlayHovered(false)}
        >
          {data.onResults ? (
            <button
              onClick={data.onResults}
              className={cn(DARK_PIXEL_BUTTON, "justify-self-end px-4 py-2.5 text-xl max-sm:px-3 max-sm:text-lg")}
            >
              <Trophy size={18} strokeWidth={2.5} className="-mt-0.5" />
              {RESULTS_ACTION}
            </button>
          ) : (
            <span />
          )}
          <DailyPlayButton
            data={data}
            className="max-sm:px-8 max-sm:py-2.5 [@media(max-height:760px)]:py-2 [@media(max-height:760px)]:text-2xl"
          />
          <HelpButton
            onHelp={data.onHelp}
            phoneIcon={data.dailyAction === CONTINUE_ACTION || data.dailyAction === ENDLESS_ACTION}
            className="justify-self-start max-sm:px-3"
          />
        </div>
        <div className="grid w-full max-w-[760px] grid-cols-2 gap-4 max-sm:gap-3 [@media(max-height:760px)]:gap-3">
          <PastShelves data={data} />
          <div className="col-span-2 mt-4 max-sm:mt-2 [@media(max-height:760px)]:sm:mt-2">
            <SetPicker sets={data.sets} onPlay={data.onSet} />
          </div>
        </div>
      </div>
    </div>
  );
}

function ShelfCase({
  slots,
  size,
  onRound,
  lifted = false,
}: {
  slots: DaySlot[];
  size: "large" | "small";
  onRound?: (index: number) => void;
  lifted?: boolean;
}) {
  const large = size === "large";
  return (
    <div
      className={cn(
        "relative overflow-hidden border-[4px] border-[color:var(--px-ink)]",
        "bg-[radial-gradient(ellipse_at_50%_20%,rgba(30,60,115,0.1),rgba(8,14,32,0.35)_75%)]",
        "shadow-[inset_0_0_0_3px_var(--px-rim),8px_8px_0_#05070a]",
        "before:pointer-events-none before:absolute before:inset-0 before:content-['']",
        "before:bg-[linear-gradient(115deg,transparent_30%,rgba(190,235,255,0.08)_40%,transparent_50%)]",
        large ? "px-4 pt-6 sm:px-10 [@media(max-height:760px)]:pt-3" : "px-3 pt-3",
      )}
    >
      <div className="relative flex items-end justify-around gap-2">
        {slots.map((slot, i) => (
          <ShelfSpot
            key={slot.round?.eventId ?? i}
            index={i}
            slot={slot}
            large={large}
            lifted={lifted}
            onPlay={onRound ? () => onRound(i) : undefined}
          />
        ))}
      </div>
      <div
        className={cn(
          "relative h-5 border-[3px] border-[#1a120b] bg-[#8a5a2e] shadow-[inset_0_3px_0_#b47b43,0_6px_0_#05070a]",
          large ? "-mx-1 sm:-mx-4" : "h-3",
        )}
      />
      <div className={large ? "h-4 max-sm:h-3 [@media(max-height:760px)]:h-2" : "h-2"} />
    </div>
  );
}

function ShelfSpot({
  index,
  slot,
  large,
  lifted,
  onPlay,
}: {
  index: number;
  slot: DaySlot;
  large: boolean;
  lifted: boolean;
  onPlay?: () => void;
}) {
  const trophy = (scale: number) => <ShelfTrophy index={index} slot={slot} scale={scale} />;
  const trophies = large ? (
    <>
      <span className="sm:hidden">{trophy(5)}</span>
      <span className="hidden sm:block [@media(max-height:760px)]:hidden">{trophy(10)}</span>
      <span className="hidden [@media(max-height:760px)]:sm:block">{trophy(5)}</span>
    </>
  ) : (
    <>
      <span className="sm:hidden [@media(max-height:760px)]:sm:block">{trophy(3)}</span>
      <span className="hidden sm:block [@media(max-height:760px)]:hidden">{trophy(4)}</span>
    </>
  );
  const base = <TrophyBase index={index} slot={slot} small={!large} />;
  if (!onPlay) {
    return (
      <span className="flex flex-col items-center">
        {trophies}
        {base}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={onPlay}
      disabled={!slot.round}
      aria-label={slot.round ? `Play ${setShortLabel(slot.round.setCode)} #${index + 1}` : "Loading"}
      className={cn(
        "relative flex flex-auto flex-col items-center transition-transform duration-200",
        "after:absolute after:-inset-x-1 after:-top-6 after:-bottom-12 after:content-['']",
        "first:after:-left-4 last:after:-right-4 sm:first:after:-left-10 sm:last:after:-right-10",
        "ease-[cubic-bezier(0.34,1.56,0.64,1)] hover:-translate-y-2",
        "hover:drop-shadow-[0_0_18px_rgba(246,201,94,0.55)]",
        lifted && "-translate-y-2 drop-shadow-[0_0_18px_rgba(246,201,94,0.55)]",
      )}
      style={lifted ? { transitionDelay: `${index * 60}ms` } : undefined}
    >
      <span className="flex flex-col items-center">
        {trophies}
        {base}
      </span>
    </button>
  );
}

function ShelfTrophy({ index, slot, scale }: { index: number; slot: DaySlot; scale: number }) {
  const won = slot.state !== "open";
  return (
    <span
      className={cn("relative block", won && "animate-stamp")}
      style={won ? { animationDelay: `${index * 80}ms` } : undefined}
    >
      {won ? (
        <SpriteStrip sheet={CLEAN_TROPHY_SPRITE} scale={scale} restMs={2400 + index * 300} />
      ) : (
        <span className="block brightness-[0.8] saturate-[0.8]">
          <PixelFrame sheet={CLEAN_TROPHY_SPRITE} scale={scale} />
        </span>
      )}
      {slot.round && (
        <span
          className="absolute left-1/2 top-[31%] -translate-x-1/2 -translate-y-1/2 animate-fadeIn"
          style={revealDelay(index)}
        >
          <SetGlyph
            code={slot.round.setCode}
            size={scale * 5}
            className={cn(
              "text-[#fff1d6] drop-shadow-[0_0_1px_#1a120b] drop-shadow-[1px_2px_0_rgba(0,0,0,0.55)]",
              !won && "opacity-[0.85]",
            )}
          />
        </span>
      )}
    </span>
  );
}

function revealDelay(index: number): CSSProperties {
  return { animationDelay: `${index * 120}ms`, animationDuration: "400ms" };
}

function TrophyBase({ index, slot, small }: { index: number; slot: DaySlot; small: boolean }) {
  const label = slot.round ? (
    <span className="animate-fadeIn" style={revealDelay(index)}>
      {setShortLabel(slot.round.setCode)}
    </span>
  ) : (
    <span className="relative inline-block">
      <span className="invisible">FRA</span>
      <span className="absolute inset-x-0 top-[20%] bottom-[25%] animate-pulse bg-[#fff1d6]/35" />
    </span>
  );
  return (
    <span
      className={cn(
        "relative block w-3/4 min-w-max border-2 border-[#1a120b] bg-[linear-gradient(180deg,#b47b43,#7a4e26)]",
        "text-center font-display text-[#fff1d6] [text-shadow:1px_1px_0_#1a120b]",
        "shadow-[inset_0_2px_0_#d99a5b,inset_0_-2px_0_#5a3a1e]",
        small
          ? "px-1 pt-px text-sm/none max-sm:hidden [@media(max-height:760px)]:sm:hidden"
          : "px-2 pt-px pb-[3px] text-lg/none",
      )}
    >
      {label}
    </span>
  );
}

function PastShelves({ data }: { data: IntroData }) {
  return (
    <>
      {data.pastDays.map(({ dayKey, slots }) => (
        <ShelfLabel key={dayKey} label={shortDayLabel(dayKey)}>
          <button
            type="button"
            onClick={() => data.onDay(dayKey)}
            aria-label={`Play ${shortDayLabel(dayKey)}`}
            className={cn(
              "block w-full text-left transition-transform duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
              "hover:-translate-y-1 hover:drop-shadow-[0_0_14px_rgba(246,201,94,0.45)]",
            )}
          >
            <ShelfCase slots={slots} size="small" />
          </button>
        </ShelfLabel>
      ))}
    </>
  );
}

function ShelfLabel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 opacity-90">
      <span className={cn("px-1 text-left text-lg", PIXEL_HEADING)}>{label}</span>
      {children}
    </div>
  );
}
