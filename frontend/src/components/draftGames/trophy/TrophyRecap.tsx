import { ChevronLeft, Play } from "lucide-react";

import { SetGlyph } from "../../Brand";
import { cn } from "../../../lib/utils";
import { setShortLabel, useWheelSets, gameDayKey } from "../../../data/draftGames";
import {
  callFor,
  EMPTY_CALLS,
  scoreTrophyRound,
  TROPHY_RECORD,
  type TrophyCalls,
  type TrophyMageDeck,
  type TrophyMageRound,
} from "../../../data/trophyMage";
import { ACCENT_BUTTON, DARK_PIXEL_BUTTON, HARD_TEXT_SHADOW } from "../pixelStyles";
import { DailyCountdown } from "../GameChrome";
import { ENDLESS_ACTION, NEXT_DAY_ACTION, NEXT_PODS_LABEL, ResponsiveTitle } from "./introParts";
import { ResultTag } from "./RecordChip";
import { useDeckImage } from "./useDeckImage";
import { nextOpenDay, type TrophyDay } from "./useTrophyDay";

const POINTS_SHORT = "PTs";

export function TrophyRecap({
  rounds,
  day,
  dayKey,
  onReview,
  onPlayDay,
  onPlaySet,
  onExit,
}: {
  rounds: TrophyMageRound[];
  day: TrophyDay;
  dayKey: string | null;
  onReview: (index: number) => void;
  onPlayDay?: (dayKey: string) => void;
  onPlaySet?: (setCode: string) => void;
  onExit: () => void;
}) {
  let points = 0;
  let max = 0;
  for (const round of rounds) {
    const score = scoreTrophyRound(round, day.locked[round.eventId] ?? EMPTY_CALLS);
    points += score.points;
    max += score.max;
  }
  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col items-center pb-4 text-center">
      <ResponsiveTitle />
      <div
        className={cn(
          "mt-7 flex w-full flex-col items-center gap-6 sm:mt-8",
          "[@media(max-height:760px)]:sm:mt-3 [@media(max-height:760px)]:gap-3 max-sm:mt-3 max-sm:gap-4",
        )}
      >
        <DayScoreRow dayKey={dayKey} points={points} max={max} />
        <div
          className={cn(
            "flex w-full max-w-[1040px] flex-col gap-4 max-sm:gap-3",
            "[@media(max-height:760px)]:max-w-[620px] [@media(max-height:760px)]:gap-2",
          )}
        >
          {rounds.map((round, i) => (
            <RecapRow
              key={round.eventId}
              round={round}
              calls={day.locked[round.eventId] ?? EMPTY_CALLS}
              onReview={() => onReview(i)}
            />
          ))}
        </div>
        <DayEndActions dayKey={dayKey} onPlayDay={onPlayDay} onPlaySet={onPlaySet} onExit={onExit} />
      </div>
    </div>
  );
}

export function DayScoreRow({
  dayKey,
  points,
  max,
  pending = false,
  className,
}: {
  dayKey: string | null;
  points: number;
  max: number;
  pending?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex w-full flex-wrap items-center justify-center gap-x-6 gap-y-2", className)}>
      <span
        className={cn("font-display text-3xl leading-none text-[#f6c95e]", HARD_TEXT_SHADOW, pending && "invisible")}
      >
        {points}
        <span className="text-2xl"> of {max} Points</span>
      </span>
      {dayKey === gameDayKey(new Date()) && <DailyCountdown label={NEXT_PODS_LABEL} />}
    </div>
  );
}

function DayEndActions({
  dayKey,
  onPlayDay,
  onPlaySet,
  onExit,
}: {
  dayKey: string | null;
  onPlayDay?: (dayKey: string) => void;
  onPlaySet?: (setCode: string) => void;
  onExit: () => void;
}) {
  const { sets } = useWheelSets();
  const nextDayKey = nextOpenDay(gameDayKey(new Date()), dayKey);
  const newestSet = sets[0]?.code;
  let playNext: (() => void) | null = null;
  if (nextDayKey && onPlayDay) {
    playNext = () => onPlayDay(nextDayKey);
  } else if (!nextDayKey && newestSet && onPlaySet) {
    playNext = () => onPlaySet(newestSet);
  }
  return (
    <div className="flex flex-wrap justify-center gap-3">
      <button onClick={onExit} className={cn(DARK_PIXEL_BUTTON, "py-3.5 pr-10 pl-7 text-3xl")}>
        <ChevronLeft size={24} strokeWidth={3} />
        Menu
      </button>
      {playNext && (
        <button onClick={playNext} className={cn(ACCENT_BUTTON, "px-10 py-3.5 text-3xl")}>
          <Play size={22} className="fill-current" />
          {nextDayKey ? NEXT_DAY_ACTION : ENDLESS_ACTION}
        </button>
      )}
    </div>
  );
}

export const SCORE_LABEL = "Score";

function RecapRow({ round, calls, onReview }: { round: TrophyMageRound; calls: TrophyCalls; onReview: () => void }) {
  const score = scoreTrophyRound(round, calls);
  return (
    <button
      type="button"
      onClick={onReview}
      aria-label={`Review ${setShortLabel(round.setCode)}`}
      className={cn(
        "grid grid-cols-[8rem_minmax(0,1fr)_7rem] items-center gap-5 border-[3px] border-[color:var(--px-ink)] px-5 py-4",
        "bg-[radial-gradient(ellipse_at_50%_20%,rgba(30,60,115,0.1),rgba(8,14,32,0.35)_75%)]",
        "shadow-[inset_0_0_0_2px_var(--px-rim),6px_6px_0_#05070a] transition-transform hover:-translate-y-0.5",
        "max-sm:grid-cols-[minmax(0,1fr)_auto] max-sm:gap-x-2 max-sm:gap-y-2 max-sm:px-2.5 max-sm:py-2",
        "[@media(max-height:760px)]:py-2",
      )}
    >
      <span className="flex flex-col items-center gap-2 max-sm:flex-row max-sm:gap-2.5">
        <span
          className={cn(
            "grid size-14 place-items-center border-2 border-[color:var(--px-ink)] shadow-[2px_2px_0_#05070a]",
            "max-sm:size-10",
            score.crowned
              ? "bg-[linear-gradient(180deg,#fff3cf,#f6c95e_45%,#cf8e2c)] text-[#0b1430]"
              : "bg-[#8a94a8] text-[#0b1430]",
          )}
        >
          <SetGlyph code={round.setCode} size={28} />
        </span>
        <span className="font-display text-2xl leading-none text-text max-sm:text-xl">
          {setShortLabel(round.setCode)}
        </span>
      </span>
      <span className="grid grid-cols-3 gap-4 max-sm:col-span-2 max-sm:row-start-2 max-sm:gap-2">
        {round.decks.map((deck) => (
          <RecapDeck key={deck.key} deck={deck} eventId={round.eventId} calls={calls} />
        ))}
      </span>
      <span
        className={cn(
          "font-display text-5xl leading-none max-sm:col-start-2 max-sm:row-start-1 max-sm:text-3xl",
          score.crowned ? "text-[#f6c95e]" : "text-[#aab3c5]",
          HARD_TEXT_SHADOW,
        )}
      >
        {score.points}
        <span className="text-2xl max-sm:text-lg"> {POINTS_SHORT}</span>
      </span>
    </button>
  );
}

function RecapDeck({ deck, eventId, calls }: { deck: TrophyMageDeck; eventId: string; calls: TrophyCalls }) {
  const { url } = useDeckImage(deck, eventId);
  const picked = calls.crown === deck.key;
  const isTrophy = deck.record === TROPHY_RECORD;
  return (
    <span className="flex min-w-0 flex-col items-center gap-1.5">
      <span
        className={cn(
          "relative block aspect-[12/5] w-full overflow-hidden border-2 bg-[color:var(--px-well)]",
          isTrophy ? "border-[#f6c95e]" : picked ? "border-[color:var(--px-accent)]" : "border-[color:var(--px-ink)]",
        )}
      >
        {url && <img src={url} alt="" draggable={false} className="absolute inset-0 size-full object-cover" />}
      </span>
      <ResultTag
        call={callFor(calls, deck)}
        actual={deck.record}
        className="text-xl max-sm:text-sm max-sm:[&>svg]:hidden max-sm:[&>svg~span]:hidden"
      />
    </span>
  );
}
