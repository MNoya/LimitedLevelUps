import { useState } from "react";
import { ChevronLeft, ChevronRight, Play } from "lucide-react";

import { SetGlyph } from "../../Brand";
import { Tooltip } from "../../Tooltip";
import { cn } from "../../../lib/utils";
import { setShortLabel, type WheelSetOption } from "../../../data/draftGames";
import { scoreTrophyRound, TROPHY_DAILY_ROUNDS, type TrophyMageRound } from "../../../data/trophyMage";
import { DARK_PIXEL_BUTTON, ACCENT_BUTTON, PIXEL_HEADING } from "../pixelStyles";
import { TrophyTitle } from "./TrophyTitle";
import type { TrophyDay } from "./useTrophyDay";

export const DAILY_PLAY = "daily";
const SET_PICKER_LABEL = "Or Select a Set";

export type SlotState = "open" | "won" | "missed";

export interface DaySlot {
  round: TrophyMageRound | null;
  state: SlotState;
}

export interface IntroData {
  dayKey: string;
  dayLabel: string;
  slots: DaySlot[];
  dailyAction: string;
  sets: WheelSetOption[];
  onDaily: () => void;
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
    if (round && calls) {
      state = scoreTrophyRound(round, calls).crowned ? "won" : "missed";
    }
    slots.push({ round, state });
  }
  const played = day ? Object.keys(day.locked).length : 0;
  let dailyAction = "Play";
  if (day && day.advanced >= TROPHY_DAILY_ROUNDS) {
    dailyAction = "Results";
  } else if (played > 0) {
    dailyAction = "Continue";
  }
  return { slots, dailyAction };
}

export function SetPicker({ sets, onPlay }: { sets: WheelSetOption[]; onPlay: (code: string) => void }) {
  const [index, setIndex] = useState(0);
  const set = sets[Math.min(index, sets.length - 1)];
  if (!set) {
    return null;
  }
  const step = (delta: number) => setIndex((i) => (i + delta + sets.length) % sets.length);
  return (
    <div className="flex w-full flex-col items-center gap-2 sm:grid sm:grid-cols-[1fr_auto_1fr] sm:gap-3">
      <span className={cn("text-lg sm:justify-self-end", PIXEL_HEADING)}>{SET_PICKER_LABEL}</span>
      <span className="flex items-center gap-2">
        <button aria-label="Previous Set" onClick={() => step(-1)} className={cn(DARK_PIXEL_BUTTON, "size-10")}>
          <ChevronLeft size={18} strokeWidth={3} />
        </button>
        <Tooltip label={`Play ${set.name}`} side="bottom">
          <button
            onClick={() => onPlay(set.code)}
            className={cn(
              DARK_PIXEL_BUTTON,
              "group h-10 min-w-[120px] px-3 text-lg",
              "hover:bg-[image:var(--px-button)] hover:text-[color:var(--px-ink)]",
            )}
          >
            <SetGlyph code={set.code} size={18} className="text-[#fff1d6] group-hover:text-[color:var(--px-ink)]" />
            {setShortLabel(set.code)}
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

export function PlayButton({ data, className }: { data: IntroData; className?: string }) {
  return (
    <button
      data-play
      onClick={data.onDaily}
      className={cn(ACCENT_BUTTON, "px-10 py-3.5 text-3xl max-sm:text-2xl", className)}
    >
      <Play size={22} className="fill-current" />
      {data.dailyAction}
    </button>
  );
}

export function HelpButton({ onHelp, className }: { onHelp: () => void; className?: string }) {
  return (
    <button onClick={onHelp} className={cn(DARK_PIXEL_BUTTON, "px-4 py-2.5 text-xl max-sm:text-lg", className)}>
      How to Play
    </button>
  );
}

export function ResponsiveTitle() {
  return (
    <>
      <div className="sm:hidden">
        <TrophyTitle scale={3.6} />
      </div>
      <div className="hidden sm:block [@media(max-height:760px)]:hidden">
        <TrophyTitle scale={5} />
      </div>
      <div className="hidden [@media(max-height:760px)]:sm:block">
        <TrophyTitle scale={4} />
      </div>
    </>
  );
}
