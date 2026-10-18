import type { ReactNode } from "react";
import { ChevronLeft, Eye, EyeOff, RotateCcw } from "lucide-react";

import { SetGlyph } from "../../Brand";
import { LuScrollText } from "../../Icons";
import { Tooltip } from "../../Tooltip";
import { cn } from "../../../lib/utils";
import type { RoundMark } from "../../../data/draftGames";
import { DARK_PIXEL_BUTTON, HARD_TEXT_SHADOW, PIXEL_HEADING } from "../pixelStyles";
import { WheelEmoji } from "./WheelEmoji";

export type WheelProgress =
  | {
      kind: "featured";
      steps: { setCode: string; name: string; mark: RoundMark | null }[];
      current: number | null;
      onSelect?: (index: number) => void;
    }
  | { kind: "free"; packNumber: number; points: number; max: number };

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
  className?: string;
}) {
  if (compact) {
    return (
      <div className={cn("flex flex-col justify-center gap-1.5", className)}>
        <div className="flex h-7 items-center gap-2">
          <div className="flex min-w-0 flex-1 items-baseline gap-2">
            {dayLabel && <span className={cn("shrink-0 text-base", PIXEL_HEADING)}>{dayLabel}</span>}
            <span className={cn("truncate font-display text-xl leading-none text-text", HARD_TEXT_SHADOW)}>
              {title}
            </span>
          </div>
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
        </div>
      </div>
    );
  }
  return (
    <div className={className}>
      <div className="flex items-start gap-3">
        {setCode ? (
          <span
            className={cn(
              "grid size-11 shrink-0 place-items-center border-[3px] border-[#1a120b] bg-[#2b3445]",
              "shadow-[3px_3px_0_#05070a]",
            )}
          >
            <SetGlyph code={setCode} size={24} className="text-[#fff1d6]" />
          </span>
        ) : (
          <WheelEmoji spinToken={null} scale={1.6} />
        )}
        <div className="flex min-h-11 min-w-0 flex-col justify-center">
          <div className={cn("truncate font-display text-2xl leading-none text-text", HARD_TEXT_SHADOW)}>{title}</div>
          {(subtitle ?? dayLabel) && <div className={cn("mt-1 text-base", PIXEL_HEADING)}>{subtitle ?? dayLabel}</div>}
        </div>
        <div className="ml-auto flex shrink-0 gap-3">
          {onExit && (
            <button
              onClick={onExit}
              aria-label="Menu"
              className={cn(DARK_PIXEL_BUTTON, "h-9 pr-3 pl-2 text-lg max-2xl:w-9 max-2xl:px-0")}
            >
              <ChevronLeft size={18} strokeWidth={3} />
              <span className="max-2xl:hidden">Menu</span>
            </button>
          )}
          {onHelp && (
            <IconButton label="How to Play" onClick={onHelp} className="size-9 text-xl">
              ?
            </IconButton>
          )}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
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
        <IconButton label="Reset" onClick={tools.onReset} className={size}>
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

function ProgressRow({ progress, small = false }: { progress: WheelProgress; small?: boolean }) {
  if (progress.kind === "free") {
    return (
      <div className="flex items-baseline gap-x-3">
        <span className={cn(small ? "text-lg" : "text-xl", PIXEL_HEADING)}>Pack {progress.packNumber}</span>
        {progress.max > 0 && (
          <span className="text-sm text-subtle">
            <span className="font-display text-xl text-text">{progress.points}</span> of {progress.max} points
          </span>
        )}
      </div>
    );
  }
  return (
    <div className={cn("flex items-center", small ? "gap-1.5" : "gap-2")} aria-label="Featured packs">
      {progress.steps.map((step, i) => (
        <button
          key={`${step.setCode}-${i}`}
          type="button"
          onClick={() => progress.onSelect?.(i)}
          disabled={!progress.onSelect || i === progress.current}
          aria-label={`${step.name} #${i + 1}`}
          aria-current={i === progress.current ? "step" : undefined}
          className={cn(
            "group/step relative grid place-items-center border-2 border-[#1a120b] shadow-[2px_2px_0_#05070a]",
            small ? "size-7" : "size-9",
            "enabled:hover:-translate-y-0.5 enabled:hover:brightness-125",
            step.mark ? cn(STEP_FILL[step.mark], "animate-flipIn") : "bg-[#2b3445] text-subtle",
            i === progress.current && "outline outline-2 outline-offset-2 outline-[#f6c95e]",
            i === progress.current && !step.mark && "text-text",
          )}
        >
          <SetGlyph code={step.setCode} size={small ? 14 : 17} className="text-current" />
          <span
            className={cn(
              "pointer-events-none absolute top-full left-1/2 z-40 mt-2.5 -translate-x-1/2 whitespace-nowrap",
              "border-2 border-[#1a120b] bg-[#16110c] px-2 py-1 text-sm leading-none font-bold text-text",
              "opacity-0 shadow-[3px_3px_0_#05070a] transition-opacity group-hover/step:opacity-100",
            )}
          >
            {step.name} #{i + 1}
          </span>
        </button>
      ))}
    </div>
  );
}
