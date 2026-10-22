import { SetGlyph } from "../../Brand";
import { cn } from "../../../lib/utils";
import { setShortLabel, shortDayLabel, useWheelSets, gameDayKey } from "../../../data/draftGames";
import {
  callFor,
  EMPTY_CALLS,
  scoreTrophyRound,
  TROPHY_RECORD,
  type TrophyCalls,
  type TrophyMageDeck,
  type TrophyMageRound,
} from "../../../data/trophyMage";
import { HARD_TEXT_SHADOW, PIXEL_HEADING } from "../pixelStyles";
import { DailyCountdown, DayEndButtons, DayPoints } from "../GameChrome";
import { ENDLESS_ACTION, NEXT_DAY_ACTION, nextPlayAfter } from "../gameDay";
import { NEXT_PODS_LABEL, ResponsiveTitle } from "./introParts";
import { ResultTag } from "./RecordChip";
import { SpriteStrip, TROPHY_SPRITE } from "./SpriteStrip";
import { TROPHY_DAY, type TrophyDay } from "./trophyDay";
import { useDeckImage } from "./useDeckImage";

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
    <div
      className={cn(
        "mx-auto flex w-full max-w-[1100px] flex-col items-center pb-4 text-center",
        "max-sm:h-[calc(100dvh-5rem)] max-sm:pb-0",
      )}
    >
      <div className="max-sm:hidden">
        <ResponsiveTitle />
      </div>
      <PhoneRecapHeading dayKey={dayKey} points={points} max={max} />
      <div
        className={cn(
          "mt-7 flex w-full flex-col items-center gap-6 sm:mt-8",
          "[@media(max-height:760px)]:sm:mt-3 [@media(max-height:760px)]:gap-3",
          "max-sm:mt-3 max-sm:min-h-0 max-sm:flex-1 max-sm:gap-3",
        )}
      >
        <DayScoreRow dayKey={dayKey} points={points} max={max} />
        <div
          className={cn(
            "flex w-full max-w-[1040px] flex-col gap-4 max-sm:min-h-0 max-sm:shrink max-sm:gap-3",
            "[@media(min-height:821px)_and_(max-height:940px)]:max-w-[820px]",
            "[@media(max-height:820px)]:max-w-[620px] [@media(max-height:760px)]:gap-2",
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

function PhoneRecapHeading({ dayKey, points, max }: { dayKey: string | null; points: number; max: number }) {
  return (
    <div className="flex w-full shrink-0 items-center justify-between gap-3 px-1 sm:hidden">
      <span className="flex items-center gap-3">
        <SpriteStrip sheet={TROPHY_SPRITE} scale={2.5} restMs={1800} className="drop-shadow-[2px_2px_0_#05070a]" />
        {dayKey && <h1 className={cn("text-3xl", PIXEL_HEADING)}>{shortDayLabel(dayKey)}</h1>}
      </span>
      <span className="flex flex-col items-end gap-1.5">
        <DayPoints points={points} max={max} className="text-2xl [&>span]:text-xl" />
        {isToday(dayKey) && <DailyCountdown label={NEXT_PODS_LABEL} className="text-sm [&>span]:text-base" />}
      </span>
    </div>
  );
}

function DayScoreRow({ dayKey, points, max }: { dayKey: string | null; points: number; max: number }) {
  return (
    <div className="flex w-full flex-wrap items-center justify-center gap-x-6 gap-y-2 max-sm:hidden">
      {dayKey && <h1 className={cn("text-3xl", PIXEL_HEADING)}>{shortDayLabel(dayKey)}</h1>}
      <DayPoints points={points} max={max} />
      {isToday(dayKey) && <DailyCountdown label={NEXT_PODS_LABEL} />}
    </div>
  );
}

function isToday(dayKey: string | null): boolean {
  return dayKey === gameDayKey(new Date());
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
  const next = nextPlayAfter(TROPHY_DAY, gameDayKey(new Date()), dayKey, sets[0]?.code);
  let playNext: (() => void) | null = null;
  if (next.label === NEXT_DAY_ACTION && onPlayDay) {
    playNext = () => onPlayDay(next.dayKey);
  } else if (next.label === ENDLESS_ACTION && next.setCode && onPlaySet) {
    const setCode = next.setCode;
    playNext = () => onPlaySet(setCode);
  }
  return (
    <div className="flex flex-wrap justify-center gap-3">
      <DayEndButtons next={next} onNext={playNext} onExit={onExit} />
    </div>
  );
}

function RecapRow({ round, calls, onReview }: { round: TrophyMageRound; calls: TrophyCalls; onReview: () => void }) {
  const score = scoreTrophyRound(round, calls);
  const crownedDeck = round.decks.find((deck) => deck.key === calls.crown);
  return (
    <button
      type="button"
      onClick={onReview}
      aria-label={`Review ${setShortLabel(round.setCode)}`}
      className={cn(
        "grid grid-cols-[8rem_minmax(0,1fr)_7rem] items-center gap-5 px-5 py-4",
        "border-[3px] border-[color:var(--px-ink)]",
        "bg-[radial-gradient(ellipse_at_50%_20%,rgba(30,60,115,0.1),rgba(8,14,32,0.35)_75%)]",
        "shadow-[inset_0_0_0_2px_var(--px-rim),6px_6px_0_#05070a] transition-transform hover:-translate-y-0.5",
        "max-sm:flex max-sm:min-h-0 max-sm:flex-col max-sm:items-stretch max-sm:gap-2 max-sm:px-2.5 max-sm:py-2",
        "[@media(max-height:760px)]:py-2",
      )}
    >
      <span className="flex shrink-0 flex-col items-center gap-2 max-sm:flex-row max-sm:gap-2.5">
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
        {crownedDeck && (
          <ResultTag
            call={callFor(calls, crownedDeck)}
            actual={crownedDeck.record}
            className="mx-auto text-sm sm:hidden"
          />
        )}
        <RoundPoints points={score.points} crowned={score.crowned} className="sm:hidden" />
      </span>
      <span className="grid grid-cols-3 gap-4 max-sm:hidden">
        {round.decks.map((deck) => (
          <RecapDeck key={deck.key} deck={deck} eventId={round.eventId} calls={calls} />
        ))}
      </span>
      {crownedDeck && <CrownedDeckImage deck={crownedDeck} eventId={round.eventId} />}
      <RoundPoints points={score.points} crowned={score.crowned} className="max-sm:hidden" />
    </button>
  );
}

function RoundPoints({ points, crowned, className }: { points: number; crowned: boolean; className: string }) {
  return (
    <span
      className={cn(
        "font-display text-5xl leading-none max-sm:text-3xl",
        crowned ? "text-[#f6c95e]" : "text-[#aab3c5]",
        HARD_TEXT_SHADOW,
        className,
      )}
    >
      {points}
      <span className="text-2xl max-sm:text-lg"> {POINTS_SHORT}</span>
    </span>
  );
}

function CrownedDeckImage({ deck, eventId }: { deck: TrophyMageDeck; eventId: string }) {
  const { url } = useDeckImage(deck, eventId);
  const isTrophy = deck.record === TROPHY_RECORD;
  return (
    <span
      className={cn(
        "relative block aspect-[12/5] min-h-0 w-full overflow-hidden border-2 bg-[color:var(--px-well)] sm:hidden",
        isTrophy ? "border-[#f6c95e]" : "border-[color:var(--px-accent)]",
      )}
    >
      {url && <img src={url} alt="" draggable={false} className="absolute inset-0 size-full object-cover" />}
    </span>
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
      <ResultTag call={callFor(calls, deck)} actual={deck.record} className="text-xl" />
    </span>
  );
}
