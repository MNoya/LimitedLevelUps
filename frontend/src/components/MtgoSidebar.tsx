import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { BsPaletteFill, ChevronDown } from "./Icons";
import { Trophy } from "./Brand";
import { Pips } from "./ManaPips";
import { SectionLabel } from "./SectionLabel";
import { SurfaceCard } from "./SurfaceCard";
import { TrophyCount } from "./TrophyCount";
import { Record } from "./Record";
import { cn } from "../lib/utils";
import { colorsOf, isSoup, mainColors, playerPath, relativeTime } from "../data/utils";
import { colorsDisplayName, MULTI } from "../data/filters";
import type { SelfReportedEvent, TrophyLeaderboardRow } from "../types/leaderboard";

// Insights sidebar for MTGO flashback boards, derived entirely from the self-reported results each
// row already carries — these sets have no scored 17lands data the normal LeaderboardSidebar reads.
// Top Colors counts trophies only; the recent feed shows every logged deck, trophies marked.

interface DeckEntry extends SelfReportedEvent {
  slug: string;
  displayName: string;
}

export function MtgoSidebar({
  rows,
  setCode,
  maxColors = 5,
  maxRecent = 10,
}: {
  rows: TrophyLeaderboardRow[] | undefined;
  setCode: string;
  maxColors?: number;
  maxRecent?: number;
}) {
  const decks = useMemo<DeckEntry[]>(
    () => (rows ?? []).flatMap((r) => r.decks.map((d) => ({ ...d, slug: r.slug, displayName: r.displayName }))),
    [rows],
  );
  const topColors = useMemo(() => aggregateColors(decks.filter((d) => d.isTrophy)), [decks]);
  const recent = useMemo(
    () => [...decks].sort((a, b) => b.reportedAt.localeCompare(a.reportedAt)),
    [decks],
  );
  const trophyTotal = useMemo(() => decks.filter((d) => d.isTrophy).length, [decks]);

  return (
    <aside className="flex flex-col gap-4">
      <SurfaceCard>
        <SectionLabel size={16} className="mb-1 text-subtle">TOP COLORS</SectionLabel>
        <TopColorsRows topColors={topColors} maxColors={maxColors} loading={!rows} />
      </SurfaceCard>

      <SurfaceCard>
        <div className="mb-1 flex items-center gap-1.5">
          <Trophy size={16} color="#ffc63a" />
          <SectionLabel size={16} className="text-subtle">RECENT DECKS</SectionLabel>
        </div>
        <RecentTrophyRows recent={recent} setCode={setCode} maxRecent={maxRecent} loading={!rows} />
      </SurfaceCard>

      {rows && (
        <div className="font-mono text-[11px] text-muted -mt-2 flex justify-between px-12">
          <span>{rows.length} PLAYERS</span>
          <span>{trophyTotal} TROPHIES</span>
        </div>
      )}
    </aside>
  );
}

interface ColorTally {
  colors: string;
  trophies: number;
}

function aggregateColors(decks: DeckEntry[]): ColorTally[] {
  const counts = new Map<string, number>();
  for (const deck of decks) {
    const combo = isSoup(deck.colors, false) ? MULTI : colorsOf(deck.colors);
    if (!combo) {
      continue;
    }
    counts.set(combo, (counts.get(combo) ?? 0) + 1);
  }
  const tallies = [...counts.entries()].map(([colors, trophies]) => ({ colors, trophies }));
  tallies.sort((a, b) => b.trophies - a.trophies || a.colors.localeCompare(b.colors));
  return tallies;
}

function TopColorsRows({
  topColors,
  maxColors,
  loading,
}: {
  topColors: ColorTally[];
  maxColors: number;
  loading: boolean;
}) {
  const [limit, setLimit] = useState(maxColors);
  if (loading) {
    return <div className="font-mono text-[11px] text-muted py-2">LOADING…</div>;
  }
  if (topColors.length === 0) {
    return <div className="font-mono text-[11px] text-muted py-2">NO TROPHIES YET</div>;
  }
  const canShowMore = topColors.length > limit;
  return (
    <>
      {topColors.slice(0, limit).map((row, i) => (
        <div
          key={row.colors}
          className={cn(
            "grid grid-cols-[24px_28px_1fr_auto] gap-2 items-center py-2",
            i > 0 && "border-t border-border",
          )}
        >
          <span className="font-num text-[11px] text-muted">{i + 1}</span>
          <span className="flex justify-center">
            {row.colors === MULTI ? (
              <BsPaletteFill size={18} className="shrink-0 block -my-1" aria-hidden="true" />
            ) : (
              <Pips colors={row.colors} size={12} />
            )}
          </span>
          <span className="font-display text-[14px] tracking-[0.05em] pl-1.5">
            {colorsDisplayName(row.colors)}
          </span>
          <TrophyCount count={row.trophies} size="compact" className="text-muted" />
        </div>
      ))}
      {canShowMore && <ShowMore onClick={() => setLimit((n) => n + maxColors)} />}
    </>
  );
}

function RecentTrophyRows({
  recent,
  setCode,
  maxRecent,
  loading,
}: {
  recent: DeckEntry[];
  setCode: string;
  maxRecent: number;
  loading: boolean;
}) {
  const [limit, setLimit] = useState(maxRecent);
  if (loading) {
    return <div className="font-mono text-[11px] text-muted py-2">LOADING…</div>;
  }
  if (recent.length === 0) {
    return <div className="font-mono text-[11px] text-muted py-2">NO DECKS YET</div>;
  }
  const canShowMore = recent.length > limit;
  return (
    <>
      {recent.slice(0, limit).map((t, i) => {
        const [wins, losses] = t.record.split("-").map((n) => Number(n) || 0);
        const soup = isSoup(t.colors, false);
        return (
          <Link
            key={`${t.slug}-${t.sourceMessageId}`}
            to={playerPath(t.slug, setCode)}
            className={cn(
              "group grid grid-cols-[auto_1fr_28px_auto] gap-2 items-center py-[7px] -mx-1 px-1 no-underline text-inherit transition-colors hover:bg-surface2",
              i > 0 && "border-t border-border",
            )}
          >
            {soup ? (
              <span className="inline-flex items-center gap-px shrink-0">
                <Pips colors={mainColors(t.colors).slice(0, 3)} size={10} />
                <BsPaletteFill size={12} aria-hidden="true" />
              </span>
            ) : (
              <Pips colors={t.colors} size={10} />
            )}
            <span className="font-display text-[15px] leading-none tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis min-w-0">
              {t.displayName.toUpperCase()}
            </span>
            <Record wins={wins} losses={losses} mono className="font-num text-[13px] text-subtle text-right" />
            <span className="flex items-center gap-1.5 justify-end whitespace-nowrap">
              {t.isTrophy && <Trophy size={11} color="#ffc63a" />}
              <span className="font-mono text-[11px] text-text">{t.platform}</span>
              <span className="font-mono text-[11px] text-dim tabular-nums transition-colors group-hover:text-text">
                {relativeTime(t.reportedAt)}
              </span>
            </span>
          </Link>
        );
      })}
      {canShowMore && <ShowMore onClick={() => setLimit((n) => n + maxRecent)} />}
    </>
  );
}

function ShowMore({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="-mb-3.5 mt-0.5 flex w-full items-center justify-center gap-1.5 border-t border-border bg-transparent py-2 font-display text-[12px] tracking-[0.18em] text-muted transition-colors hover:text-text"
    >
      SHOW MORE
      <ChevronDown size={15} strokeWidth={2.5} />
    </button>
  );
}
