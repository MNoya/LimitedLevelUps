import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";

export function ProPlaySkeleton({ layout, header }: { layout: "sheet" | "replay"; header?: ReactNode }) {
  const isMobile = useIsMobile(1024);
  if (layout === "sheet") {
    return isMobile ? (
      <main className="flex-1" />
    ) : (
      <main className="flex-1 min-h-0 grid grid-cols-[510px_1fr] overflow-hidden">
        <section className="h-full border-r border-border bg-surface" />
        <section />
      </main>
    );
  }
  return (
    <main className="flex-1 lg:min-h-0 lg:overflow-y-auto themed-scrollbar lg:[scrollbar-gutter:stable]">
      <div
        className={cn(
          "bg-surface border-b border-border flex items-center justify-center",
          isMobile ? "min-h-[100px] px-3 py-3" : "min-h-[135px] py-6",
        )}
      >
        {header}
      </div>
      <div className="h-[33px] border-b border-border" />
      <div className={cn("max-w-[1400px] mx-auto", isMobile ? "px-3 pt-3" : "px-7 pt-6")}>
        <ReplayTilesSkeleton compact={isMobile} />
      </div>
    </main>
  );
}

function ReplayTilesSkeleton({ compact }: { compact: boolean }) {
  const nameWidths = [62, 48, 70, 55, 66, 44, 58, 74];
  return (
    <div>
      <span className={cn("block w-40 bg-surface2", compact ? "h-[27px] mb-2" : "h-[28px] mb-3")} />
      <div className={cn("grid", compact ? "grid-cols-1 gap-1.5" : "grid-cols-4 gap-3")}>
        {Array.from({ length: compact ? 10 : 16 }, (_, index) => (
          <div
            key={index}
            className={cn(
              "flex items-center border border-border bg-surface",
              compact ? "gap-2.5 min-h-[48px]" : "gap-3 min-h-[64px]",
            )}
          >
            <span className={cn("self-stretch shrink-0 bg-surface2", compact ? "w-12" : "w-16")} />
            <span className="h-3 bg-surface2" style={{ width: `${nameWidths[index % nameWidths.length]}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}
