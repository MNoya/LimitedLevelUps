import { useMemo, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ChevronDown } from "lucide-react";

import { PodPage } from "./PodPage";

import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { SectionLabel } from "../components/SectionLabel";
import { SetSwitcherDesktop, SetSwitcherMobile } from "../components/SetSwitcher";
import { AAvatar, setGlyphCode, SetGlyph, Trophy } from "../components/Brand";
import { ArrowRight, GiRoundTable, LuScrollText, TbCards } from "../components/Icons";
import { DiscordIcon } from "../components/BrandIcons";
import { CtaPill } from "../components/CtaPill";
import { ChamferedButton } from "../components/ChamferedButton";
import { Tooltip } from "../components/Tooltip";
import { BREAKDOWN_CAPTION, DeckScreenshotModal } from "../components/pod/DeckScreenshotModal";
import { highlightEventLabel, PodEventTitle } from "../components/pod/EventLabel";
import { Pips } from "../components/ManaPips";
import { Record } from "../components/Record";
import {
  DEFAULT_SORT_NOSCORE,
  LeaderboardTable,
  sortRows,
  type LeaderboardTableRow,
  type SortKey,
  type SortState,
} from "../components/LeaderboardTable";
import { formatCountdown, useNow } from "../lib/countdown";
import { useIsMobile } from "../lib/use-is-mobile";
import { cn } from "../lib/utils";
import { cleanPodEventName, fmtRange, playerPath, podDiscordName, stripDiscriminator, weekOfSet } from "../data/utils";
import { ACTIVE_SET_CODE } from "../data/constants";
import { SITE_LINKS } from "../data/site";
import {
  usePodDraftArtifact,
  usePodEventMatches,
  usePodEventParticipants,
  usePodEvents,
  usePodLeaderboard,
  usePodSetCodes,
  useSets,
} from "../data/hooks";
import { resolveDeck } from "../data/draft-artifact";
import { usePodDecklistAccess } from "../data/podDecklistAccess";
import type {
  PodEventParticipantRow,
  PodEventSummary,
  PodLeaderboardRow,
  SetSummary,
} from "../types/leaderboard";

const MONTHS_CAL = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function parseMonthDay(iso: string): { month: string; day: number } {
  const m = parseInt(iso.slice(5, 7), 10);
  const d = parseInt(iso.slice(8, 10), 10);
  return { month: MONTHS_CAL[m - 1] ?? "", day: d };
}

function formatLocalTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(d);
}

function CountdownChip({ iso }: { iso: string }) {
  const targetMs = useMemo(() => new Date(iso).getTime(), [iso]);
  const now = useNow(1000);
  if (!Number.isFinite(targetMs)) return null;
  const remaining = targetMs - now;
  const label = remaining <= 0 ? "00:00:00" : formatCountdown(targetMs, now);
  return (
    <span
      className="font-mono text-text tabular-nums shrink-0 border border-border2 bg-surface2/40 px-2 py-1"
      style={{ fontSize: 13, lineHeight: 1, letterSpacing: "0.02em" }}
    >
      {label}
    </span>
  );
}

function toLeaderboardRow(r: PodLeaderboardRow): LeaderboardTableRow {
  return {
    setCode: r.setCode,
    slug: r.slug,
    displayName: r.displayName,
    avatarUrl: r.avatarUrl,
    rank: r.rank,
    trophies: r.trophies,
    events: r.events,
    wins: r.wins,
    losses: r.losses,
    lastCalculatedAt: r.lastFinishedAt ?? "",
  };
}

export function PodsRoute() {
  const { slug } = useParams<{ slug: string }>();
  const { data: podSetCodes } = usePodSetCodes();
  if (!slug) return <PodDraftsPage />;
  if (podSetCodes === undefined) {
    return (
      <div className="bg-bg text-text min-h-screen flex flex-col">
        <AppHeader subtitle="POD DRAFTS" />
      </div>
    );
  }
  const match = podSetCodes.find((p) => p.code.toLowerCase() === slug.toLowerCase());
  if (!match) return <PodPage />;
  if (slug !== match.code) return <Navigate to={`/pods/${match.code}`} replace />;
  return <PodDraftsPage setCode={match.code} />;
}

export function PodDraftsPage({ setCode }: { setCode?: string } = {}) {
  const isMobile = useIsMobile(1024);
  const navigate = useNavigate();
  const { data: allSets } = useSets();
  const { data: podSetCodes } = usePodSetCodes();

  const availableSets = useMemo<SetSummary[]>(() => {
    if (!allSets || !podSetCodes) return [];
    const byCode = new Map(allSets.map((s) => [s.code, s]));
    // Real sets first, then pod-only codes with no visible `sets` row. A label marks a cube format
    // (custom → generic glyph); a bare code is a set hidden until release and keeps its own keyrune.
    const real = allSets.filter((s) => podSetCodes.some((p) => p.code === s.code));
    const synthesized = podSetCodes
      .filter((p) => !byCode.has(p.code))
      .map<SetSummary>((p) => ({
        code: p.code,
        name: p.label ?? p.code,
        startDate: "",
        endDate: "",
        isActive: false,
        custom: p.label != null,
      }));
    return [...real, ...synthesized];
  }, [allSets, podSetCodes]);

  const homeCode = useMemo(() => {
    if (availableSets.length === 0) return ACTIVE_SET_CODE;
    const active = availableSets.find((s) => s.isActive);
    if (active) return active.code;
    if (availableSets.some((s) => s.code === ACTIVE_SET_CODE)) return ACTIVE_SET_CODE;
    const realSet = availableSets.find((s) => !s.custom);
    return (realSet ?? availableSets[0]).code;
  }, [availableSets]);

  const activeSet = setCode ?? homeCode;
  const onSelectSet = (code: string) => {
    navigate(code === homeCode ? "/pods" : `/pods/${code}`);
  };

  const { data: events } = usePodEvents(activeSet);
  const { data: leaderboard } = usePodLeaderboard(activeSet);
  const setMeta = availableSets.find((s) => s.code === activeSet);

  const [sort, setSort] = useState<SortState>(DEFAULT_SORT_NOSCORE);
  const sortedLeaderboard = useMemo(() => {
    if (!leaderboard) return undefined;
    const adapted: LeaderboardTableRow[] = leaderboard.map(toLeaderboardRow);
    return sortRows(adapted, sort);
  }, [leaderboard, sort]);
  const onSort = (key: SortKey) => {
    setSort((cur) =>
      cur.key === key
        ? { key, dir: cur.dir === "desc" ? "asc" : "desc" }
        : { key, dir: "desc" },
    );
  };

  const nowMs = useNow(60_000);
  const { played, upcoming, mock } = useMemo(() => {
    if (!events) {
      return {
        played: [] as PodEventSummary[],
        upcoming: [] as PodEventSummary[],
        mock: [] as PodEventSummary[],
      };
    }
    const p: PodEventSummary[] = [];
    const u: PodEventSummary[] = [];
    const m: PodEventSummary[] = [];
    for (const e of events) {
      if (e.kind === "mock") m.push(e);
      else if (!e.championDisplayName && new Date(e.eventTime).getTime() > nowMs) u.push(e);
      else p.push(e);
    }
    return { played: p, upcoming: u, mock: m };
  }, [events, nowMs]);

  usePodEventParticipants(played[0]?.eventId);

  return (
    <div className="bg-bg text-text min-h-screen flex flex-col animate-fadeIn">
      <AppHeader subtitle="POD DRAFTS" />

      {isMobile ? (
        <MobileSetStrip
          activeSet={activeSet}
          availableSets={availableSets}
          onSelectSet={onSelectSet}
        />
      ) : (
        <SetHero
          activeSet={activeSet}
          setMeta={setMeta}
          sets={availableSets}
          onSelectSet={onSelectSet}
        />
      )}

      <main className="flex-1 lg:px-5 lg:pb-10">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-6 lg:gap-y-8">
          <section className="order-2 lg:order-1">
            <SectionHeading
              label="STANDINGS"
              count={leaderboard ? leaderboard.length : undefined}
              unit={(leaderboard?.length ?? 0) === 1 ? "PLAYER" : "PLAYERS"}
              compact={isMobile}
              meta={
                isMobile && leaderboard && events ? (
                  <>
                    <span className="tabular-nums text-subtle">{leaderboard.length}</span>{" "}
                    {leaderboard.length === 1 ? "PLAYER" : "PLAYERS"},{" "}
                    <span className="tabular-nums text-subtle">{events.length}</span>{" "}
                    {events.length === 1 ? "EVENT" : "EVENTS"}
                  </>
                ) : undefined
              }
            />
            <LeaderboardTable
              rows={sortedLeaderboard}
              loading={leaderboard === undefined}
              variant={isMobile ? "mobile" : "desktop"}
              mode="pod"
              sort={sort}
              onSort={onSort}
              emptyMessage={`No player stats yet for ${activeSet}.`}
              playerHref={(row) => playerPath(row.slug, activeSet)}
            />
          </section>

          <section className="order-1 lg:order-2 flex flex-col gap-4">
            {events === undefined ? (
              <EventsLoadingBlock />
            ) : upcoming.length === 0 && played.length === 0 && mock.length === 0 ? (
              <div>
                <SectionHeading label="EVENTS" count={0} unit="EVENTS" />
                <EmptyHint>No pod drafts recorded yet for {activeSet}.</EmptyHint>
              </div>
            ) : (
              <>
                {isMobile ? (
                  (upcoming.length > 0 || played.length > 0) && (
                    <MobileEventsBlock played={played} upcoming={upcoming} nowMs={nowMs} />
                  )
                ) : (
                  <>
                    {upcoming.length > 0 && (
                      <EventsBlock label="UPCOMING" events={upcoming} nowMs={nowMs} />
                    )}
                    {played.length > 0 && (
                      <EventsBlock label="PAST" events={played} nowMs={nowMs} defaultOpenFirst />
                    )}
                  </>
                )}
                {!isMobile && mock.length > 0 && <MockDraftsBlock events={mock} />}
              </>
            )}
          </section>

          {isMobile && mock.length > 0 && (
            <section className="order-3">
              <MockDraftsBlock events={mock} />
            </section>
          )}
        </div>
      </main>

      <Footer className="mt-auto px-5 py-4 md:pt-5 md:pb-3 shrink-0" />
    </div>
  );
}

function SectionHeading({
  label,
  count,
  unit,
  compact,
  meta,
}: {
  label: string;
  count?: number;
  unit: string;
  compact?: boolean;
  meta?: React.ReactNode;
}) {
  if (compact) {
    return (
      <div className="flex items-baseline justify-between gap-3 py-2 pl-4 pr-3 border-b border-border">
        <span className="font-display text-text text-[14px] tracking-[0.16em] leading-none">
          {label}
        </span>
        {meta && (
          <span className="font-display text-[10px] tracking-[0.14em] leading-none text-muted">
            {meta}
          </span>
        )}
      </div>
    );
  }
  return (
    <div className="flex items-baseline justify-between py-4 pl-2 pr-5 border-b border-border">
      <span
        className="font-display text-text tracking-[0.18em] leading-none"
        style={{ fontSize: 17 }}
      >
        {label}
      </span>
      {count === undefined ? (
        <span className="inline-block h-3.5 w-24 bg-surface2 animate-pulse" />
      ) : (
        <span
          className="font-display tracking-[0.18em] leading-none flex items-baseline gap-1.5"
          style={{ fontSize: 17 }}
        >
          <span className="tabular-nums text-subtle">{count}</span>
          <span className="text-muted">{unit}</span>
        </span>
      )}
    </div>
  );
}

function EventsBlock({
  label,
  events,
  nowMs,
  defaultOpenFirst = false,
}: {
  label: string;
  events: PodEventSummary[];
  nowMs: number;
  defaultOpenFirst?: boolean;
}) {
  return (
    <div>
      <SectionHeading
        label={label}
        count={events.length}
        unit={events.length === 1 ? "EVENT" : "EVENTS"}
      />
      <div className="flex flex-col lg:gap-2">
        {events.map((e, i) => (
          <EventRow
            key={e.eventId}
            event={e}
            index={i}
            nowMs={nowMs}
            defaultOpen={defaultOpenFirst && i === 0}
          />
        ))}
      </div>
    </div>
  );
}

function MockDraftsBlock({ events }: { events: PodEventSummary[] }) {
  return (
    <div>
      <SectionHeading
        label="MOCK DRAFTS"
        count={events.length}
        unit={events.length === 1 ? "DRAFT" : "DRAFTS"}
      />
      <div className="flex flex-col lg:gap-2">
        {events.map((e, i) => (
          <MockEventRow key={e.eventId} event={e} index={i} />
        ))}
      </div>
    </div>
  );
}

function MockEventRow({ event, index }: { event: PodEventSummary; index: number }) {
  return (
    <Link
      to={`/pods/${event.slug}`}
      className="group bg-surface border-b lg:border border-border first:lg:border-t-0 min-h-[68px] flex items-stretch no-underline hover:bg-surface2/30 transition-colors animate-fadeUpIn"
      style={{ animationDelay: `${Math.min(index, 6) * 45}ms` }}
    >
      <DateRail date={event.eventDate} highlighted={false} />
      <div className="flex-1 min-w-0 py-2.5 px-3 md:px-4 flex items-center gap-3">
        <span
          className="font-display text-text min-w-0 truncate"
          style={{ fontSize: 21, letterSpacing: "0.04em", lineHeight: 1.15 }}
        >
          {highlightEventLabel(cleanPodEventName(event.name, event.setCode).toUpperCase())}
        </span>
      </div>
      <div className="flex items-center pr-3 md:pr-4 pl-2 shrink-0 self-center gap-3">
        <span className="hidden lg:inline text-muted text-[13px] font-body">{BREAKDOWN_CAPTION}</span>
        <ChamferedButton className="!pt-[11px] !pb-[3px]">
          <span className="inline-flex items-center gap-2">
            <GiRoundTable size={30} className="-my-[6px]" />
            VIEW BREAKDOWN
            <ArrowRight size={14} />
          </span>
        </ChamferedButton>
      </div>
    </Link>
  );
}

function EventRow({
  event,
  index,
  nowMs,
  defaultOpen = false,
}: {
  event: PodEventSummary;
  index: number;
  nowMs: number;
  defaultOpen?: boolean;
}) {
  const isUpcoming = !event.championDisplayName && new Date(event.eventTime).getTime() > nowMs;
  const expandable = !isUpcoming;
  const joinHref = isUpcoming ? SITE_LINKS.discord : null;
  const isJoinable = isUpcoming && joinHref !== null;
  const [open, setOpen] = useState(defaultOpen && expandable);
  const headerClass = cn(
    "group w-full min-h-[68px] flex items-stretch text-left bg-transparent border-0 no-underline transition-colors",
    expandable || isJoinable ? "cursor-pointer" : "cursor-default",
    open
      ? "bg-surface2/40"
      : expandable
      ? "hover:bg-surface2/30"
      : isJoinable
      ? "hover:bg-green/15"
      : "",
  );
  const headerContent = (
    <>
      <DateRail
        date={event.eventDate}
        highlighted={open}
        time={isUpcoming ? formatLocalTime(event.eventTime) : null}
      />
      <EventRowBody event={event} nowMs={nowMs} />
      {isJoinable ? (
        <JoinEventCTA />
      ) : (
        <EventRowMeta open={open} expandable={expandable} />
      )}
    </>
  );
  return (
    <div
      className="bg-surface border-b lg:border border-border first:lg:border-t-0 transition-colors animate-fadeUpIn"
      style={{ animationDelay: `${Math.min(index, 6) * 45}ms` }}
    >
      {isJoinable ? (
        <a
          href={joinHref ?? undefined}
          target="_blank"
          rel="noreferrer"
          className={headerClass}
        >
          {headerContent}
        </a>
      ) : expandable ? (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className={headerClass}
        >
          {headerContent}
        </button>
      ) : (
        <div className={headerClass}>{headerContent}</div>
      )}

      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
        aria-hidden={!open}
      >
        <div className="overflow-hidden">{open && <EventStandings event={event} />}</div>
      </div>
    </div>
  );
}

function JoinEventCTA() {
  return (
    <div className="flex items-center pr-3 md:pr-4 pl-2 shrink-0 self-center">
      <CtaPill size="sm" icon={<DiscordIcon size={15} />} hover="group">
        JOIN EVENT
      </CtaPill>
    </div>
  );
}

function DateRail({
  date,
  highlighted,
  time = null,
}: {
  date: string;
  highlighted: boolean;
  time?: string | null;
}) {
  const { month, day } = parseMonthDay(date);
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center border-r transition-colors",
        time ? "px-1.5 min-w-[84px] md:min-w-[88px]" : "px-3 min-w-[72px] md:min-w-[78px]",
        highlighted
          ? "bg-surface2 border-border2"
          : "bg-surface2/40 border-border group-hover:bg-surface2/70",
      )}
    >
      {time ? (
        <>
          <div className="flex items-baseline gap-2">
            <span
              className="font-display text-muted leading-none tracking-[0.04em]"
              style={{ fontSize: 18 }}
            >
              {month}
            </span>
            <span
              className="font-display text-text leading-none tabular-nums"
              style={{ fontSize: 22 }}
            >
              {String(day).padStart(2, "0")}
            </span>
          </div>
          <span
            className="font-display text-text leading-none tabular-nums tracking-[0.04em] mt-1"
            style={{ fontSize: 18 }}
          >
            {time}
          </span>
        </>
      ) : (
        <>
          <span
            className="font-display text-muted leading-none tracking-[0.04em]"
            style={{ fontSize: 20 }}
          >
            {month}
          </span>
          <span
            className="font-display text-text leading-none tabular-nums mt-0.5"
            style={{ fontSize: 22 }}
          >
            {String(day).padStart(2, "0")}
          </span>
        </>
      )}
    </div>
  );
}

function EventRowBody({ event, nowMs }: { event: PodEventSummary; nowMs: number }) {
  const hasChamp = !!event.championDisplayName;
  const startMs = new Date(event.eventTime).getTime();
  const inProgress = !event.isFinalized && startMs <= nowMs;
  const isUpcoming = !event.isFinalized && startMs > nowMs;
  const { data: matches } = usePodEventMatches(inProgress ? event.eventId : undefined);
  const currentRound = useMemo(() => {
    if (!matches || matches.length === 0) return null;
    let earliestUnreported = null;
    let latest = 1;
    for (const m of matches) {
      if (m.round > latest) latest = m.round;
      if (m.reportedAt == null && (earliestUnreported == null || m.round < earliestUnreported)) {
        earliestUnreported = m.round;
      }
    }
    const round = earliestUnreported ?? latest;
    return Math.min(round, event.totalRounds);
  }, [matches, event.totalRounds]);
  return (
    <div
      className={cn(
        "flex-1 min-w-0 py-2.5 px-3 md:px-4",
        isUpcoming
          ? "flex flex-col items-start gap-1.5 lg:flex-row lg:items-center lg:gap-4"
          : "flex items-center gap-4",
      )}
    >
      <span
        className={cn(
          "font-display text-text min-w-0 line-clamp-2 lg:line-clamp-none lg:truncate",
          isUpcoming ? "lg:flex-none" : "flex-1 lg:flex-none lg:w-2/5",
        )}
        style={{ fontSize: 21, letterSpacing: "0.04em", lineHeight: 1.15 }}
      >
        <PodEventTitle event={event} />
      </span>
      {isUpcoming && <CountdownChip iso={event.eventTime} />}
      {hasChamp && event.championDisplayName && (
        <div className="flex flex-col items-center gap-1 min-w-0 max-w-[50%] lg:flex-row lg:items-center lg:gap-2.5 lg:max-w-none lg:shrink-0 lg:w-[260px]">
          <div className="flex items-center gap-1 min-w-0 max-w-full lg:contents">
            <Trophy size={17} color="#ffc63a" />
            <span
              className="font-display text-text tracking-[0.04em] truncate max-w-full"
              style={{ fontSize: 18, lineHeight: 1 }}
            >
              {stripDiscriminator(event.championDisplayName).toUpperCase()}
            </span>
          </div>
          {event.championDeckColors && (
            <Pips colors={event.championDeckColors} size={15} />
          )}
        </div>
      )}
      {inProgress && (
        <div
          className="flex items-center gap-2.5 shrink-0 font-display tracking-[0.18em]"
          style={{ fontSize: 13 }}
        >
          {currentRound != null && <span className="text-text">ROUND {currentRound}</span>}
          <span className="text-muted">IN PROGRESS</span>
        </div>
      )}
      <div className="hidden lg:block flex-1" />
    </div>
  );
}

function EventRowMeta({ open, expandable }: { open: boolean; expandable: boolean }) {
  return (
    <div className="flex items-center pr-3 md:pr-4 pl-2 shrink-0 self-center">
      {expandable && (
        <ChevronDown
          size={16}
          className={cn(
            "text-muted transition-all duration-200 group-hover:text-text",
            open && "rotate-180 text-text",
          )}
        />
      )}
    </div>
  );
}

const STANDING_COLS_CLASS =
  "[grid-template-columns:28px_1fr_60px_50px_38px] " +
  "lg:[grid-template-columns:44px_1fr_80px_70px_150px]";

const STANDINGS_LIMIT = 4;

function EventStandings({ event }: { event: PodEventSummary }) {
  const { data: rows, isLoading } = usePodEventParticipants(event.eventId);
  const [deckTarget, setDeckTarget] = useState<PodEventParticipantRow | null>(null);
  const { data: draftArtifact } = usePodDraftArtifact(event.eventId);
  const decklistAccess = usePodDecklistAccess(event);
  const deckTargetMainboard = useMemo(
    () =>
      draftArtifact && deckTarget?.seatIndex != null
        ? resolveDeck(draftArtifact, deckTarget.seatIndex)
        : null,
    [draftArtifact, deckTarget],
  );
  const sorted = useMemo(() => {
    if (!rows) return [];
    return [...rows].sort((a, b) => (a.placement ?? 99) - (b.placement ?? 99));
  }, [rows]);
  const visible = sorted.slice(0, STANDINGS_LIMIT);
  const hiddenCount = sorted.length - visible.length;
  const cycleDeck = (direction: number) => {
    if (!deckTarget || visible.length === 0) return;
    const index = visible.indexOf(deckTarget);
    if (index === -1) return;
    for (let step = 1; step <= visible.length; step++) {
      const next = visible[(((index + direction * step) % visible.length) + visible.length) % visible.length];
      if (decklistAccess.canViewSeat(next.avatarUrl)) {
        setDeckTarget(next);
        return;
      }
    }
  };
  return (
    <>
      <div className="border-t border-dashed border-border2">
        <div className="flex flex-col gap-[1px] pb-[1px] bg-bg">
          {isLoading
            ? Array.from({ length: STANDINGS_LIMIT }).map((_, i) => <StandingRowSkeleton key={i} />)
            : visible.map((p) => (
                <StandingRow
                  key={`${p.eventId}-${p.displayName}`}
                  p={decklistAccess.canViewSeat(p.avatarUrl) ? p : { ...p, deckColors: null }}
                  profileHref={p.playerSlug ? playerPath(p.playerSlug, event.setCode) : null}
                  logHref={draftArtifact && decklistAccess.canViewSeat(p.avatarUrl) ? `/pods/${event.slug}/${p.playerSlug ?? p.seatIndex}` : null}
                  onShowDeck={p.deckScreenshotUrl && decklistAccess.canViewSeat(p.avatarUrl) ? () => setDeckTarget(p) : undefined}
                />
              ))}
        </div>
        <Link to={`/pods/${event.slug}`} className="block no-underline">
          <div className="flex justify-between items-center gap-4 pl-2 pr-3 md:pr-4 py-3 bg-surface hover:bg-green/5 transition-colors cursor-pointer">
            {hiddenCount > 0 ? (
              <span className="font-display text-muted tracking-[0.14em] leading-none pl-10 lg:pl-16 whitespace-nowrap" style={{ fontSize: 14 }}>
                +{hiddenCount} MORE {hiddenCount === 1 ? "PLAYER" : "PLAYERS"}
              </span>
            ) : (
              <span />
            )}
            <div className="flex items-center gap-4">
              <span className="hidden lg:inline text-muted text-[13px] font-body">
                {BREAKDOWN_CAPTION}
              </span>
              <ChamferedButton className="!pt-[11px] !pb-[3px]">
                <span className="inline-flex items-center gap-2 whitespace-nowrap">
                  <GiRoundTable size={30} className="-my-[6px]" />
                  VIEW BREAKDOWN
                  <ArrowRight size={14} />
                </span>
              </ChamferedButton>
            </div>
          </div>
        </Link>
      </div>
      {deckTarget && (
        <DeckScreenshotModal
          participant={{
            eventId: deckTarget.eventId,
            displayName: podDiscordName(deckTarget),
            participantDisplayName: deckTarget.displayName,
            deckColors: deckTarget.deckColors,
            deckScreenshotUrl: deckTarget.deckScreenshotUrl,
            deckScreenshotCaption: deckTarget.deckScreenshotCaption,
            mainboard: deckTargetMainboard,
            record: deckTarget.record,
          }}
          draftLogHref={
            draftArtifact && decklistAccess.canViewSeat(deckTarget.avatarUrl)
              ? `/pods/${event.slug}/${deckTarget.playerSlug ?? deckTarget.seatIndex}`
              : null
          }
          breakdownHref={`/pods/${event.slug}?player=${encodeURIComponent(podDiscordName(deckTarget))}`}
          onClose={() => setDeckTarget(null)}
          onPrev={() => cycleDeck(-1)}
          onNext={() => cycleDeck(1)}
        />
      )}
    </>
  );
}

function StandingRow({
  p,
  profileHref,
  logHref,
  onShowDeck,
}: {
  p: PodEventParticipantRow;
  profileHref?: string | null;
  logHref?: string | null;
  onShowDeck?: () => void;
}) {
  const navigate = useNavigate();
  const wins = p.record ? Number(p.record.split("-")[0] || 0) : 0;
  const losses = p.record ? Number(p.record.split("-")[1] || 0) : 0;
  const name = podDiscordName(p);
  const hasDeck = !!onShowDeck;
  const draftLog = !hasDeck ? (logHref ?? null) : null;
  const interactive = hasDeck || !!draftLog;
  const handleRowClick = () => {
    if (onShowDeck) onShowDeck();
    else if (draftLog) navigate(draftLog);
  };
  return (
    <div
      onClick={interactive ? handleRowClick : undefined}
      className={cn(
        "group/row grid items-center gap-x-2 lg:gap-x-3 py-2.5 pl-2 pr-3 lg:pr-5 bg-surface transition-colors",
        STANDING_COLS_CLASS,
        interactive && "cursor-pointer hover:bg-surface2",
      )}
    >
      <span className="mono text-[13px] text-muted text-center">{p.placement ?? ""}</span>
      {profileHref ? (
        <Tooltip label={`View ${name}'s Profile`} side="top" align="start" delayDuration={0}>
          <Link
            to={profileHref}
            onClick={(e) => e.stopPropagation()}
            className="group/name peer/name flex items-center gap-2 lg:gap-2.5 min-w-0 max-w-full justify-self-start w-fit no-underline text-text hover:text-green transition-colors"
          >
            <AAvatar displayName={name} avatarUrl={p.avatarUrl} size={28} />
            <span
              className="font-display leading-none tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis"
              style={{ fontSize: 16 }}
            >
              {name.toUpperCase()}
            </span>
          </Link>
        </Tooltip>
      ) : (
        <div className="flex items-center gap-2 lg:gap-2.5 min-w-0">
          <AAvatar displayName={name} avatarUrl={p.avatarUrl} size={28} />
          <span
            className="font-display text-text leading-none tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis"
            style={{ fontSize: 16 }}
          >
            {name.toUpperCase()}
          </span>
        </div>
      )}
      <div className="flex items-center">
        {p.deckColors ? (
          <Pips colors={p.deckColors} size={14} />
        ) : (
          <span className="text-dim text-[12px]">—</span>
        )}
      </div>
      <Record className="mono text-center text-[13px]" wins={wins} losses={losses} />
      {hasDeck ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onShowDeck?.();
          }}
          className="group/action inline-flex items-center justify-center gap-2 bg-bg border border-border text-text hover:border-green/60 hover:bg-green/10 hover:text-green group-hover/row:border-green/60 group-hover/row:bg-green/10 group-hover/row:text-green peer-hover/name:!border-border peer-hover/name:!bg-bg peer-hover/name:!text-text transition-colors px-1.5 lg:px-3 cursor-pointer whitespace-nowrap"
          style={{ height: 34 }}
        >
          <span
            className="hidden lg:inline font-display tracking-[0.16em] transition-colors leading-none"
            style={{ fontSize: 14 }}
          >
            VIEW DECK
          </span>
          <TbCards size={17} aria-hidden="true" className="transition-colors" />
        </button>
      ) : draftLog ? (
        <Link
          to={draftLog}
          onClick={(e) => e.stopPropagation()}
          className="group/action inline-flex items-center justify-center gap-2 bg-bg border border-border text-text hover:border-green/60 hover:bg-green/10 hover:text-green group-hover/row:border-green/60 group-hover/row:bg-green/10 group-hover/row:text-green peer-hover/name:!border-border peer-hover/name:!bg-bg peer-hover/name:!text-text transition-colors px-1.5 lg:px-3 no-underline whitespace-nowrap"
          style={{ height: 34 }}
        >
          <span
            className="hidden lg:inline font-display tracking-[0.16em] transition-colors leading-none"
            style={{ fontSize: 14 }}
          >
            DRAFT LOG
          </span>
          <LuScrollText size={16} aria-hidden="true" className="transition-colors" />
        </Link>
      ) : (
        <span />
      )}
    </div>
  );
}

function StandingRowSkeleton() {
  return (
    <div
      className={cn(
        "grid items-center gap-x-2 lg:gap-x-3 py-2.5 pl-2 pr-3 lg:pr-5 bg-surface",
        STANDING_COLS_CLASS,
      )}
    >
      <div className="h-3 w-3 bg-surface2 animate-pulse mx-auto" />
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 bg-surface2" />
        <div className="h-3.5 w-32 bg-surface2 animate-pulse" />
      </div>
      <div className="h-3.5 w-14 bg-surface2 animate-pulse" />
      <div className="h-3.5 w-10 bg-surface2 animate-pulse ml-auto" />
      <div className="h-[34px] w-full bg-surface2 animate-pulse" />
    </div>
  );
}

function EventRowSkeleton({ index }: { index: number }) {
  return (
    <div
      className="bg-surface border-b lg:border border-border first:lg:border-t-0 min-h-[68px] flex items-stretch animate-fadeUpIn"
      style={{ animationDelay: `${Math.min(index, 6) * 45}ms` }}
    >
      <div className="px-3 min-w-[72px] md:min-w-[78px] bg-surface2/40 border-r border-border flex flex-col items-center justify-center gap-1.5">
        <div className="h-4 w-10 bg-surface2 animate-pulse" />
        <div className="h-5 w-8 bg-surface2 animate-pulse" />
      </div>
      <div className="flex-1 flex items-center px-3 md:px-4">
        <div className="h-4 w-2/3 bg-surface2 animate-pulse" />
      </div>
    </div>
  );
}

function EventsLoadingBlock() {
  return (
    <div>
      <SectionHeading label="EVENTS" unit="EVENTS" />
      <div className="flex flex-col lg:gap-2">
        {[0, 1, 2].map((i) => (
          <EventRowSkeleton key={i} index={i} />
        ))}
      </div>
    </div>
  );
}

type EventsTab = "last" | "upcoming" | "all";

function MobileEventsBlock({
  played,
  upcoming,
  nowMs,
}: {
  played: PodEventSummary[];
  upcoming: PodEventSummary[];
  nowMs: number;
}) {
  const [tab, setTab] = useState<EventsTab>("last");
  const list = useMemo<PodEventSummary[]>(() => {
    if (tab === "last") return played[0] ? [played[0]] : [];
    if (tab === "upcoming") return upcoming;
    return played;
  }, [tab, played, upcoming]);
  return (
    <div>
      <div className="flex border-b border-border">
        <EventsTabButton active={tab === "last"} onClick={() => setTab("last")}>
          LAST EVENT
        </EventsTabButton>
        <EventsTabButton active={tab === "upcoming"} onClick={() => setTab("upcoming")}>
          UPCOMING
        </EventsTabButton>
        <EventsTabButton active={tab === "all"} onClick={() => setTab("all")}>
          ALL
        </EventsTabButton>
      </div>
      {list.length === 0 ? (
        <EmptyHint>
          {tab === "upcoming" ? "No upcoming pod drafts." : "No pod drafts yet."}
        </EmptyHint>
      ) : (
        <div className="flex flex-col">
          {list.map((e, i) => (
            <EventRow
              key={e.eventId}
              event={e}
              index={i}
              nowMs={nowMs}
              defaultOpen={i === 0}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EventsTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 py-2.5 px-1.5 bg-transparent cursor-pointer font-display text-[11px] tracking-[0.16em] transition-colors border-b-2 border-solid",
        active ? "text-text border-green" : "text-muted border-transparent",
      )}
      style={active ? { marginBottom: -1 } : undefined}
    >
      {children}
    </button>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-muted text-[13px] py-4 px-2 bg-surface border border-border">
      {children}
    </div>
  );
}

function MobileSetStrip({
  activeSet,
  availableSets,
  onSelectSet,
}: {
  activeSet: string;
  availableSets: SetSummary[];
  onSelectSet: (code: string) => void;
}) {
  return (
    <div className="px-3 pt-2 pb-1 border-b border-border bg-surface flex items-center gap-3">
      <div className="pl-1 pr-1">
        <SetGlyph
          code={setGlyphCode(availableSets.find((s) => s.code === activeSet) ?? { code: activeSet })}
          size={32}
        />
      </div>
      <span className="font-display text-text tracking-[0.04em]" style={{ fontSize: 28, lineHeight: 1 }}>
        {activeSet}
      </span>
      {availableSets.length > 0 && (
        <div className="ml-auto basis-[34%] min-w-0">
          <SetSwitcherMobile sets={availableSets} activeCode={activeSet} onChange={onSelectSet} />
        </div>
      )}
    </div>
  );
}

function SetHero({
  activeSet,
  setMeta,
  sets,
  onSelectSet,
}: {
  activeSet: string;
  setMeta: SetSummary | undefined;
  sets: SetSummary[];
  onSelectSet: (code: string) => void;
}) {
  const week = weekOfSet(setMeta);
  const isActive = setMeta?.isActive ?? false;
  return (
    <div className="relative px-10 py-5 border-b border-border bg-surface flex items-center gap-6">
      <SetGlyph code={setMeta ? setGlyphCode(setMeta) : activeSet} size={84} />
      <div>
        <SectionLabel size={13} className={isActive ? "" : "invisible"}>CURRENT SET</SectionLabel>
        <div className="flex items-baseline gap-3.5 mt-0.5">
          <span className="font-display tracking-[0.04em]" style={{ fontSize: 56, lineHeight: 0.9 }}>
            {activeSet}
          </span>
          <span className="font-display text-[22px] text-muted tracking-[0.06em]">
            {setMeta?.name?.toUpperCase() ?? ""}
          </span>
        </div>
        <div className="mono text-[11px] text-muted mt-1 flex justify-between gap-4">
          {setMeta && <span>{fmtRange(setMeta.startDate, setMeta.endDate)}</span>}
          {week && <span>{week}</span>}
        </div>
      </div>
      <div className="flex-1" />
      {sets.length > 0 && (
        <SetSwitcherDesktop sets={sets} activeCode={activeSet} onChange={onSelectSet} />
      )}
    </div>
  );
}
