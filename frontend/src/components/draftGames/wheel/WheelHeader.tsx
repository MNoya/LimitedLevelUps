import { useLayoutEffect, useRef, type ReactNode } from "react";
import { ChevronLeft, Eye, EyeOff, RotateCcw } from "lucide-react";

import { SetGlyph } from "../../Brand";
import { LuScrollText } from "../../Icons";
import { Tooltip } from "../../Tooltip";
import { cn } from "../../../lib/utils";
import { ordinal, type RoundMark } from "../../../data/draftGames";
import { MenuButton } from "../GameChrome";
import { DARK_PIXEL_BUTTON, HARD_TEXT_SHADOW, PIXEL_HEADING, PIXEL_TOOLTIP } from "../pixelStyles";
import { useFlip } from "./motion";
import { WheelEmoji } from "./WheelEmoji";

export type WheelProgress =
  | {
      kind: "featured";
      steps: { setCode: string; name: string; mark: RoundMark | null; id?: string }[];
      current: number | null;
      onSelect?: (index: number) => void;
    }
  | { kind: "free"; packNumber: number };

export interface WheelHeaderTools {
  draftHref?: string;
  draftersShown?: boolean;
  onToggleDrafters?: () => void;
  onReset?: () => void;
}

const STEP_FILL: Record<RoundMark, string> = {
  hit: "bg-green text-[#0b1a10]",
  close: "bg-[#f6c95e] text-[#1a120b]",
  miss: "bg-red text-[#1a0b0b]",
};

export function WheelHeader({
  setCode,
  title,
  subtitle,
  dayLabel,
  progress,
  tools = {},
  onHelp,
  onExit,
  compact = false,
  action,
  center,
  className,
}: {
  setCode: string | null;
  title: string;
  subtitle?: string;
  dayLabel?: string;
  progress: WheelProgress;
  tools?: WheelHeaderTools;
  onHelp?: () => void;
  onExit?: () => void;
  compact?: boolean;
  action?: ReactNode;
  center?: ReactNode;
  className?: string;
}) {
  if (compact) {
    return (
      <div className={cn("flex flex-col justify-center gap-1.5", className)}>
        <div className="flex h-7 items-center gap-2">
          {setCode && !center && <SetTile code={setCode} small />}
          <div className={cn("flex min-w-0 items-baseline gap-2", !center && "flex-1")}>
            {dayLabel && <span className={cn("shrink-0 text-base", PIXEL_HEADING)}>{dayLabel}</span>}
            <span className={cn("truncate font-display text-xl leading-none text-text", HARD_TEXT_SHADOW)}>
              {title}
            </span>
          </div>
          {center && <span className="mr-auto">{center}</span>}
          {onExit && (
            <IconButton label="Menu" onClick={onExit} className="size-7">
              <ChevronLeft size={16} strokeWidth={3} />
            </IconButton>
          )}
          {onHelp && (
            <IconButton label="How to Play" onClick={onHelp} className="size-7 text-lg">
              ?
            </IconButton>
          )}
        </div>
        <div className="flex h-7 items-center gap-2">
          <ProgressRow progress={progress} small />
          <ToolButtons tools={tools} small />
          {action && <span className="ml-auto">{action}</span>}
        </div>
      </div>
    );
  }
  return (
    <div className={className}>
      <div className="flex items-start gap-3">
        {setCode ? <SetTile code={setCode} /> : <WheelEmoji spinToken={null} scale={1.6} />}
        <div className="flex min-h-11 min-w-0 flex-col justify-center">
          <div
            className={cn("truncate font-display text-2xl leading-none text-text max-2xl:text-xl", HARD_TEXT_SHADOW)}
          >
            {title}
          </div>
          {(subtitle ?? dayLabel) && <div className={cn("mt-1 text-base", PIXEL_HEADING)}>{subtitle ?? dayLabel}</div>}
        </div>
        {center && <div className="flex h-11 items-center">{center}</div>}
        <div className={cn("ml-auto flex shrink-0 gap-3", center && "h-11 items-center")}>
          {onExit && (
            <MenuButton
              onClick={onExit}
              className="h-9 pr-3 pl-2 text-lg max-2xl:w-9 max-2xl:px-0"
              labelClassName="max-2xl:hidden"
            />
          )}
          {onHelp && (
            <IconButton label="How to Play" onClick={onHelp} className="size-9 text-xl">
              ?
            </IconButton>
          )}
        </div>
      </div>
      <div className="mt-2 flex min-h-9 flex-wrap items-center gap-x-4 gap-y-2">
        <ProgressRow progress={progress} />
        <ToolButtons tools={tools} />
      </div>
    </div>
  );
}

function ToolButtons({ tools, small = false }: { tools: WheelHeaderTools; small?: boolean }) {
  const size = small ? "size-7" : "size-9";
  const iconSize = small ? 14 : 17;
  return (
    <div className="ml-auto flex items-center gap-2 animate-fadeIn">
      {tools.draftHref && (
        <Tooltip label="Draft Log">
          <a
            href={tools.draftHref}
            target="_blank"
            rel="noopener"
            aria-label="Draft Log"
            className={cn(DARK_PIXEL_BUTTON, size)}
          >
            <LuScrollText size={iconSize} aria-hidden="true" />
          </a>
        </Tooltip>
      )}
      {tools.onToggleDrafters && (
        <IconButton
          label={tools.draftersShown ? "Hide Drafters" : "Show Drafters"}
          onClick={tools.onToggleDrafters}
          className={size}
        >
          {tools.draftersShown ? <EyeOff size={iconSize} /> : <Eye size={iconSize} />}
        </IconButton>
      )}
      {tools.onReset && (
        <IconButton label="Replay Today" onClick={tools.onReset} className={size}>
          <RotateCcw size={iconSize - 1} strokeWidth={3} />
        </IconButton>
      )}
    </div>
  );
}

function IconButton({
  label,
  onClick,
  className,
  children,
}: {
  label: string;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Tooltip label={label}>
      <button onClick={onClick} aria-label={label} className={cn(DARK_PIXEL_BUTTON, className)}>
        {children}
      </button>
    </Tooltip>
  );
}

function SetTile({ code, small = false }: { code: string; small?: boolean }) {
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center border-[#1a120b] bg-[#2b3445]",
        small ? "size-7 border-2 shadow-[2px_2px_0_#05070a]" : "size-11 border-[3px] shadow-[3px_3px_0_#05070a]",
      )}
    >
      <SetGlyph code={code} size={small ? 16 : 24} className="text-[#fff1d6]" />
    </span>
  );
}

function ProgressRow({ progress, small = false }: { progress: WheelProgress; small?: boolean }) {
  if (progress.kind === "free") {
    return (
      <span className={cn("translate-y-1", small ? "text-lg" : "text-xl", PIXEL_HEADING)}>
        {ordinal(progress.packNumber)} Pack
      </span>
    );
  }
  return <StepSquares progress={progress} small={small} />;
}

function StepSquares({ progress, small }: { progress: Extract<WheelProgress, { kind: "featured" }>; small: boolean }) {
  const rowRef = useRef<HTMLDivElement>(null);
  const firstStep = progress.steps[0]?.id;
  const previousFirst = useRef(firstStep);
  const oldestDropped = previousFirst.current !== undefined && previousFirst.current !== firstStep;
  useFlip(rowRef, null, undefined, oldestDropped);
  useLayoutEffect(() => {
    previousFirst.current = firstStep;
  });
  return (
    <div ref={rowRef} className={cn("flex items-center", small ? "gap-1.5" : "gap-2")} aria-label="Featured packs">
      {progress.steps.map((step, i) => (
        <Tooltip
          key={step.id ?? `${step.setCode}-${i}`}
          label={`${step.name} #${i + 1}`}
          side="bottom"
          delayDuration={0}
          hideArrow
          className={PIXEL_TOOLTIP}
        >
          <span data-flip={step.id ?? `${step.setCode}-${i}`} className="flex">
            <button
              type="button"
              onClick={() => progress.onSelect?.(i)}
              disabled={!progress.onSelect || i === progress.current}
              aria-label={`${step.name} #${i + 1}`}
              aria-current={i === progress.current ? "step" : undefined}
              className={cn(
                "relative grid place-items-center border-2 border-[#1a120b] shadow-[2px_2px_0_#05070a]",
                small ? "size-7" : "size-9",
                "enabled:hover:-translate-y-0.5 enabled:hover:brightness-125",
                step.mark ? cn(STEP_FILL[step.mark], "animate-flipIn") : "bg-[#2b3445] text-subtle",
                i === progress.current && "outline outline-2 outline-offset-2 outline-[#f6c95e]",
                i === progress.current && !step.mark && "bg-[#f6c95e] text-[#1a120b]",
              )}
            >
              <SetGlyph code={step.setCode} size={small ? 14 : 17} className="text-current" />
            </button>
          </span>
        </Tooltip>
      ))}
    </div>
  );
}
