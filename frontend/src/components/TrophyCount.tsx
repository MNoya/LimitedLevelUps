import { Trophy } from "./Brand";
import { cn } from "../lib/utils";

// Trophy icon + count, used wherever the marquee stat shows up. Sizes track the
// row contexts where it appears (compact = inline mini-rows; sm = sidebar
// captions; md = main leaderboard row). `display` swaps the mono count for the
// display face, which needs a larger point size to match the same optical height.

export function TrophyCount({
  count,
  size = "sm",
  display = false,
  fixedDigits,
  className,
}: {
  count: number;
  size?: "compact" | "sm" | "md";
  display?: boolean;
  fixedDigits?: number;
  className?: string;
}) {
  const trophySize = size === "compact" ? 12 : size === "sm" ? 12 : 16;
  const monoSize = size === "compact" ? "text-[12px]" : size === "sm" ? "text-[11px]" : "text-[15px]";
  const displaySize = size === "compact" ? "text-[14px]" : size === "sm" ? "text-[13px]" : "text-[17px]";
  const countStyle = fixedDigits
    ? { display: "inline-block", minWidth: `${fixedDigits}ch`, textAlign: "right" as const }
    : undefined;
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <Trophy size={trophySize} color="#ffc63a" />
      <span
        className={cn(
          display ? cn("font-display leading-none", displaySize) : cn("mono", monoSize),
          !display && size === "md" && "font-semibold",
        )}
        style={countStyle}
      >
        {count}
      </span>
    </span>
  );
}
