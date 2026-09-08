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
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "right" | "center";
  inline?: boolean;
}) {
  const centered = align === "center";
  const Icon = active && dir === "asc" ? ChevronUp : ChevronDown;
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
