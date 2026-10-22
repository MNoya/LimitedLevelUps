import type { ReactNode } from "react";
import { ExternalLink, Play, X } from "lucide-react";

import { cachedImageUrl } from "../../lib/dev-image-cache";
import { cn } from "../../lib/utils";
import { SITE_LINKS } from "../../data/site";
import { useDialogKeys } from "./GameChrome";
import { DARK_PIXEL_BUTTON, HARD_TEXT_SHADOW } from "./pixelStyles";

const HELP_STEP_NUMBER = cn(
  "grid size-7 shrink-0 place-items-center border-2 border-[color:var(--px-ink)] bg-[color:var(--px-accent)] pt-0.5",
  "font-display text-xl leading-none text-[color:var(--px-ink)] shadow-[2px_2px_0_#05070a]",
);

export interface GameHelpAction {
  label: string;
  onClick: () => void;
}

export function GameHelpDialog({
  open,
  onClose,
  action = { label: "Resume", onClick: onClose },
  title = "How to Play",
  art,
  artPosition,
  icon,
  playButton,
  footnote,
  className,
  children,
}: {
  open: boolean;
  onClose: () => void;
  action?: GameHelpAction;
  title?: string;
  art: string;
  artPosition: string;
  icon: ReactNode;
  playButton: string;
  footnote: string;
  className?: string;
  children: ReactNode;
}) {
  useDialogKeys(open, onClose);
  if (!open) {
    return null;
  }
  return (
    <div
      className={cn("fixed inset-0 z-50 grid place-items-center bg-[#05070a]/80 p-2 animate-fadeIn sm:p-4", className)}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="game-help-title"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "themed-scrollbar relative max-h-[calc(100dvh-1rem)] w-full max-w-[420px] overflow-y-auto animate-fadeUpIn",
          "border-[3px] border-[color:var(--px-ink)] bg-[color:var(--px-panel)] shadow-[6px_6px_0_#05070a]",
          "after:pointer-events-none after:absolute after:inset-0 after:z-20 after:content-['']",
          "after:shadow-[inset_0_0_0_2px_var(--px-rim)]",
        )}
      >
        <img
          src={cachedImageUrl(art)}
          alt=""
          aria-hidden
          className="pointer-events-none absolute top-0 right-0 h-56 w-[85%] object-cover opacity-60"
          style={{
            objectPosition: artPosition,
            maskImage:
              "linear-gradient(to right, transparent, black 45%), linear-gradient(to bottom, black 40%, transparent)",
            maskComposite: "intersect",
          }}
        />
        <div className="relative flex flex-col items-start gap-5 px-4 pt-4 sm:px-6">
          {icon}
          <h2 id="game-help-title" className={cn("font-display text-4xl leading-none text-text", HARD_TEXT_SHADOW)}>
            {title}
          </h2>
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className={cn(DARK_PIXEL_BUTTON, "absolute top-4 right-4 z-30 size-9")}
        >
          <X size={18} />
        </button>
        <div className="relative space-y-5 px-4 pt-5 text-[15px] leading-snug sm:px-6">{children}</div>
        <div className="relative px-4 pt-5 pb-4 sm:px-6">
          <button onClick={action.onClick} className={cn(playButton, "w-full py-3 text-2xl")}>
            <Play size={20} className="fill-current" />
            {action.label}
          </button>
          <p className="mt-3 text-center text-[13px] text-subtle">
            {footnote}{" "}
            <a
              href={SITE_LINKS.discord}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center font-bold text-[color:var(--px-accent)] hover:underline"
            >
              our Discord
              <ExternalLink size={13} className="ml-1" />
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}

export function HelpSection({
  title,
  centered = false,
  children,
}: {
  title: string;
  centered?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={cn(centered && "flex flex-col items-center")}>
      <h3 className={cn("mb-3 font-display text-2xl leading-none text-[color:var(--px-accent)]", HARD_TEXT_SHADOW)}>
        {title}
      </h3>
      {children}
    </section>
  );
}

export function HelpSteps({ steps }: { steps: string[] }) {
  return (
    <ol className="space-y-2.5">
      {steps.map((step, i) => (
        <li key={step} className="flex items-center gap-3">
          <span className={HELP_STEP_NUMBER}>{i + 1}</span>
          <span>{step}</span>
        </li>
      ))}
    </ol>
  );
}

export function HelpScoreRow({ plate, points, children }: { plate: ReactNode; points: number; children: ReactNode }) {
  return (
    <li className="contents">
      {plate}
      <span className="font-bold">{children}</span>
      <span className="font-display text-2xl leading-none text-[color:var(--px-accent)]">+{points}</span>
    </li>
  );
}
