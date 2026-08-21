import { cn } from "../../lib/utils";
import { useTrackerTotals } from "../../data/trackerDrafts";

export function TrackerStatsBlock({
  slug, setCode, accountId = null, className,
}: { slug: string | undefined; setCode: string; accountId?: number | null; className?: string }) {
  const totals = useTrackerTotals(slug, setCode, accountId);
  if (!totals.drafts) {
    return null;
  }

  const cells = [
    { label: "RARES", value: String(totals.rares) },
    { label: "AVG RARES", value: totals.avgRares.toFixed(1) },
    { label: "MYTHICS", value: totals.avgMythics.toFixed(1) },
    { label: "GEMS", value: compactThousands(totals.gems) },
    { label: "GEMS USED", value: compactThousands(totals.spent) },
    { label: "PACKS", value: String(totals.packs) },
  ];

  return (
    <div
      className={cn("self-stretch shrink-0 grid auto-rows-fr gap-[1px] bg-border border border-border", className)}
      style={{ gridTemplateColumns: "repeat(3, auto)" }}
    >
      {cells.map((c) => (
        <div
          key={c.label}
          className="bg-surface px-[6px] py-[7px] flex flex-col items-center justify-center text-center"
        >
          <div className="font-display text-[10.5px] tracking-[0.16em] leading-none text-muted whitespace-nowrap">
            {c.label}
          </div>
          <div className="font-display tabular-nums text-[20px] leading-none mt-1 whitespace-nowrap">
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Gem totals run to five digits, which is wider than the cell reads well at */
function compactThousands(value: number): string {
  if (value < 1000) {
    return String(value);
  }
  const thousands = Math.round(value / 100) / 10;
  return `${thousands % 1 === 0 ? thousands : thousands.toFixed(1)}k`;
}
