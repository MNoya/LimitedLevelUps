import type { CSSProperties } from "react";
import { ChevronLeft, Play } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { SetGlyph } from "../../Brand";
import { useCardImageMapContext, useFallbackImage } from "../../pod/review/ReviewCard";
import { cn } from "../../../lib/utils";
import { cardArtSources } from "../../../data/cardImages";
import {
  gameDayKey,
  scoreWheel,
  setShortLabel,
  useWheelSets,
  type WheelPack,
  type WheelScore,
} from "../../../data/draftGames";
import type { ArtifactCard } from "../../../types/leaderboard";
import {
  ACCENT_BUTTON,
  DARK_PIXEL_BUTTON,
  HARD_TEXT_SHADOW,
  PIXEL_HEADING,
  PIXEL_TAG,
  PIXEL_WELL,
} from "../pixelStyles";
import { useCountUp } from "./motion";
import { CallChipFace, revealOutcome } from "./PackGrid";
import { NextPacksCountdown } from "./NextPacksCountdown";
import { nextOpenWheelDay } from "./useWheelDay";
import { WheelTitle } from "./WheelTitle";

const ROW_GRID = cn(
  "grid grid-cols-[5rem_minmax(0,1fr)_minmax(0,1fr)_5rem] gap-x-3",
  "[@media(max-height:760px)]:sm:grid-cols-[4.25rem_minmax(0,1fr)_minmax(0,1fr)_4.25rem]",
  "max-sm:grid-cols-2 max-sm:gap-x-2",
);
const PHONE_BUTTON = cn(
  "max-sm:w-full max-sm:justify-self-stretch max-sm:px-0 max-sm:py-3 max-sm:text-2xl",
  "[@media(max-height:760px)]:sm:px-6 [@media(max-height:760px)]:sm:py-3 [@media(max-height:760px)]:sm:text-2xl",
);
const STRIP_SHAPE = "aspect-[12/5] max-sm:aspect-[14/5] max-sm:[@media(min-height:740px)]:aspect-[5/3]";
const BOTTOM_ROW = cn(
  "flex min-h-[calc(1.3em+6px)] items-center text-xl",
  "max-sm:text-base [@media(max-height:760px)]:sm:text-base",
);

export function WheelSummary({
  packs,
  locked,
  dayKey,
  animate,
  onReview,
  onExit,
}: {
  packs: WheelPack[];
  locked: Record<string, number[]>;
  dayKey: string;
  animate: boolean;
  onReview: (index: number) => void;
  onExit: () => void;
}) {
  const navigate = useNavigate();
  const scores = packs.map((pack) => scoreWheel(pack, locked[pack.eventId] ?? []));
  let points = 0;
  let max = 0;
  for (const score of scores) {
    points += score.points;
    max += score.max;
  }
  const shownPoints = useCountUp(points, animate, 150, 900);
  const { sets } = useWheelSets();
  const nextDayKey = nextOpenWheelDay(gameDayKey(), dayKey);
  const nextPath = nextDayKey ? nextDayKey : sets[0]?.code.toLowerCase();

  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col items-center pb-4 text-center">
      <div className="hidden sm:block [@media(max-height:760px)]:hidden">
        <WheelTitle scale={5} />
      </div>
      <div className="hidden [@media(max-height:760px)]:sm:block">
        <WheelTitle scale={3.5} />
      </div>
      <div
        className={cn(
          "mt-5 flex w-full flex-col items-center gap-5",
          "max-sm:mt-2 max-sm:gap-3 [@media(max-height:760px)]:mt-2 [@media(max-height:760px)]:gap-2.5",
        )}
      >
        <div className="flex items-center justify-center gap-x-4">
          <span className={PIXEL_TAG}>{dayKey === gameDayKey() ? "Today's Score" : "Score"}</span>
          <span className={cn("font-display text-3xl leading-none text-[#f6c95e]", HARD_TEXT_SHADOW)}>
            {shownPoints}
            <span className="text-2xl"> of {max} Points</span>
          </span>
        </div>
        <div
          className={cn(
            "flex w-full max-w-[690px] flex-col gap-3",
            "[@media(max-height:760px)]:max-w-[420px] [@media(max-height:760px)]:gap-2",
          )}
        >
          {packs.map((pack, i) => (
            <PackRecapRow
              key={pack.eventId}
              pack={pack}
              slots={locked[pack.eventId] ?? []}
              score={scores[i]}
              delayMs={animate ? i * 90 : 0}
              animate={animate}
              onReview={() => onReview(i)}
            />
          ))}
          <div className={cn(ROW_GRID, "mt-2 px-[19px] max-sm:px-[13px] [@media(max-height:760px)]:mt-0")}>
            <button
              onClick={onExit}
              className={cn(
                DARK_PIXEL_BUTTON,
                "col-start-2 justify-self-center py-3.5 pr-10 pl-7 text-3xl",
                PHONE_BUTTON,
                "max-sm:col-start-1",
              )}
            >
              <ChevronLeft size={24} strokeWidth={3} />
              Menu
            </button>
            <button
              onClick={() => nextPath && navigate(`/wheel-of-fortune/${nextPath}`)}
              className={cn(
                ACCENT_BUTTON,
                "col-start-3 justify-self-center px-10 py-3.5 text-3xl",
                PHONE_BUTTON,
                "max-sm:col-start-2",
              )}
            >
              <Play size={22} className="fill-current" />
              {nextDayKey ? "Next" : "Endless"}
            </button>
          </div>
        </div>
        {dayKey === gameDayKey() && <NextPacksCountdown className="-mt-1" />}
      </div>
    </div>
  );
}

function PackRecapRow({
  pack,
  slots,
  score,
  delayMs,
  animate,
  onReview,
}: {
  pack: WheelPack;
  slots: number[];
  score: WheelScore;
  delayMs: number;
  animate: boolean;
  onReview: () => void;
}) {
  const firstPick = pack.order[0].card;
  const yourIndex = slots.indexOf(firstPick);
  const firstPickOutcome = revealOutcome(0, yourIndex);
  return (
    <button
      type="button"
      onClick={onReview}
      aria-label={`Review ${setShortLabel(pack.setCode)}`}
      style={{ animationDelay: `${delayMs}ms` }}
      className={cn(
        ROW_GRID,
        "items-center gap-y-1.5 px-4 py-3 [@media(max-height:760px)]:gap-y-1 [@media(max-height:760px)]:py-2",
        animate && "animate-dealIn",
        "border-[3px] border-[color:var(--px-ink)] bg-[color:var(--px-panel-glass)] backdrop-blur-[3px]",
        "shadow-[inset_0_0_0_2px_var(--px-rim),6px_6px_0_#05070a] transition-transform hover:-translate-y-0.5",
        "max-sm:px-2.5 max-sm:py-2 max-sm:[@media(max-height:740px)]:py-1.5",
      )}
    >
      <span
        className={cn(
          "col-start-1 row-start-1 flex flex-col items-center gap-1.5 text-lg",
          "[--set-icon:2.75rem] [@media(max-height:760px)]:sm:[--set-icon:1.5rem] [@media(max-height:760px)]:sm:gap-1",
          "[@media(max-height:760px)]:sm:text-base",
          "max-sm:flex-row max-sm:justify-self-start max-sm:text-xl max-sm:[--set-icon:1.4rem]",
          PIXEL_HEADING,
        )}
      >
        <SetGlyph code={pack.setCode} size="var(--set-icon)" className="text-[#fff1d6]" />
        {setShortLabel(pack.setCode)}
      </span>
      <span
        className={cn(
          "col-start-4 row-start-1 justify-self-center whitespace-nowrap font-display text-3xl leading-none",
          "text-[#f6c95e] max-sm:col-start-2 max-sm:justify-self-end max-sm:text-2xl [@media(max-height:760px)]:sm:text-2xl",
          HARD_TEXT_SHADOW,
        )}
      >
        {score.points}
        <span className="text-[0.62em]"> of </span>
        {score.max}
        <span className="text-[0.62em]"> pts</span>
      </span>
      <span className="col-start-2 row-start-1 min-w-0 max-sm:col-start-1 max-sm:row-start-2">
        <ArtStrip card={pack.cards[firstPick]} />
      </span>
      <span className="col-start-3 row-start-1 min-w-0 max-sm:col-start-2 max-sm:row-start-2">
        <WheelTally pack={pack} slots={slots} />
      </span>
      <span
        className={cn(BOTTOM_ROW, "col-start-2 row-start-2 justify-self-center max-sm:col-start-1 max-sm:row-start-3")}
      >
        <CallChipFace
          yourIndex={yourIndex}
          realIndex={0}
          outcome={firstPickOutcome === "first" ? "right" : firstPickOutcome}
          still
        />
      </span>
      <span
        className={cn(BOTTOM_ROW, "col-start-3 row-start-2 justify-self-center max-sm:col-start-2 max-sm:row-start-3")}
      >
        <span className={cn("flex items-baseline gap-[0.25em] text-[1.2em]", PIXEL_HEADING)}>
          {score.wheelCalled}
          <span className="text-[0.75em]">of {pack.wheel.length} Wheels</span>
        </span>
      </span>
    </button>
  );
}

function ArtStrip({ card }: { card: ArtifactCard }) {
  const cardImages = useCardImageMapContext();
  const { src, onError } = useFallbackImage(cardArtSources(card.n, card.s, cardImages));
  return (
    <span className={cn("relative block w-full overflow-hidden", STRIP_SHAPE, PIXEL_WELL)}>
      {src && (
        <img
          src={src}
          alt={card.n ?? ""}
          onError={onError}
          draggable={false}
          className="absolute inset-0 size-full object-cover"
        />
      )}
    </span>
  );
}

function WheelTally({ pack, slots }: { pack: WheelPack; slots: number[] }) {
  const columns = Math.ceil(pack.wheel.length / 2);
  const cellSize = {
    width: `calc((100% - ${columns - 1} * 0.25rem) / ${columns})`,
    height: "calc((100% - 0.25rem) / 2)",
  };
  return (
    <span className={cn("block w-full p-1", STRIP_SHAPE, PIXEL_WELL)}>
      <span className="flex size-full flex-wrap content-between justify-center gap-1">
        {pack.wheel.map((card) => (
          <WheelTallyCard key={card} card={pack.cards[card]} called={!slots.includes(card)} style={cellSize} />
        ))}
      </span>
    </span>
  );
}

function WheelTallyCard({ card, called, style }: { card: ArtifactCard; called: boolean; style: CSSProperties }) {
  const cardImages = useCardImageMapContext();
  const { src, onError } = useFallbackImage(cardArtSources(card.n, card.s, cardImages));
  return (
    <span
      className={cn(
        "relative block min-h-0 overflow-hidden border-2",
        called ? "border-green" : "border-[#2b3445] opacity-40 grayscale",
      )}
      style={style}
    >
      {src && (
        <img
          src={src}
          alt={card.n ?? ""}
          onError={onError}
          draggable={false}
          className="absolute inset-0 size-full object-cover"
        />
      )}
    </span>
  );
}
