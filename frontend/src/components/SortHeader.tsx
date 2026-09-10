import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "../lib/utils";

export type SortDir = "asc" | "desc";

type SortHeaderButtonProps = {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "right" | "center" | "left";
  inline?: boolean;
  fill?: boolean;
  grow?: boolean;
  trailing?: ReactNode;
  className?: string;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "onClick">;

export const SortHeaderButton = forwardRef<HTMLButtonElement, SortHeaderButtonProps>(function SortHeaderButton({
  label,
  active,
  dir,
  onClick,
  align = "right",
  inline = false,
  fill = false,
  grow = true,
  trailing = null,
  className,
  ...rest
}, ref) {
  const Icon = active && dir === "asc" ? ChevronUp : ChevronDown;

  if (fill) {
    const justify =
      align === "center" ? "justify-center" : align === "left" ? "justify-start" : "justify-end";
    return (
      <button
        ref={ref}
        type="button"
        onClick={onClick}
        aria-label={`Sort by ${label}`}
        aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
        className={cn(
          "flex items-center gap-0.5 cursor-pointer transition-colors tracking-[inherit] text-[inherit] font-[inherit]",
          grow ? "w-full" : "w-fit",
          justify,
          active ? "text-text" : "hover:text-text",
          className,
        )}
        {...rest}
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
      ref={ref}
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
      {...rest}
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
});
