import { useState } from "react";
import { ChevronLeft, ChevronRight, Play, Trophy } from "lucide-react";

import { SetGlyph } from "../../Brand";
import { Tooltip } from "../../Tooltip";
import { cn } from "../../../lib/utils";
import { setShortLabel, type WheelSetOption } from "../../../data/draftGames";
import { EMPTY_CALLS, scoreTrophyRound, TROPHY_DAILY_ROUNDS, type TrophyMageRound } from "../../../data/trophyMage";
import { dayAction, RESULTS_ACTION } from "../gameDay";
import { LoadingLabel, PlayButton } from "../GameChrome";
import { ResponsiveWordmark } from "../PixelWordmark";
import { DARK_PIXEL_BUTTON, PIXEL_HEADING } from "../pixelStyles";
import { CLEAN_TROPHY_SPRITE, PixelFrame } from "./SpriteStrip";
import { TrophyTitle } from "./TrophyTitle";
import { TROPHY_DAY, type TrophyDay } from "./trophyDay";

export const DAILY_PLAY = "daily";
export const NEXT_PODS_LABEL = "New Pods In";
const SET_PICKER_LABEL = "Or Select a Set";
const LOADING_LINES = ["Pondering Drafts", "Studying Decks", "Polishing Trophies", "Reading Draft Logs"];

export type SlotState = "open" | "won" | "missed";

export interface DaySlot {
  round: TrophyMageRound | null;
  state: SlotState;
  points: number | null;
  max: number;
}

export interface IntroData {
  dayKey: string;
  dayLabel: string;
  slots: DaySlot[];
  dailyAction: string;
  dayDone: boolean;
  pastDays: { dayKey: string; slots: DaySlot[] }[];
  sets: WheelSetOption[];
  onDaily: () => void;
  onResults: (() => void) | null;
  onRound: (index: number) => void;
  onDay: (dayKey: string) => void;
  onSet: (code: string) => void;
  onHelp: () => void;
}

export function dayProgress(
  rounds: TrophyMageRound[],
  day: TrophyDay | null,
): { slots: DaySlot[]; dailyAction: string } {
  const slots: DaySlot[] = [];
  for (let i = 0; i < TROPHY_DAILY_ROUNDS; i++) {
    const round = rounds[i] ?? null;
    const calls = round ? day?.locked[round.eventId] : undefined;
    let state: SlotState = "open";
    let points: number | null = null;
    let max = 0;
    if (round) {
      const score = scoreTrophyRound(round, calls ?? EMPTY_CALLS);
      max = score.max;
      if (calls) {
        state = score.crowned ? "won" : "missed";
        points = score.points;
      }
    }
    slots.push({ round, state, points, max });
  }
  return { slots, dailyAction: dayAction(TROPHY_DAY, day) };
}

export function SetPicker({ sets, onPlay }: { sets: WheelSetOption[]; onPlay: (code: string) => void }) {
  const [index, setIndex] = useState(0);
  const set = sets[Math.min(index, sets.length - 1)];
  const step = (delta: number) => setIndex((i) => (i + delta + sets.length) % sets.length);
  return (
    <div
      aria-hidden={!set}
      className={cn(
        "flex w-full flex-col items-center gap-2 sm:grid sm:grid-cols-[1fr_auto_1fr] sm:gap-3",
        !set && "invisible",
      )}
    >
      <span className={cn("text-lg sm:justify-self-end", PIXEL_HEADING)}>{SET_PICKER_LABEL}</span>
      <span className="flex items-center gap-2">
        <button aria-label="Previous Set" onClick={() => step(-1)} className={cn(DARK_PIXEL_BUTTON, "size-10")}>
          <ChevronLeft size={18} strokeWidth={3} />
        </button>
        <Tooltip label={set ? `Play ${set.name}` : ""} side="bottom">
          <button
            onClick={() => set && onPlay(set.code)}
            className={cn(
              DARK_PIXEL_BUTTON,
              "group h-10 min-w-[120px] px-3 text-lg",
              "hover:bg-[image:var(--px-button)] hover:text-[color:var(--px-ink)]",
            )}
          >
            {set && (
              <>
                <SetGlyph code={set.code} size={18} className="text-[#fff1d6] group-hover:text-[color:var(--px-ink)]" />
                {setShortLabel(set.code)}
              </>
            )}
          </button>
        </Tooltip>
        <button aria-label="Next Set" onClick={() => step(1)} className={cn(DARK_PIXEL_BUTTON, "size-10")}>
          <ChevronRight size={18} strokeWidth={3} />
        </button>
      </span>
      <span className="max-sm:hidden" />
    </div>
  );
}

export function DailyPlayButton({ data, className }: { data: IntroData; className?: string }) {
  const resultsIcon = <Trophy size={22} strokeWidth={2.5} className="-mt-1" />;
  return (
    <PlayButton
      label={data.dailyAction}
      icon={data.dailyAction === RESULTS_ACTION ? resultsIcon : undefined}
      onClick={data.onDaily}
      className={cn("px-10 py-3.5 text-3xl max-sm:text-2xl", className)}
    />
  );
}

export function HelpButton({
  onHelp,
  phoneIcon = false,
  className,
}: {
  onHelp: () => void;
  phoneIcon?: boolean;
  className?: string;
}) {
  return (
    <button
      onClick={onHelp}
      aria-label="How to Play"
      className={cn(
        DARK_PIXEL_BUTTON,
        "px-4 py-2.5 text-xl max-sm:text-lg",
        className,
        phoneIcon && "max-sm:w-12 max-sm:px-0 max-sm:text-2xl",
      )}
    >
      {phoneIcon ? (
        <>
          <span className="sm:hidden">?</span>
          <span className="max-sm:hidden">How to Play</span>
        </>
      ) : (
        "How to Play"
      )}
    </button>
  );
}

export function ResponsiveTitle() {
  return <ResponsiveWordmark wordmark={TrophyTitle} phone={3.6} desktop={5} short={4} />;
}

export function TrophyLoading() {
  const [label] = useState(() => LOADING_LINES[Math.floor(Math.random() * LOADING_LINES.length)]);
  return (
    <div
      className={cn(
        "pointer-events-none fixed inset-x-0 z-[1] flex -translate-y-1/2 justify-center animate-fadeIn",
        "top-[calc(var(--header)+(100dvh-var(--header))*var(--eyes))] [--eyes:0.385] [--header:56px]",
        "lg:[--eyes:0.3] lg:[--header:93px]",
      )}
    >
      <LoadingLabel label={label} className="text-3xl" />
    </div>
  );
}

export function TrophyNotice({ label, onExit }: { label: string; onExit: () => void }) {
  return (
    <div className="flex min-h-[60dvh] flex-col items-center justify-center gap-5 text-center">
      <span className="brightness-[0.75] grayscale drop-shadow-[4px_4px_0_#05070a]">
        <PixelFrame sheet={CLEAN_TROPHY_SPRITE} scale={5} />
      </span>
      <span className={cn("text-2xl", PIXEL_HEADING)}>{label}</span>
      <button onClick={onExit} className={cn(DARK_PIXEL_BUTTON, "px-6 py-2.5 text-xl")}>
        Menu
      </button>
    </div>
  );
}
