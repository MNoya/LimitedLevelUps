import { useEffect, useState, type MouseEvent } from "react";
import { Check, Copy } from "lucide-react";
import { Tooltip } from "./Tooltip";
import { cn } from "../lib/utils";

const COPIED_RESET_MS = 2000;

export function CopyTextButton({
  text,
  label,
  ariaLabel,
  className,
}: {
  text: () => string;
  label: string;
  ariaLabel: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = window.setTimeout(() => setCopied(false), COPIED_RESET_MS);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setCopied(await copyToClipboard(text()));
  };

  return (
    <Tooltip label="Copy to Clipboard">
      <button
        type="button"
        onClick={copy}
        aria-label={ariaLabel}
        className={cn(
          "shrink-0 inline-flex items-center gap-1.5 rounded-full border bg-surface2 px-3 py-1.5",
          "font-display tracking-[0.14em] leading-none transition-colors cursor-pointer",
          "outline-none focus:outline-none focus-visible:outline-none hover:text-green hover:border-green/50",
          copied ? "text-green border-green/50" : "text-subtle border-border",
          className,
        )}
        style={{ fontSize: 13 }}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
        <span className="grid">
          <span className={cn("col-start-1 row-start-1", copied && "invisible")}>{label}</span>
          <span className={cn("col-start-1 row-start-1", !copied && "invisible")}>COPIED!</span>
        </span>
      </button>
    </Tooltip>
  );
}

async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return copyWithTextarea(text);
    }
  }
  return copyWithTextarea(text);
}

function copyWithTextarea(text: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied;
}
