import { useMemo, useState } from "react";

import { Pips } from "./ManaPips";
import { Trophy } from "./Brand";
import { BsPaletteFill, ChevronDown } from "./Icons";
import { SectionLabel } from "./SectionLabel";
import { SortHeaderButton } from "./SortHeader";
import { SurfaceCard } from "./SurfaceCard";
import { cn } from "../lib/utils";
import { colorsDisplayName } from "../data/filters";
import { winRateColor } from "../data/winRate";
import { usePodArchetypes } from "../data/hooks";
import { OTHER_KEY, aggregateArchetypes, type Archetype } from "../data/podArchetypes";

const pct = (n: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);

const GRID = "grid grid-cols-[22px_26px_minmax(0,1fr)_78px_62px] gap-1.5 items-center";

const ARCH_PAGE = 5;

type ArchSortKey = "play" | "win";
type ArchSortDir = "asc" | "desc";

export function ArchetypePanel({ setCode, season }: { setCode: string; season: string | null }) {
  const { data, isPending } = usePodArchetypes(setCode);
  const [sortKey, setSortKey] = useState<ArchSortKey>("play");
  const [sortDir, setSortDir] = useState<ArchSortDir>("desc");
  const [limit, setLimit] = useState(ARCH_PAGE);

  const rows = useMemo(() => {
    const scoped = season == null ? (data ?? []) : (data ?? []).filter((r) => r.season === season);
    const value = (a: Archetype) => (sortKey === "play" ? a.playRate : (a.winRate ?? -1));
    return aggregateArchetypes(scoped).sort((a, b) => {
      const diff = value(a) - value(b);
      return sortDir === "desc" ? -diff : diff;
    });
  }, [data, season, sortKey, sortDir]);
  const shown = rows.slice(0, limit);

  const onSort = (key: ArchSortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  return (
    <SurfaceCard>
      <div className={cn(GRID, "mb-2 items-center font-display text-[11px] tracking-[0.1em] text-muted")}>
        <div className="col-span-3 flex items-center gap-1.5">
          <Trophy size={16} color="#ffc63a" />
          <SectionLabel size={16} className="text-subtle">TOP COLORS</SectionLabel>
        </div>
        <SortHeaderButton label="PLAY RATE" active={sortKey === "play"} dir={sortDir} onClick={() => onSort("play")} />
        <SortHeaderButton label="WIN RATE" active={sortKey === "win"} dir={sortDir} onClick={() => onSort("win")} />
      </div>
      {isPending ? (
        <div className="font-mono text-[11px] text-muted py-2">LOADING…</div>
      ) : rows.length === 0 ? (
        <div className="font-mono text-[11px] text-muted py-2">NO DECK COLORS RECORDED YET</div>
      ) : (
        <>
          {shown.map((a, i) => (
            <div key={a.key} className={cn(GRID, "py-2", i ? "border-t border-border" : "")}>
              <span className="font-num text-[13px] text-muted pl-1 leading-none">{i + 1}</span>
              <span className="flex justify-center">
                {a.key === OTHER_KEY ? (
                  <BsPaletteFill size={18} className="shrink-0 block -my-1" aria-hidden="true" />
                ) : (
                  <Pips colors={a.colors} size={12} />
                )}
              </span>
              <span className="font-display text-[14px] tracking-[0.05em] pl-1.5 truncate">
                {a.key === OTHER_KEY ? "Other" : colorsDisplayName(a.colors)}
              </span>
              <span className="font-num text-[14px] tabular-nums text-right text-text">
                {pct(a.playRate)}
                <span className="ml-1 text-[11px] text-subtle">({a.decks})</span>
              </span>
              <span
                className="font-num text-[14px] tabular-nums text-right"
                style={{ color: winRateColor(a.winRate) }}
              >
                {pct(a.winRate)}
              </span>
            </div>
          ))}
          {rows.length > limit && (
            <button
              type="button"
              onClick={() => setLimit((n) => n + ARCH_PAGE)}
              className="-mb-3.5 mt-0.5 flex w-full items-center justify-center gap-1.5 border-t border-border bg-transparent py-2 font-display text-[12px] tracking-[0.18em] text-muted transition-colors hover:text-text"
            >
              SHOW MORE
              <ChevronDown size={15} strokeWidth={2.5} />
            </button>
          )}
        </>
      )}
    </SurfaceCard>
  );
}
