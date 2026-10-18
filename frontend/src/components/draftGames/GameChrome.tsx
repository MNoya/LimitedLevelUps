import { useEffect, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";

import { copyToClipboard } from "../CopyTextButton";
import { cn } from "../../lib/utils";
import type { RoundMark } from "../../data/draftGames";

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

export function GameStatus({ children }: { children: ReactNode }) {
  return <div className="py-16 text-center text-subtle">{children}</div>;
}
