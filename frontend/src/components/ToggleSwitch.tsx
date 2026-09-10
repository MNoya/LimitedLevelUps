import { cn } from "../lib/utils";

export function ToggleSwitch({ on, className }: { on: boolean; className?: string }) {
  return (
    <span
      className={cn("relative h-[18px] w-8 shrink-0 rounded-full transition-colors", on ? "bg-green" : "bg-border2", className)}
    >
      <span
        className={cn(
          "absolute top-[3px] h-3.5 w-3.5 rounded-full bg-white transition-all",
          on ? "left-[15px]" : "left-[1px]",
        )}
      />
    </span>
  );
}
