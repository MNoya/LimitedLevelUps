import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";

export function ProPlaySkeleton({ layout, header }: { layout: "sheet" | "replay"; header?: ReactNode }) {
  const isMobile = useIsMobile(1024);
  const tiles = <TileGridSkeleton compact={isMobile} />;
  if (layout === "sheet" && !isMobile) {
    return (
      <main className="flex-1 min-h-0 grid grid-cols-[510px_1fr] overflow-hidden">
        <section className="h-full border-r border-border bg-surface px-6 py-6 flex flex-col items-center gap-[70px]">
          {header}
          <div className="grid grid-cols-2 gap-[18px]">
            {Array.from({ length: 4 }, (_, index) => (
              <span key={index} className="w-[172px] h-[240px] rounded-[8px] border-2 border-border2 bg-bg" />
            ))}
          </div>
        </section>
        <section className="min-w-0 px-7 pt-[60px]">{tiles}</section>
      </main>
    );
  }
  return (
    <main className="flex-1">
      <div
        className={cn(
          "bg-surface border-b border-border flex items-center justify-center",
          isMobile ? "min-h-[118px] px-3 py-3" : "min-h-[132px] py-6",
        )}
      >
        {header}
      </div>
      <div className="h-[45px] border-b border-border" />
      <div className={cn("max-w-[1400px] mx-auto", isMobile ? "px-3 pt-3" : "px-7 pt-6")}>{tiles}</div>
    </main>
  );
}

function TileGridSkeleton({ compact }: { compact: boolean }) {
  const nameWidths = [62, 48, 70, 55, 66, 44, 58, 74];
  return (
    <div
      className={cn("grid", compact ? "gap-1.5" : "gap-2.5")}
      style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${compact ? 160 : 220}px, 1fr))` }}
    >
      {Array.from({ length: compact ? 12 : 24 }, (_, index) => (
        <div
          key={index}
          className={cn("flex items-center gap-3 border border-border bg-surface", compact ? "h-12" : "h-16")}
        >
          <span className={cn("self-stretch shrink-0 bg-surface2", compact ? "w-12" : "w-16")} />
          <span className="h-3 bg-surface2" style={{ width: `${nameWidths[index % nameWidths.length]}%` }} />
        </div>
      ))}
    </div>
  );
}
