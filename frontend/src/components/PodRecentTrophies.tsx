import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Pips } from "./ManaPips";
import { SectionLabel } from "./SectionLabel";
import { SurfaceCard } from "./SurfaceCard";
import { Trophy } from "./Brand";
import { ChevronDown, ExternalLink } from "./Icons";
import { cn } from "../lib/utils";
import { usePodEvents } from "../data/hooks";
import { mainColors, relativeTime, stripDiscriminator } from "../data/utils";
import type { PodEventSummary, SetSummary } from "../types/leaderboard";

const RECENT_PAGE = 8;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function podShortName(e: PodEventSummary): string {
  const raw = e.eventDate.includes("T") ? e.eventDate : `${e.eventDate}T12:00:00`;
  const date = new Date(raw);
  const datePart = Number.isNaN(date.getTime()) ? "" : `${MONTHS[date.getMonth()]} ${date.getDate()}`;
  const slot = /early/i.test(e.name) ? "Early" : /late/i.test(e.name) ? "Late" : "";
  return [datePart, slot].filter(Boolean).join(" ").toUpperCase();
}

function eventSeason(e: PodEventSummary, sets: SetSummary[] | undefined): string | undefined {
  const date = e.eventDate.slice(0, 10);
  for (const set of sets ?? []) {
    if (date >= set.startDate && date <= set.endDate) {
      return set.code;
    }
  }
  return undefined;
}

export function PodRecentTrophies({
  setCode,
  season,
  sets,
}: {
  setCode: string;
  season: string | null;
  sets: SetSummary[] | undefined;
}) {
  const { data } = usePodEvents(setCode);
  const [limit, setLimit] = useState(RECENT_PAGE);

  const finalized = useMemo(
    () =>
      (data ?? []).filter(
        (e) => e.kind !== "mock" && e.isFinalized && (season == null || eventSeason(e, sets) === season),
      ),
    [data, season, sets],
  );
  const champions = useMemo(
    () =>
      finalized
        .filter((e) => e.championDisplayName)
        .sort((a, b) => (a.eventTime < b.eventTime ? 1 : a.eventTime > b.eventTime ? -1 : 0)),
    [finalized],
  );
  const players = useMemo(() => finalized.reduce((sum, e) => sum + (e.participantCount ?? 0), 0), [finalized]);
  const shown = champions.slice(0, limit);

  return (
    <div className="flex flex-col gap-4">
      <SurfaceCard>
        <div className="mb-1 flex items-center gap-1.5">
          <Trophy size={16} color="#ffc63a" />
          <SectionLabel size={16} className="text-subtle">RECENT TROPHIES</SectionLabel>
        </div>
        {!data ? (
          <div className="font-mono text-[11px] text-muted py-2">LOADING…</div>
        ) : champions.length === 0 ? (
          <div className="font-mono text-[11px] text-muted py-2">NO TROPHIES YET</div>
        ) : (
          <>
            {shown.map((e, i) => {
              const to = e.championPlayerSlug
                ? `/pods/${e.slug}/${e.championPlayerSlug}`
                : `/pods/${e.slug}?player=${encodeURIComponent(e.championDisplayName ?? "")}`;
              return (
                <Link
                  key={e.eventId}
                  to={to}
                  className={cn(
                    "group grid grid-cols-[28px_minmax(0,1fr)_86px_50px] gap-2 items-center py-[7px] -mx-1 px-1 no-underline text-inherit transition-colors hover:bg-surface2",
                    i ? "border-t border-border" : "",
                  )}
                >
                  <Pips colors={mainColors(e.championDeckColors)} size={10} />
                  <span className="font-display text-[15px] leading-none tracking-[0.04em] truncate">
                    {stripDiscriminator(e.championDisplayName ?? "").toUpperCase()}
                  </span>
                  <span className="font-mono text-[11px] text-subtle whitespace-nowrap text-left">
                    {podShortName(e)}
                  </span>
                  <span className="flex items-center justify-end gap-1 font-mono text-[11px] text-muted tabular-nums whitespace-nowrap">
                    {relativeTime(e.eventTime)}
                    <ExternalLink size={12} className="text-dim transition-colors group-hover:text-text" aria-hidden="true" />
                  </span>
                </Link>
              );
            })}
            {champions.length > limit && (
              <button
                type="button"
                onClick={() => setLimit((n) => n + RECENT_PAGE)}
                className="-mb-3.5 mt-0.5 flex w-full items-center justify-center gap-1.5 border-t border-border bg-transparent py-2 font-display text-[12px] tracking-[0.18em] text-muted transition-colors hover:text-text"
              >
                SHOW MORE
                <ChevronDown size={15} strokeWidth={2.5} />
              </button>
            )}
          </>
        )}
      </SurfaceCard>
      {finalized.length > 0 && (
        <div className="font-mono text-[11px] text-muted -mt-2 flex justify-between px-8">
          <span>{players} PLAYERS</span>
          <span>{finalized.length} EVENTS</span>
        </div>
      )}
    </div>
  );
}
