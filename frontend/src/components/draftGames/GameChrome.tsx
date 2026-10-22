import { useEffect, useState, type ReactNode } from "react";
import { Check, ChevronLeft, Copy, Play } from "lucide-react";

import { copyToClipboard } from "../CopyTextButton";
import { cn } from "../../lib/utils";
import { ACCENT_BUTTON, DARK_PIXEL_BUTTON, HARD_TEXT_SHADOW, PIXEL_HEADING } from "./pixelStyles";
import { msUntilNextGameDay, type RoundMark } from "../../data/draftGames";
import type { NextPlay } from "./gameDay";

export const MARK_EMOJI: Record<RoundMark, string> = { hit: "🟩", close: "🟨", miss: "🟥" };
const GAME_BUTTON = cn(
  "inline-flex items-center justify-center gap-2 rounded-lg border border-green/55 bg-green/15 px-5 py-2.5",
  "font-semibold text-green transition-[background-color,transform] hover:bg-green/25 active:scale-[0.97]",
);

export function useDialogKeys(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        e.stopImmediatePropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);
}

export function ShareButton({
  text,
  className,
  buttonClass = GAME_BUTTON,
}: {
  text: string;
  className?: string;
  buttonClass?: string;
}) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);
  return (
    <button onClick={async () => setCopied(await copyToClipboard(text))} className={cn(buttonClass, "py-3", className)}>
      {copied ? <Check size={18} /> : <Copy size={18} />}
      {copied ? "Copied" : "Copy for Discord"}
    </button>
  );
}

export function LoadingLabel({ label, className }: { label: string; className?: string }) {
  return (
    <span className={cn(PIXEL_HEADING, className)}>
      {label}
      {[0, 1, 2].map((dot) => (
        <span
          key={dot}
          className="inline-block"
          style={{ animation: "pulse 1.2s ease-in-out infinite", animationDelay: `${dot * 200}ms` }}
        >
          .
        </span>
      ))}
    </span>
  );
}

export function DailyCountdown({ label, className }: { label: string; className?: string }) {
  const [remaining, setRemaining] = useState(msUntilNextGameDay);
  useEffect(() => {
    const timer = window.setInterval(() => setRemaining(msUntilNextGameDay()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const hours = Math.floor(remaining / 3_600_000);
  const minutes = Math.floor((remaining % 3_600_000) / 60_000);
  return (
    <p className={cn("flex items-baseline gap-2 font-display text-xl leading-none text-subtle", className)}>
      {label}
      <span className={cn("text-2xl", PIXEL_HEADING)}>
        {hours}h {minutes}m
      </span>
    </p>
  );
}

export function GameStatus({ children }: { children: ReactNode }) {
  return <div className="py-16 text-center text-subtle">{children}</div>;
}

export function MenuButton({
  onClick,
  className,
  labelClassName,
  iconSize = 18,
}: {
  onClick: () => void;
  className: string;
  labelClassName?: string;
  iconSize?: number;
}) {
  return (
    <button onClick={onClick} aria-label="Menu" className={cn(DARK_PIXEL_BUTTON, className)}>
      <ChevronLeft size={iconSize} strokeWidth={3} />
      <span className={labelClassName}>Menu</span>
    </button>
  );
}

export function HelpSquareButton({
  onClick,
  label = "How to Play",
  className,
}: {
  onClick: () => void;
  label?: string;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={cn(DARK_PIXEL_BUTTON, "size-10 shrink-0 text-xl", className)}
    >
      ?
    </button>
  );
}

export function PlayButton({
  label,
  onClick,
  icon,
  className,
}: {
  label: string;
  onClick: () => void;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <button data-play onClick={onClick} className={cn(ACCENT_BUTTON, className)}>
      {icon ?? <Play size={22} className="fill-current" />}
      {label}
    </button>
  );
}

export function DayEndButtons({
  next,
  onNext,
  onExit,
  menuClassName,
  nextClassName,
}: {
  next: NextPlay;
  onNext: (() => void) | null;
  onExit: () => void;
  menuClassName?: string;
  nextClassName?: string;
}) {
  return (
    <>
      <MenuButton onClick={onExit} iconSize={24} className={cn("py-3.5 pr-10 pl-7 text-3xl", menuClassName)} />
      {onNext && (
        <PlayButton label={next.label} onClick={onNext} className={cn("px-10 py-3.5 text-3xl", nextClassName)} />
      )}
    </>
  );
}

export function DayPoints({ points, max, className }: { points: number; max: number; className?: string }) {
  return (
    <span className={cn("font-display text-3xl leading-none text-[#f6c95e]", HARD_TEXT_SHADOW, className)}>
      {points}
      <span className="text-2xl"> of {max} Points</span>
    </span>
  );
}
