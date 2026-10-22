import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, LayoutGrid, Play, Zap } from "lucide-react";

import { cn } from "../../../lib/utils";
import {
  CUBE_SET_CODE,
  daysBefore,
  setShortLabel,
  useFeaturedSetCodes,
  useWheelSets,
  type WheelSetOption,
  shortDayLabel,
} from "../../../data/draftGames";
import { DailyCountdown, HelpSquareButton, PlayButton } from "../GameChrome";
import { ResponsiveWordmark } from "../PixelWordmark";
import { dayAction, NEXT_DAY_ACTION, nextPlayAfter, PLAY_ACTION, readGameDay, RESULTS_ACTION } from "../gameDay";
import { DARK_PIXEL_BUTTON, ACCENT_BUTTON, HARD_TEXT_SHADOW, PIXEL_TAG } from "../pixelStyles";
import { CardBack } from "./CardBack";
import { NEXT_PACKS_LABEL, WHEEL_DAY } from "./wheelDay";
import { useTouchVerb } from "./pageHooks";
import { useQuickPreload } from "./quickPreload";
import { WheelHelpDialog } from "./WheelHelp";
import { WheelTitle } from "./WheelTitle";

export const FEATURED_PLAY = "featured";

export function WheelIntro({
  dayKey,
  onPlay,
  onHelp,
  onQuickHelp,
  helpOpen,
  onCloseHelp,
}: {
  dayKey: string;
  onPlay: (play: string) => void;
  onHelp: () => void;
  onQuickHelp: () => void;
  helpOpen: boolean;
  onCloseHelp: () => void;
}) {
  const touchVerb = useTouchVerb();
  const { sets } = useWheelSets();
  const yesterdayKey = daysBefore(dayKey, 1);
  const featuredSets = useFeaturedSetCodes(dayKey);
  const yesterdaySets = useFeaturedSetCodes(yesterdayKey);
  const today = daySlide(dayKey, featuredSets, "Today", "Today's Packs");
  const todayDone = today.action === RESULTS_ACTION;
  const newestSet = sets[0]?.code;
  const nextPlay = nextPlayAfter(WHEEL_DAY, dayKey, dayKey, newestSet);
  useQuickPreload(newestSet);
  const playNext = () => {
    if (nextPlay.label === NEXT_DAY_ACTION) {
      onPlay(nextPlay.dayKey);
    } else if (nextPlay.setCode) {
      onPlay(nextPlay.setCode);
    }
  };
  const data: IntroData = {
    dayLabel: today.label,
    featuredSets,
    featuredAction: todayDone ? nextPlay.label : today.action,
    todayDone,
    onTodayResults: () => onPlay(FEATURED_PLAY),
    days: [daySlide(yesterdayKey, yesterdaySets, "Yesterday", "Yesterday's Packs"), today],
    sets,
    onFeatured: todayDone ? playNext : () => onPlay(FEATURED_PLAY),
    onDay: (key) => (key === dayKey ? (todayDone ? playNext() : onPlay(FEATURED_PLAY)) : onPlay(key)),
    onSet: onPlay,
    onHelp,
    onQuickHelp,
  };

  return (
    <div className="mx-auto flex w-full max-w-[880px] flex-1 flex-col items-center pb-4 text-center">
      <ResponsiveWordmark wordmark={WheelTitle} phone={3} desktop={6} short={4} phoneClassName="mt-1" />
      <PickerIntro data={data} />
      <WheelHelpDialog
        open={helpOpen}
        onClose={onCloseHelp}
        action={{ label: data.featuredAction, onClick: data.onFeatured }}
        touchVerb={touchVerb}
      />
    </div>
  );
}

function daySlide(dayKey: string, sets: string[], name: string, title: string): DaySlide {
  const action = dayAction(WHEEL_DAY, readGameDay(WHEEL_DAY, dayKey));
  return { dayKey, label: shortDayLabel(dayKey), name, title, sets, action };
}

function resultsIcon(action: string): ReactNode {
  return action === RESULTS_ACTION ? <LayoutGrid size={22} strokeWidth={3} /> : undefined;
}

interface DaySlide {
  dayKey: string;
  label: string;
  name: string;
  title: string;
  sets: string[];
  action: string;
}

interface IntroData {
  dayLabel: string;
  featuredSets: string[];
  featuredAction: string;
  todayDone: boolean;
  onTodayResults: () => void;
  days: DaySlide[];
  sets: WheelSetOption[];
  onFeatured: () => void;
  onDay: (dayKey: string) => void;
  onSet: (code: string) => void;
  onHelp: () => void;
  onQuickHelp: () => void;
}

const TODAY_SLIDE = "today";
const DAY_SLIDE_PREFIX = "day:";
const LOADING_SET_SLIDES = ["loading-0", "loading-1", "loading-2", "loading-3", "loading-4"];
const SHORT_SCREEN_BUTTON = "[@media(max-height:760px)]:sm:py-1.5 [@media(max-height:760px)]:sm:text-2xl";
const DESKTOP_PLAY = cn("px-12 py-3.5 text-3xl", SHORT_SCREEN_BUTTON);
const DESKTOP_QUICK = cn("px-7 py-3.5 text-2xl", SHORT_SCREEN_BUTTON, "[@media(max-height:760px)]:sm:text-xl");
const PHONE_PLAY = "px-10 py-2.5 text-2xl";
const PHONE_QUICK = "px-6 py-2.5 text-xl";
const FAN_STEP = 0.92;
const SIDE_SCALE = 0.78;
const SET_GAP = 0.14;
const TODAY_GAP = 0.75;
const STEP_BUTTON_PX = 44;

function PickerIntro({ data }: { data: IntroData }) {
  const pastDays = data.days.slice(0, -1);
  const todayIndex = pastDays.length;
  const slides = useMemo(
    () => [
      ...pastDays.map((day) => `${DAY_SLIDE_PREFIX}${day.dayKey}`),
      TODAY_SLIDE,
      ...(data.sets.length > 0 ? data.sets.map((set) => set.code) : LOADING_SET_SLIDES),
    ],
    [pastDays, data.sets],
  );
  const [requestedIndex, setRequestedIndex] = useState(todayIndex);
  const lastIndex = todayIndex + data.sets.length;
  const selectedIndex = Math.min(requestedIndex, lastIndex);
  const selected = slides[selectedIndex];
  const isToday = selected === TODAY_SLIDE;
  const selectedDay = selectedIndex <= todayIndex ? data.days[selectedIndex] : null;
  const selectedSet = data.sets.find((set) => set.code === selected);
  const step = useCallback(
    (delta: number) => setRequestedIndex((index) => Math.max(0, Math.min(lastIndex, index + delta))),
    [lastIndex],
  );
  useArrowKeys(step);
  const swipe = useSwipe(step);
  const play = () => (selectedDay ? data.onDay(selectedDay.dayKey) : data.onSet(selected));
  let desktopAction = selectedDay ? selectedDay.action : PLAY_ACTION;
  if (isToday) {
    desktopAction = data.featuredAction;
  }
  const fanCounts = data.days.map((day) => fanCount(day.sets));
  const offsets = slideOffsets(slides.length, todayIndex, selectedIndex, fanCounts);
  const firstSetEdge = fanWidth(data.featuredSets.length) / 2 + TODAY_GAP;

  return (
    <div
      className={cn(
        "group/picker mt-4 flex w-full flex-col items-center sm:mt-8 sm:[--u:108px] [@media(max-height:700px)]:mt-1",
        "max-sm:flex-1 max-sm:[--u:clamp(50px,8dvh,80px)]",
        "[@media(max-height:760px)]:sm:mt-4 [@media(max-height:760px)]:sm:[--u:80px]",
      )}
    >
      <PremiseRow onHelp={data.onHelp} />
      <MobileToday data={data} />
      <div
        className={cn(
          "relative z-20 mt-8 grid max-w-full grid-cols-[auto_1fr_auto] items-center gap-3 max-sm:hidden",
          "[@media(max-height:760px)]:sm:mt-4",
        )}
        style={{ width: `calc(var(--u) * ${2 * firstSetEdge} + ${2 * STEP_BUTTON_PX}px)` }}
      >
        <StepButton label="Previous" disabled={selectedIndex === 0} onClick={() => step(-1)}>
          <ChevronLeft size={24} strokeWidth={3} />
        </StepButton>
        <div key={selected} className="flex min-h-[56px] items-center justify-center gap-3 animate-fadeUpIn">
          {selectedDay ? (
            <TodayHeading dayLabel={selectedDay.label} title={selectedDay.title} />
          ) : (
            <h2 className={cn("font-display text-4xl leading-none text-text", HARD_TEXT_SHADOW)}>
              {selectedSet?.name}
            </h2>
          )}
        </div>
        <StepButton label="Next" disabled={selectedIndex === lastIndex} onClick={() => step(1)}>
          <ChevronRight size={24} strokeWidth={3} />
        </StepButton>
      </div>
      <div
        className={cn(
          "relative -mt-4 -mb-8 h-[calc(var(--u)*1.55+40px+4rem)] w-screen touch-pan-y select-none overflow-x-clip",
          "max-sm:hidden",
          "py-8 sm:[mask-image:linear-gradient(to_right,transparent_4%,black_24%,black_76%,transparent_96%)]",
        )}
        {...swipe}
      >
        {slides.map((slide, i) => {
          const center = i === selectedIndex;
          const day = i <= todayIndex ? data.days[i] : null;
          const pinnedToday = firstShownSet(todayIndex, selectedIndex) > todayIndex + 1;
          const hiddenSet = !day && i < firstShownSet(todayIndex, selectedIndex);
          const hiddenPast = i < todayIndex && pinnedToday;
          const hidden = hiddenSet || hiddenPast || Math.abs(offsets[i]) > 5.5;
          const faded = i === todayIndex && pinnedToday;
          const transform = `translateX(calc(-50% + var(--u) * ${offsets[i]})) scale(${center ? 1 : SIDE_SCALE})`;
          return (
            <button
              key={i > todayIndex ? `set-${i}` : slide}
              onClick={() => (center ? play() : setRequestedIndex(i))}
              aria-label={day ? `${day.label} ${day.title}` : data.sets[i - todayIndex - 1]?.name}
              tabIndex={hidden ? -1 : 0}
              className={cn(
                "group absolute bottom-8 left-1/2 flex origin-bottom flex-col items-center gap-2",
                "transition-[transform,opacity,filter] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
                center && "picker-center z-10",
                hidden && "pointer-events-none opacity-0",
                faded && "opacity-40 hover:opacity-100",
              )}
              style={{ transform }}
            >
              <span
                className={cn(
                  "block transition-[filter,transform] duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
                  !center && "brightness-[0.65] group-hover:brightness-100",
                  center && "[@media(hover:hover)]:group-has-[.picker-play:hover]/picker:-translate-y-3",
                  center && "[@media(hover:hover)]:group-has-[.picker-play:hover]/picker:scale-[1.06]",
                )}
              >
                {day ? (
                  <TodayFan sets={day.sets} lift={center} />
                ) : LOADING_SET_SLIDES.includes(slide) ? (
                  <CardBack code={null} index={i} className="w-[var(--u)]" />
                ) : (
                  <CardBack code={slide} index={i} className="w-[var(--u)]" />
                )}
              </span>
              <span
                className={cn(
                  "relative z-30 text-xl leading-none font-bold",
                  center ? "text-[#f6c95e]" : "text-text group-hover:text-[#f6c95e]",
                  HARD_TEXT_SHADOW,
                )}
              >
                <SlideLabel slide={slide} center={center} day={day} />
              </span>
            </button>
          );
        })}
      </div>
      <div
        className={cn(
          "mt-10 flex flex-col items-center gap-7 max-sm:hidden",
          "[@media(max-height:760px)]:sm:mt-5 [@media(max-height:760px)]:sm:gap-3",
        )}
      >
        <div className="relative">
          {isToday && data.todayDone && <ResultsButton onClick={data.onTodayResults} />}
          <PlayButton
            label={desktopAction}
            icon={resultsIcon(desktopAction)}
            onClick={play}
            className={cn(
              "picker-play",
              "[@media(hover:hover)]:group-has-[.picker-center:hover]/picker:-translate-y-0.5",
              "[@media(hover:hover)]:group-has-[.picker-center:hover]/picker:brightness-110",
              "[@media(hover:hover)]:group-has-[.picker-center:hover]/picker:shadow-[6px_7px_0_#05070a]",
              DESKTOP_PLAY,
            )}
          />
        </div>
        {isToday && data.todayDone && <DailyCountdown label={NEXT_PACKS_LABEL} className="-mt-3" />}
        <QuickModeRow onHelp={data.onQuickHelp} size={DESKTOP_QUICK} />
      </div>
    </div>
  );
}

function ResultsButton({ onClick, small = false }: { onClick: () => void; small?: boolean }) {
  return (
    <span className={cn("absolute inset-y-0 right-full flex items-center", small ? "mr-3" : "mr-4")}>
      <button onClick={onClick} className={cn(DARK_PIXEL_BUTTON, small ? "px-3 py-2 text-lg" : "px-4 py-2.5 text-xl")}>
        <LayoutGrid size={small ? 16 : 18} strokeWidth={3} />
        {RESULTS_ACTION}
      </button>
    </span>
  );
}

function QuickModeRow({ onHelp, size, className }: { onHelp: () => void; size: string; className?: string }) {
  return (
    <div className={cn("flex justify-center", className)}>
      <div className="relative">
        <span className="absolute top-1/2 right-full mr-4 -translate-y-1/2">
          <ChoiceHeading>Or</ChoiceHeading>
        </span>
        <Link to="/wheel-of-fortune/quick" className={cn(ACCENT_BUTTON, size)}>
          <Zap size={18} className="fill-current" />
          Quick Mode
        </Link>
        <span className="absolute inset-y-0 left-full ml-4 flex items-center">
          <HelpSquareButton onClick={onHelp} label="About Quick Mode" />
        </span>
      </div>
    </div>
  );
}

function ChoiceHeading({ children }: { children: string }) {
  return (
    <h2 className={cn("text-center font-display text-2xl leading-none text-[#f6c95e]", HARD_TEXT_SHADOW)}>
      {children}
    </h2>
  );
}

function PremiseRow({ onHelp }: { onHelp: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 sm:gap-x-4 sm:gap-y-4">
      <span className={PIXEL_TAG}>Pack 1 Pick 1</span>
      <span
        className={cn("text-2xl font-bold text-text max-sm:order-last max-sm:w-full max-sm:text-lg", HARD_TEXT_SHADOW)}
      >
        Can you guess what will wheel?
      </span>
      <button onClick={onHelp} className={cn(DARK_PIXEL_BUTTON, "px-3 py-2 text-lg sm:px-4 sm:py-2.5 sm:text-xl")}>
        How to Play
      </button>
    </div>
  );
}

function MobileToday({ data }: { data: IntroData }) {
  return (
    <div
      className={cn(
        "mt-4 flex w-full flex-1 flex-col items-center justify-evenly sm:hidden [--fan-step:1.08]",
        "[@media(max-height:700px)]:mt-1",
      )}
    >
      <div className="flex flex-col items-center">
        <TodayHeading dayLabel={data.dayLabel} />
        <button
          onClick={data.onFeatured}
          aria-label="Play Today's Packs"
          className="mt-3 flex flex-col items-center gap-2"
        >
          <TodayFan sets={data.featuredSets} lift={false} />
          <span className={cn("relative z-30 text-lg leading-none font-bold text-[#f6c95e]", HARD_TEXT_SHADOW)}>
            <SlideLabel slide={TODAY_SLIDE} center day={data.days[data.days.length - 1]} />
          </span>
        </button>
      </div>
      <div className="relative mt-4 flex flex-col items-center gap-3">
        <div className="relative">
          {data.todayDone && <ResultsButton onClick={data.onTodayResults} small />}
          <PlayButton
            label={data.featuredAction}
            icon={resultsIcon(data.featuredAction)}
            onClick={data.onFeatured}
            className={PHONE_PLAY}
          />
        </div>
        {data.todayDone && (
          <DailyCountdown
            label={NEXT_PACKS_LABEL}
            className={cn(
              "[@media(max-height:700px)]:absolute [@media(max-height:700px)]:top-1/2",
              "[@media(max-height:700px)]:left-full [@media(max-height:700px)]:w-max",
              "[@media(max-height:700px)]:ml-3 [@media(max-height:700px)]:-translate-y-1/2",
              "[@media(max-height:700px)]:flex-col [@media(max-height:700px)]:items-start",
            )}
          />
        )}
      </div>
      <FreePlayRow data={data} title="Or Select a Set" className="mt-5 [@media(max-height:700px)]:mt-2" />
      <QuickModeRow onHelp={data.onQuickHelp} size={PHONE_QUICK} />
    </div>
  );
}

function TodayHeading({ dayLabel, title = "Today's Packs" }: { dayLabel: string; title?: string }) {
  return (
    <h2 className={cn("relative font-display text-3xl leading-none text-text sm:text-4xl", HARD_TEXT_SHADOW)}>
      <span
        className={cn(
          "absolute top-1/2 right-full mr-3 -translate-y-1/2 whitespace-nowrap text-xl text-[#f6c95e] sm:text-2xl",
          HARD_TEXT_SHADOW,
        )}
      >
        {dayLabel}
      </span>
      {title}
    </h2>
  );
}

function SlideLabel({ slide, center, day }: { slide: string; center: boolean; day: DaySlide | null }) {
  if (!day) {
    return LOADING_SET_SLIDES.includes(slide) ? "\u00a0" : homeSetLabel(slide);
  }
  if (day.sets.length === 0) {
    return "\u00a0";
  }
  if (!center) {
    return day.name;
  }
  return (
    <span className="flex justify-center">
      {day.sets.map((code, i) => (
        <span
          key={`${code}-${i}`}
          className="shrink-0 px-1 text-center whitespace-nowrap"
          style={{ minWidth: `calc(var(--u) * var(--fan-step, ${FAN_STEP}))` }}
        >
          {homeSetLabel(code)}
        </span>
      ))}
    </span>
  );
}

function fanCount(sets: string[]): number {
  return sets.length > 0 ? sets.length : WHEEL_DAY.roundsPerDay;
}

function homeSetLabel(code: string): string {
  return code === CUBE_SET_CODE ? "CUBE" : setShortLabel(code);
}

function TodayFan({ sets, lift }: { sets: string[]; lift: boolean }) {
  const count = fanCount(sets);
  const cards = sets.length > 0 ? sets : Array.from({ length: count }, () => null);
  return (
    <span
      className="relative mb-[calc(var(--u)*0.12)] block h-[calc(var(--u)*1.55)]"
      style={{
        width: `calc(var(--u) * (1 + ${count - 1} * var(--fan-step, ${FAN_STEP})))`,
      }}
    >
      {cards.map((code, i) => {
        const offset = i - (count - 1) / 2;
        return (
          <span
            key={`card-${i}`}
            className={cn("group/pack absolute bottom-0 origin-bottom", lift && "hover:!z-20")}
            style={{
              left: `calc(var(--u) * ${i} * var(--fan-step, ${FAN_STEP}))`,
              zIndex: i + 1,
              transform: `rotate(${offset * 6}deg) translateY(calc(var(--u) * ${Math.abs(offset) * 0.05}))`,
            }}
          >
            <span
              className={cn(
                "block transition-transform duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
                lift && "group-hover/pack:-translate-y-4 group-hover/pack:scale-[1.18]",
              )}
            >
              <CardBack code={code} index={i} className="w-[var(--u)]" />
            </span>
          </span>
        );
      })}
    </span>
  );
}

function FreePlayRow({ data, title, className }: { data: IntroData; title: string; className?: string }) {
  return (
    <section className={cn("w-full", className)}>
      <ChoiceHeading>{title}</ChoiceHeading>
      <div
        className={cn(
          "-mx-4 mt-4 flex gap-x-2 overflow-x-auto px-5 pt-2 pb-2 [justify-content:safe_center]",
          "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
          "[mask-image:linear-gradient(to_right,transparent,black_28px,black_calc(100%-28px),transparent)]",
        )}
      >
        {data.days
          .slice(0, -1)
          .reverse()
          .map((day) => (
            <button
              key={day.dayKey}
              onClick={() => data.onDay(day.dayKey)}
              className={cn(
                "group flex shrink-0 flex-col items-center gap-2 px-1.5",
                "transition-transform duration-200 hover:-translate-y-1.5",
              )}
            >
              <span className="block [--fan-step:0.5] [--u:36px]">
                <TodayFan sets={day.sets} lift={false} />
              </span>
              <span
                className={cn(
                  "relative z-10 text-center text-base leading-none font-bold text-text group-hover:text-[#f6c95e]",
                  HARD_TEXT_SHADOW,
                )}
              >
                {day.sets.length > 0 ? day.name : "\u00a0"}
              </span>
            </button>
          ))}
        {(data.sets.length > 0 ? data.sets.map((set) => set.code) : LOADING_SET_SLIDES).map((code, i) => (
          <button
            key={`set-${i}`}
            disabled={LOADING_SET_SLIDES.includes(code)}
            onClick={() => data.onSet(code)}
            className={cn(
              "group flex w-[60px] shrink-0 flex-col items-center gap-2 transition-transform duration-200",
              "hover:-translate-y-1.5",
            )}
          >
            <CardBack code={LOADING_SET_SLIDES.includes(code) ? null : code} index={i} className="w-[54px]" />
            <span
              className={cn(
                "relative z-10 text-center text-base leading-none font-bold text-text",
                "group-hover:text-[#f6c95e]",
                HARD_TEXT_SHADOW,
              )}
            >
              {LOADING_SET_SLIDES.includes(code) ? "\u00a0" : homeSetLabel(code)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function StepButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(DARK_PIXEL_BUTTON, "disabled:pointer-events-none disabled:opacity-30")}
      style={{ width: STEP_BUTTON_PX, height: STEP_BUTTON_PX }}
    >
      {children}
    </button>
  );
}

function fanWidth(packCount: number): number {
  return 1 + Math.max(0, packCount - 1) * FAN_STEP;
}

function firstShownSet(todayIndex: number, centerIndex: number): number {
  return Math.max(todayIndex + 1, centerIndex - 2);
}

function slideOffsets(count: number, todayIndex: number, centerIndex: number, fanCounts: number[]): number[] {
  const isDay = (i: number) => i <= todayIndex;
  const scaledWidth = (i: number) => {
    const width = isDay(i) ? fanWidth(fanCounts[i]) : 1;
    return i === centerIndex ? width : width * SIDE_SCALE;
  };
  const gapBetween = (left: number, right: number) => (isDay(left) || isDay(right) ? TODAY_GAP : SET_GAP);
  const offsets = Array.from({ length: count }, () => 0);
  for (let i = centerIndex + 1; i < count; i++) {
    offsets[i] = offsets[i - 1] + scaledWidth(i - 1) / 2 + gapBetween(i - 1, i) + scaledWidth(i) / 2;
  }
  for (let i = centerIndex - 1; i >= 0; i--) {
    offsets[i] = offsets[i + 1] - scaledWidth(i + 1) / 2 - gapBetween(i, i + 1) - scaledWidth(i) / 2;
  }
  const firstShown = firstShownSet(todayIndex, centerIndex);
  if (firstShown > todayIndex + 1) {
    offsets[todayIndex] = offsets[firstShown] - scaledWidth(firstShown) / 2 - TODAY_GAP - scaledWidth(todayIndex) / 2;
  }
  return offsets;
}

function useArrowKeys(step: (delta: number) => void) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return;
      }
      if (isTypingTarget(event.target) || document.querySelector('[role="dialog"]')) {
        return;
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        step(event.key === "ArrowLeft" ? -1 : 1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [step]);
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

function useSwipe(step: (delta: number) => void) {
  const startX = useRef<number | null>(null);
  const swiped = useRef(false);
  return {
    onPointerDown: (event: PointerEvent<HTMLDivElement>) => {
      startX.current = event.clientX;
      swiped.current = false;
    },
    onPointerUp: (event: PointerEvent<HTMLDivElement>) => {
      if (startX.current === null) {
        return;
      }
      const distance = event.clientX - startX.current;
      startX.current = null;
      if (Math.abs(distance) > 40) {
        swiped.current = true;
        step(distance < 0 ? 1 : -1);
      }
    },
    onPointerCancel: () => {
      startX.current = null;
    },
    onClickCapture: (event: MouseEvent<HTMLDivElement>) => {
      if (swiped.current) {
        event.stopPropagation();
        swiped.current = false;
      }
    },
  };
}
