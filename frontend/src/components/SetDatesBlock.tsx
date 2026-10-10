import { Fragment } from "react";

import { cn } from "../lib/utils";
import { useNow } from "../lib/countdown";
import { useSets } from "../data/hooks";
import { setDates, type ScribeDate, type SetDates } from "../data/scribeDates";

export function SetDatesBlock({
  setCode, variant, className,
}: { setCode: string; variant: "header" | "list"; className?: string }) {
  const now = useNow(60_000);
  const dates = useSetDates(setCode, now);
  if (!dates) {
    return null;
  }

  const daysLeft = Math.ceil((dates.setEnd - now) / DAY_MS);
  if (variant === "header") {
    return <HeaderBlock setCode={setCode} daysLeft={daysLeft} dates={dates.dates} now={now} className={className} />;
  }
  return <List daysLeft={daysLeft} setEnd={dates.setEnd} dates={dates.dates} now={now} className={className} />;
}

export function useSetDates(setCode: string, now: number = Date.now()): SetDates | null {
  const { data: sets } = useSets();
  const set = sets?.find((s) => s.code === setCode);
  return set && sets ? setDates(set, sets, now) : null;
}

const DAY_MS = 86_400_000;
const HEADER_ROWS = 5;
const HOUR_MS = 3_600_000;
const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function List({
  daysLeft, setEnd, dates, now, className,
}: { daysLeft: number; setEnd: number; dates: ScribeDate[]; now: number; className?: string }) {
  return (
    <div className={cn("flex flex-col", className)}>
      <div className="flex items-baseline gap-3 px-4 py-4 border-b border-border">
        <span className="font-display tabular-nums text-[34px] leading-none text-green">{daysLeft}</span>
        <span className="font-display text-[14px] tracking-[0.18em] text-muted">DAYS LEFT</span>
        <span className="ml-auto font-display text-[13px] tracking-[0.16em] text-muted">
          ENDS {fmtDay(setEnd)}
        </span>
      </div>
      {dates.map((d) => (
        <div
          key={`${d.label}-${d.start}`}
          className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-4 px-4 py-[9px] border-b border-border"
        >
          <span className={cn("text-[14px] truncate", d.live ? "text-text" : "text-muted")}>{d.label}</span>
          <span className="font-display tabular-nums text-[13px] tracking-[0.12em] text-muted whitespace-nowrap">
            {fmtDay(d.start)} – {fmtDay(d.end)}
          </span>
          <Countdown date={d} now={now} className="w-[72px] text-right" />
        </div>
      ))}
    </div>
  );
}

function HeaderBlock({
  setCode, daysLeft, dates, now, className,
}: { setCode: string; daysLeft: number; dates: ScribeDate[]; now: number; className?: string }) {
  const nextDates = headerDates(dates);
  return (
    <div className={cn("self-stretch shrink-0 flex gap-[1px] bg-border border border-border", className)}>
      <div className="bg-surface px-4 flex flex-col items-center justify-center text-center">
        <div className="font-display tabular-nums text-[34px] leading-none text-green">{daysLeft}</div>
        <div className="font-display text-[14px] tracking-[0.16em] leading-none text-text mt-1">DAYS</div>
        <div className="font-display text-[14px] tracking-[0.16em] leading-none text-text mt-[2px]">LEFT</div>
      </div>
      <div className={cn("bg-surface px-3 py-1 grid grid-cols-[auto_auto]",
                         "content-center items-baseline gap-x-5 leading-[18px]")}>
        {nextDates.map((d) => (
          <Fragment key={`${d.label}-${d.start}`}>
            <span className={cn("text-[12.5px] whitespace-nowrap", d.live ? "text-text" : "text-muted")}>
              {headerLabel(d.label, setCode)}
            </span>
            <Countdown date={d} now={now} className="text-right" />
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function Countdown({ date, now, className }: { date: ScribeDate; now: number; className?: string }) {
  const text = date.live ? `${shortSpan(date.end - now)} left` : `in ${shortSpan(date.start - now)}`;
  return (
    <span
      className={cn("tabular-nums text-[12px] whitespace-nowrap", date.live ? "text-green" : "text-muted", className)}
    >
      {text}
    </span>
  );
}

function headerDates(dates: ScribeDate[]): ScribeDate[] {
  const playIns = dates.filter((d) => d.playIn);
  const others = dates.filter((d) => !d.playIn).slice(0, Math.max(0, HEADER_ROWS - playIns.length));
  return [...others, ...playIns].slice(0, HEADER_ROWS).sort((a, b) => a.start - b.start);
}

function headerLabel(label: string, setCode: string): string {
  const ownSetSuffix = `: ${setCode}`;
  if (label.startsWith(`Arena Direct${ownSetSuffix} `)) {
    return "Arena Direct";
  }
  return label.endsWith(ownSetSuffix) ? label.slice(0, -ownSetSuffix.length) : label;
}

function shortSpan(ms: number): string {
  if (ms < DAY_MS) {
    return `${Math.max(1, Math.ceil(ms / HOUR_MS))}h`;
  }
  return `${Math.ceil(ms / DAY_MS)}d`;
}

function fmtDay(ms: number): string {
  const date = new Date(ms);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}`;
}
