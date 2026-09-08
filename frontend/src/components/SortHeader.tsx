import type { ReactNode } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "../lib/utils";

export type SortDir = "asc" | "desc";

export function SortHeaderButton({
  label,
  active,
  dir,
  onClick,
  align = "right",
  inline = false,
  fill = false,
  trailing = null,
  className,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "right" | "center" | "left";
  inline?: boolean;
  fill?: boolean;
  trailing?: ReactNode;
  className?: string;
}) {
  const Icon = active && dir === "asc" ? ChevronUp : ChevronDown;

  if (fill) {
    const justify =
      align === "center" ? "justify-center" : align === "left" ? "justify-start" : "justify-end";
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label={`Sort by ${label}`}
        aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
        className={cn(
          "flex w-full items-center gap-0.5 cursor-pointer transition-colors tracking-[inherit] text-[inherit] font-[inherit]",
          justify,
          active ? "text-text" : "hover:text-text",
          className,
        )}
      >
        <span>{label}</span>
        <Icon
          size={11}
          strokeWidth={2.5}
          className={cn("shrink-0", active ? "opacity-100" : "opacity-30")}
          aria-hidden="true"
        />
        {trailing}
      </button>
    );
  }

  const centered = align === "center";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Sort by ${label}`}
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={cn(
        "relative cursor-pointer transition-colors tracking-[inherit] text-[inherit] font-[inherit]",
        inline
          ? "inline-flex items-center"
          : centered
            ? "flex w-full items-center justify-center gap-0.5"
            : "block w-full text-right",
        active ? "text-text" : "hover:text-text",
      )}
    >
      <span>{label}</span>
      <Icon
        size={11}
        strokeWidth={2.5}
        className={cn(
          centered ? "shrink-0" : "absolute left-full top-1/2 -translate-y-1/2 ml-0.5 shrink-0",
          active ? "opacity-100" : "opacity-30",
        )}
        aria-hidden="true"
      />
    </button>
  );
}
