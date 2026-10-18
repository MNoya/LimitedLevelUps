import { useEffect, useState } from "react";

import { CardImage } from "../../pod/review/ReviewCard";
import { cn } from "../../../lib/utils";
import {
  dayNumber,
  msUntilNextDay,
  scoreWheel,
  WHEEL_GAME_TITLE,
  type RoundMark,
  type WheelPack,
} from "../../../data/draftGames";
import { SetGlyph } from "../../Brand";
import { MARK_EMOJI, ShareButton } from "../GameChrome";
import { GOLD_BUTTON, HARD_TEXT_SHADOW, PIXEL_HEADING, PIXEL_PANEL, PIXEL_WELL } from "../pixelStyles";
import { useCountUp } from "./motion";
import { GAME_COLUMNS, PACK_GRID_WIDTH } from "./PackGrid";
import { WheelHeader } from "./WheelHeader";

const MARK_RING: Record<RoundMark, string> = { hit: "ring-green", close: "ring-gold", miss: "ring-red" };
const SHARE_URL = "limitedlevelups.com/wheel-of-fortune";

export function WheelSummary({
  packs,
  locked,
  dayKey,
  animate,
  onReview,
  onExit,
  setName,
  touchVerb,
}: {
  packs: WheelPack[];
  locked: Record<string, number[]>;
  dayKey: string;
  animate: boolean;
  onReview: (index: number) => void;
  onExit: () => void;
  setName: (code: string) => string;
  touchVerb: string;
}) {
  const scores = packs.map((pack) => scoreWheel(pack, locked[pack.eventId] ?? []));
  const marks = scores.map((score) => score.mark);
  let points = 0;
  let max = 0;
  let baseline = 0;
  let firstPicks = 0;
  let wheelCalled = 0;
  let wheelTotal = 0;
  for (let i = 0; i < scores.length; i++) {
    const score = scores[i];
    points += score.points;
    max += score.max;
    baseline += score.baseline;
    if (score.firstPickExact) {
      firstPicks += 1;
    }
    wheelCalled += score.wheelCalled;
    wheelTotal += packs[i].wheel.length;
  }
  const shownPoints = useCountUp(points, animate, 150, 900);
  const squares = marks.map((mark) => MARK_EMOJI[mark]).join("");
  const dayLabel = `Day ${dayNumber(dayKey)}`;
  const share = `${WHEEL_GAME_TITLE} ${dayLabel}\n${squares}\n${points} of ${max} points\n${SHARE_URL}`;
  const aboveRandom = Math.round(points - baseline);

  return (
    <div
      className={cn(
        "flex flex-col gap-3 lg:grid lg:min-h-[calc(100vh-125px)] lg:grid-rows-[auto_auto]",
        GAME_COLUMNS,
        "lg:content-center lg:justify-center lg:gap-x-4",
      )}
    >
      <WheelHeader
        setCode={null}
        title="Today's Featured"
        subtitle={dayLabel}
        progress={{
          kind: "featured",
          steps: packs.map((pack, i) => ({ setCode: pack.setCode, name: setName(pack.setCode), mark: marks[i] })),
          current: null,
          onSelect: onReview,
        }}
        onExit={onExit}
        className={cn(PIXEL_PANEL, "px-4 py-3 lg:col-start-2 lg:row-start-1")}
      />
      <div
        className={cn(
          "grid grid-cols-2 gap-3 sm:grid-cols-3 lg:col-start-1 lg:row-span-2 lg:row-start-1 lg:grid-cols-5",
          "max-lg:order-last lg:self-center",
          PACK_GRID_WIDTH,
        )}
      >
        {packs.map((pack, i) => {
          const score = scores[i];
          return (
            <div key={pack.eventId} className="animate-dealIn" style={{ animationDelay: `${i * 70}ms` }}>
              <button
                onClick={() => onReview(i)}
                aria-label={`Review pack ${i + 1} of ${packs.length}`}
                className={cn(
                  "group block w-full text-left transition-transform duration-150",
                  "hover:-translate-y-1 active:scale-[0.98]",
                )}
              >
                <div
                  className={cn(
                    "rounded-[4.5%/3.2%] ring-[3px] shadow-[5px_6px_0_3px_#05070a] transition-shadow",
                    "group-hover:ring-[#f6c95e]",
                    MARK_RING[score.mark],
                  )}
                >
                  <CardImage card={pack.cards[pack.order[0].card]} className="rounded-[4.5%/3.2%]" />
                </div>
                <div className="mt-2 flex items-center justify-between gap-2 px-0.5">
                  <span className="flex min-w-0 items-center gap-1.5 text-sm font-bold text-text group-hover:text-[#f6c95e]">
                    <SetGlyph code={pack.setCode} size={15} />
                    <span className="truncate">{setName(pack.setCode)}</span>
                  </span>
                  <span className="font-display text-xl leading-none text-[#f6c95e]">
                    {score.points}
                    <span className="font-normal text-subtle"> of {score.max}</span>
                  </span>
                </div>
                <div className="mt-0.5 flex gap-x-3 px-0.5 text-[13px] text-subtle">
                  <span>
                    Wheel {score.wheelCalled} of {pack.wheel.length}
                  </span>
                  {score.firstPickExact && <span className="text-[#f6c95e]">First Pick</span>}
                </div>
              </button>
            </div>
          );
        })}
      </div>
      <div className={cn(PIXEL_PANEL, "p-5 animate-fadeUpIn", "lg:col-start-2 lg:row-start-2 lg:self-start")}>
        <h2 className={cn("text-2xl", PIXEL_HEADING)}>Today's Score</h2>
        <div className="mt-2 flex items-baseline gap-2">
          <span className={cn("font-display text-7xl leading-none text-text", HARD_TEXT_SHADOW)}>{shownPoints}</span>
          <span className="text-lg text-subtle">of {max} points</span>
        </div>
        <RandomComparison pointsAbove={aboveRandom} />
        <div className="mt-4 grid grid-cols-2 gap-3">
          <SummaryStat label="First Picks" value={`${firstPicks} of ${packs.length}`} />
          <SummaryStat label="Wheel Cards" value={`${wheelCalled} of ${wheelTotal}`} />
        </div>
        <div className={cn(PIXEL_WELL, "mt-4 px-4 py-3 text-sm leading-relaxed whitespace-pre-line text-subtle")}>
          {share}
        </div>
        <ShareButton text={share} buttonClass={GOLD_BUTTON} className="mt-4 w-full text-xl" />
        <p className="mt-3 text-center text-sm text-subtle">{touchVerb} a pack to see its picks again</p>
        <NextPacksCountdown />
        <button onClick={onExit} className="mt-2 w-full text-center text-sm font-bold text-[#f6c95e] hover:underline">
          Keep Playing in Free Play
        </button>
      </div>
    </div>
  );
}

function RandomComparison({ pointsAbove }: { pointsAbove: number }) {
  const pointsWord = Math.abs(pointsAbove) === 1 ? "point" : "points";
  let text = "Same score as random guesses";
  let color = "text-subtle";
  if (pointsAbove > 0) {
    text = `${pointsAbove} ${pointsWord} above random guesses`;
    color = "text-[#f6c95e]";
  } else if (pointsAbove < 0) {
    text = `${-pointsAbove} ${pointsWord} below random guesses`;
    color = "text-red";
  }
  return <p className={cn("mt-2 text-sm font-semibold", color)}>{text}</p>;
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className={cn(PIXEL_WELL, "px-3 py-2")}>
      <div className="text-[13px] font-bold text-subtle">{label}</div>
      <div className="font-display text-2xl leading-none text-text">{value}</div>
    </div>
  );
}

function NextPacksCountdown() {
  const [remaining, setRemaining] = useState(msUntilNextDay);
  useEffect(() => {
    const timer = window.setInterval(() => setRemaining(msUntilNextDay()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const hours = Math.floor(remaining / 3_600_000);
  const minutes = Math.floor((remaining % 3_600_000) / 60_000);
  return (
    <p className="mt-4 text-center text-sm text-subtle">
      New packs in{" "}
      <span className="font-num font-semibold text-text">
        {hours}h {minutes}m
      </span>
    </p>
  );
}
