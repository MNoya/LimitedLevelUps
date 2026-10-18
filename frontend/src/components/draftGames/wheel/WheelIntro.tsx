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
import { ChevronLeft, ChevronRight, Play, Zap } from "lucide-react";

import { cn } from "../../../lib/utils";
import {
  DAILY_ROUNDS,
  setShortLabel,
  useFeaturedSetCodes,
  useWheelSets,
  type WheelSetOption,
  shortDayLabel,
} from "../../../data/draftGames";
import { DARK_PIXEL_BUTTON, GOLD_BUTTON, HARD_TEXT_SHADOW, PIXEL_TAG } from "../pixelStyles";
import { CardBack } from "./CardBack";
import { readFeaturedDay } from "./useWheelDay";
import { WheelTitle } from "./WheelTitle";

export const FEATURED_PLAY = "featured";

export function WheelIntro({
  dayKey,
  onPlay,
  onHelp,
  onQuickHelp,
}: {
  dayKey: string;
  onPlay: (play: string) => void;
  onHelp: () => void;
  onQuickHelp: () => void;
}) {
  const { sets } = useWheelSets();
  const featuredSets = useFeaturedSetCodes(dayKey);
  const featuredDay = readFeaturedDay(dayKey);
  const played = featuredDay ? Object.keys(featuredDay.locked).length : 0;
  let featuredAction = "Play";
  if (featuredDay && featuredDay.advanced >= DAILY_ROUNDS) {
    featuredAction = "See Results";
  } else if (played > 0) {
    featuredAction = "Continue";
  }
  const data: IntroData = {
    dayLabel: shortDayLabel(dayKey),
    featuredSets,
    featuredAction,
    sets,
    onFeatured: () => onPlay(FEATURED_PLAY),
    onSet: onPlay,
    onHelp,
    onQuickHelp,
  };

  return (
    <div className="mx-auto flex w-full max-w-[880px] flex-1 flex-col items-center pb-4 text-center">
      <div className="mt-1 sm:hidden">
        <WheelTitle scale={3} />
      </div>
      <div className="hidden sm:block [@media(max-height:760px)]:hidden">
        <WheelTitle scale={6} />
      </div>
      <div className="hidden [@media(max-height:760px)]:sm:block">
        <WheelTitle scale={4} />
      </div>
      <PickerIntro data={data} />
    </div>
  );
}

interface IntroData {
  dayLabel: string;
  featuredSets: string[];
  featuredAction: string;
  sets: WheelSetOption[];
  onFeatured: () => void;
  onSet: (code: string) => void;
  onHelp: () => void;
  onQuickHelp: () => void;
}

const TODAY_SLIDE = "today";
const FAN_STEP = 0.74;
const SIDE_SCALE = 0.78;
const SET_GAP = 0.14;
const TODAY_GAP = 0.75;
const STEP_BUTTON_PX = 44;

function PickerIntro({ data }: { data: IntroData }) {
  const slides = useMemo(() => [TODAY_SLIDE, ...data.sets.map((set) => set.code)], [data.sets]);
  const [requestedIndex, setRequestedIndex] = useState(0);
  const lastIndex = slides.length - 1;
  const selectedIndex = Math.min(requestedIndex, lastIndex);
  const selected = slides[selectedIndex];
  const isToday = selected === TODAY_SLIDE;
  const selectedSet = data.sets.find((set) => set.code === selected);
  const step = useCallback(
    (delta: number) => setRequestedIndex((index) => Math.max(0, Math.min(lastIndex, index + delta))),
    [lastIndex],
  );
  useArrowKeys(step);
  const swipe = useSwipe(step);
  const play = () => (isToday ? data.onFeatured() : data.onSet(selected));
  const offsets = slideOffsets(slides, selectedIndex, data.featuredSets.length);
  const firstSetEdge = fanWidth(data.featuredSets.length) / 2 + TODAY_GAP;

  return (
    <div
      className={cn(
        "group/picker mt-4 flex w-full flex-col items-center sm:mt-8 sm:[--u:108px]",
        "max-sm:flex-1 max-sm:[--u:clamp(64px,10dvh,80px)]",
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
          {isToday ? (
            <TodayHeading dayLabel={data.dayLabel} />
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
          const todaySlide = slide === TODAY_SLIDE;
          const hidden = !todaySlide && (i < firstShownSet(selectedIndex) || Math.abs(offsets[i]) > 5.5);
          const faded = todaySlide && firstShownSet(selectedIndex) > 1;
          const transform = `translateX(calc(-50% + var(--u) * ${offsets[i]})) scale(${center ? 1 : SIDE_SCALE})`;
          return (
            <button
              key={slide}
              onClick={() => (center ? play() : setRequestedIndex(i))}
              aria-label={slide === TODAY_SLIDE ? "Today's Packs" : data.sets[i - 1]?.name}
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
                {slide === TODAY_SLIDE ? (
                  <TodayFan data={data} lift={center} />
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
                <SlideLabel slide={slide} center={center} featuredSets={data.featuredSets} />
              </span>
            </button>
          );
        })}
      </div>
      <div className="mt-10 flex flex-col items-center gap-5 max-sm:hidden [@media(max-height:760px)]:sm:mt-6">
        <button
          onClick={play}
          className={cn(
            GOLD_BUTTON,
            "picker-play",
            "[@media(hover:hover)]:group-has-[.picker-center:hover]/picker:-translate-y-0.5",
            "[@media(hover:hover)]:group-has-[.picker-center:hover]/picker:brightness-110",
            "[@media(hover:hover)]:group-has-[.picker-center:hover]/picker:shadow-[6px_7px_0_#05070a]",
            "px-12 py-3.5 text-3xl",
            "[@media(max-height:760px)]:sm:py-2 [@media(max-height:760px)]:sm:text-2xl",
          )}
        >
          <Play size={22} className="fill-current" />
          {isToday ? data.featuredAction : "Play"}
        </button>
        <QuickModeRow onHelp={data.onQuickHelp} />
      </div>
    </div>
  );
}

function QuickModeRow({ onHelp }: { onHelp: () => void }) {
  return (
    <div className="flex items-center gap-3">
      <Link to="/wheel-of-fortune/quick" className={cn(DARK_PIXEL_BUTTON, "h-11 px-5 text-xl")}>
        <Zap size={18} className="fill-current" />
        Quick Mode
      </Link>
      <button onClick={onHelp} aria-label="About Quick Mode" className={cn(DARK_PIXEL_BUTTON, "size-11 text-xl")}>
        ?
      </button>
    </div>
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
    <div className="mt-4 flex w-full flex-1 flex-col items-center justify-evenly sm:hidden">
      <div className="flex flex-col items-center">
        <TodayHeading dayLabel={data.dayLabel} />
        <button
          onClick={data.onFeatured}
          aria-label="Play Today's Packs"
          className="mt-3 flex flex-col items-center gap-2"
        >
          <TodayFan data={data} lift={false} />
          <span className={cn("relative z-30 text-lg leading-none font-bold text-[#f6c95e]", HARD_TEXT_SHADOW)}>
            <SlideLabel slide={TODAY_SLIDE} center featuredSets={data.featuredSets} />
          </span>
        </button>
      </div>
      <div className="mt-4 flex flex-col items-center gap-4">
        <button onClick={data.onFeatured} className={cn(GOLD_BUTTON, "px-10 py-2.5 text-2xl")}>
          <Play size={22} className="fill-current" />
          {data.featuredAction}
        </button>
        <QuickModeRow onHelp={data.onQuickHelp} />
      </div>
      <FreePlayRow data={data} title="Or Select a Set" className="mt-5" />
    </div>
  );
}

function TodayHeading({ dayLabel }: { dayLabel: string }) {
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
      Today's Packs
    </h2>
  );
}

function SlideLabel({ slide, center, featuredSets }: { slide: string; center: boolean; featuredSets: string[] }) {
  if (slide !== TODAY_SLIDE) {
    return setShortLabel(slide);
  }
  if (!center) {
    return "Today";
  }
  return (
    <span className="flex gap-x-4">
      {packCounts(featuredSets).map(({ code, count }) => (
        <span key={code}>
          {setShortLabel(code)} x{count}
        </span>
      ))}
    </span>
  );
}

function packCounts(codes: string[]): { code: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const code of codes) {
    counts.set(code, (counts.get(code) ?? 0) + 1);
  }
  return [...counts].map(([code, count]) => ({ code, count }));
}

function TodayFan({ data, lift }: { data: IntroData; lift: boolean }) {
  const count = data.featuredSets.length;
  return (
    <span
      className="relative mb-[calc(var(--u)*0.12)] block h-[calc(var(--u)*1.55)]"
      style={{
        width: `calc(var(--u) * ${fanWidth(count)})`,
      }}
    >
      {data.featuredSets.map((code, i) => {
        const offset = i - (count - 1) / 2;
        return (
          <span
            key={`${code}-${i}`}
            className={cn("group/pack absolute bottom-0 origin-bottom", lift && "hover:!z-20")}
            style={{
              left: `calc(var(--u) * ${i * FAN_STEP})`,
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
      <h2 className={cn("text-center font-display text-2xl leading-none text-[#f6c95e]", HARD_TEXT_SHADOW)}>{title}</h2>
      <div className={cn("mt-4 flex gap-x-2 overflow-x-auto px-2 pt-2 pb-2 [justify-content:safe_center]")}>
        {data.sets.map((set, i) => (
          <button
            key={set.code}
            onClick={() => data.onSet(set.code)}
            className={cn(
              "group flex w-[60px] shrink-0 flex-col items-center gap-2 transition-transform duration-200",
              "hover:-translate-y-1.5",
            )}
          >
            <CardBack code={set.code} index={i} className="w-[54px]" />
            <span
              className={cn(
                "relative z-10 text-center text-base leading-none font-bold text-text",
                "group-hover:text-[#f6c95e]",
                HARD_TEXT_SHADOW,
              )}
            >
              {setShortLabel(set.code)}
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

function firstShownSet(centerIndex: number): number {
  return Math.max(1, centerIndex - 2);
}

function slideOffsets(slides: string[], centerIndex: number, packCount: number): number[] {
  const scaledWidth = (i: number) => {
    const width = slides[i] === TODAY_SLIDE ? fanWidth(packCount) : 1;
    return i === centerIndex ? width : width * SIDE_SCALE;
  };
  const gapBetween = (left: number, right: number) =>
    slides[left] === TODAY_SLIDE || slides[right] === TODAY_SLIDE ? TODAY_GAP : SET_GAP;
  const offsets = slides.map(() => 0);
  for (let i = centerIndex + 1; i < slides.length; i++) {
    offsets[i] = offsets[i - 1] + scaledWidth(i - 1) / 2 + gapBetween(i - 1, i) + scaledWidth(i) / 2;
  }
  for (let i = centerIndex - 1; i >= 0; i--) {
    offsets[i] = offsets[i + 1] - scaledWidth(i + 1) / 2 - gapBetween(i, i + 1) - scaledWidth(i) / 2;
  }
  const firstShown = firstShownSet(centerIndex);
  if (firstShown > 1) {
    offsets[0] = offsets[firstShown] - scaledWidth(firstShown) / 2 - TODAY_GAP - scaledWidth(0) / 2;
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
