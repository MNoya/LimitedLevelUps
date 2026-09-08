import type React from "react";
import { cn } from "../lib/utils";

export function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 py-2 px-1.5 bg-transparent cursor-pointer font-display text-[14px] tracking-[0.16em] leading-none transition-colors border-b-2 border-solid inline-flex items-center justify-center gap-1.5",
        active ? "text-text border-green" : "text-muted border-transparent",
      )}
      style={active ? { marginBottom: -1 } : undefined}
    >
      {children}
    </button>
  );
}
