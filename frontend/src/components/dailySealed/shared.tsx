import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, ChevronLeft, ChevronRight, CircleAlert, LogIn } from "lucide-react";

import { cn } from "../../lib/utils";
import type { PoolEntry, Zone } from "../../data/dailySealed";
import type { BuilderView } from "../../pages/DailySealedPage";

export const DayNav = ({
  view,
  withToday = true,
  dateClassName,
}: {
  view: BuilderView;
  withToday?: boolean;
  dateClassName?: string;
}) => (
  <DayNavBar
    day={view.pool.day}
    older={view.neighbors.older?.day}
    newer={view.neighbors.newer?.day}
    showToday={withToday && !view.isToday}
    dateClassName={dateClassName}
  />
);

export const DayNavBar = ({
  day,
  older,
  newer,
  showToday = false,
  dateClassName,
}: {
  day: string;
  older?: string;
  newer?: string;
  showToday?: boolean;
  dateClassName?: string;
}) => (
  <span className="flex items-center gap-2 whitespace-nowrap">
    <NavArrow to={older} label="Older pool">
      <ChevronLeft size={18} />
    </NavArrow>
    <span className={cn("w-[8.6em] text-center", dateClassName)}>{formatDay(day)}</span>
    <NavArrow to={newer} label="Newer pool">
      <ChevronRight size={18} />
    </NavArrow>
    {showToday && <TodayPoolLink className="ml-2 self-center" />}
  </span>
);

export const GREEN_CTA =
  "rounded-md border border-green/60 bg-green/10 font-display text-[13px] tracking-[0.12em] text-green transition-colors hover:bg-green/20 active:bg-green/30";

export const TodayPoolLink = ({ className }: { className?: string }) => (
  <Link
    to="/daily-sealed"
    className={cn("flex h-8 items-center justify-center gap-1.5 whitespace-nowrap px-3", GREEN_CTA, className)}
  >
    TODAY'S POOL
    <ArrowRight size={14} />
  </Link>
);

const NAV_ARROW =
  "flex h-8 w-8 shrink-0 items-center justify-center self-center rounded-md border border-border bg-surface2";

const NavArrow = ({ to, label, children }: { to: string | undefined; label: string; children: ReactNode }) =>
  to ? (
    <Link
      to={`/daily-sealed/${to}`}
      aria-label={label}
      className={cn(NAV_ARROW, "text-subtle transition-colors hover:border-white/40 hover:bg-white/10 hover:text-text")}
    >
      {children}
    </Link>
  ) : (
    <span className={cn(NAV_ARROW, "text-subtle opacity-30")}>{children}</span>
  );

export const formatDay = (day: string) => {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date))
    .toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", timeZone: "UTC" })
    .replace(",", "")
    .toUpperCase();
};

export const SubmitButton = ({
  view,
  wide = false,
  statusOnly = false,
}: {
  view: BuilderView;
  wide?: boolean;
  statusOnly?: boolean;
}) => {
  const { submitState } = view;
  const label = statusOnly
    ? "SUBMITTED"
    : !submitState.signedIn
    ? "SIGN IN TO SUBMIT"
    : submitState.submitted
      ? submitState.unchanged
        ? "SUBMITTED"
        : "UPDATE"
      : "SUBMIT";
  const enabled =
    !statusOnly && !submitState.pending && (!submitState.signedIn || (submitState.ready && !submitState.unchanged));
  return (
    <button
      type="button"
      onClick={submitState.run}
      disabled={!enabled}
      className={cn(
        "flex h-10 items-center justify-center gap-2 rounded px-3 font-display text-[14px] tracking-[0.14em]",
        wide && "flex-1",
        enabled ? "bg-green text-bg" : "bg-surface2 text-muted",
      )}
    >
      {submitState.signedIn ? <Check size={16} strokeWidth={2.5} /> : <LogIn size={16} />}
      <ReservedLabel label={label} widest={submitState.signedIn ? "SUBMITTED" : label} />
    </button>
  );
};

export const ReservedLabel = ({ label, widest }: { label: string; widest: string }) => (
  <span className="grid">
    <span className="invisible col-start-1 row-start-1">{widest}</span>
    <span className="col-start-1 row-start-1 text-center">{label}</span>
  </span>
);

export const PreviewMove = ({ view, entry }: { view: BuilderView; entry: PoolEntry }) => {
  const zone = view.builder.zoneOf(entry.index);
  const move = (target: Zone) => {
    view.builder.move([entry.index], target);
    view.closePreview();
  };
  return (
    <>
      {zone !== "deck" && <PreviewButton onClick={() => move("deck")}>Add to Deck</PreviewButton>}
      {zone !== "side" && <PreviewButton onClick={() => move("side")}>Move to Sideboard</PreviewButton>}
      {zone === "side" && <PreviewButton onClick={() => move("hidden")}>Hide</PreviewButton>}
    </>
  );
};

export const PreviewButton = ({ onClick, children }: { onClick: () => void; children: ReactNode }) => (
  <button
    type="button"
    onClick={onClick}
    className="h-10 rounded border border-border2 bg-surface px-3 text-[13px] text-subtle hover:text-text"
  >
    {children}
  </button>
);

export interface Notice {
  text: string;
  tone: "ok" | "error";
}

export const Toast = ({ notice, phone }: { notice: Notice; phone: boolean }) => {
  const ok = notice.tone === "ok";
  return (
    <div
      role="status"
      className={cn(
        "pointer-events-none fixed left-1/2 z-[95] flex -translate-x-1/2 items-center gap-2 rounded-md border bg-surface2",
        "px-4 py-2.5 text-[14px] font-medium text-text shadow-[0_8px_24px_rgba(0,0,0,0.5)]",
        phone ? "bottom-[72px]" : "top-[96px]",
        ok ? "border-green/70" : "border-red/70",
      )}
    >
      {ok ? (
        <Check size={16} strokeWidth={3} className="shrink-0 text-green" />
      ) : (
        <CircleAlert size={16} className="shrink-0 text-red" />
      )}
      {notice.text}
    </div>
  );
};
