import { Fragment, createContext, useContext, useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, ExternalLink, UserMinus, X } from "lucide-react";
import { SectionLabel } from "../SectionLabel";
import { Trophy } from "../Brand";
import { cn } from "../../lib/utils";
import {
  CountryFlag,
  PlayerPortrait,
  qualificationLabel,
  formatRecord,
  fullName,
  statsFor,
  qualificationOf,
  slotFor,
  type FieldPlayer,
  type CareerStats,
  type MatchRecord,
  type PlayerStats,
  type Slot,
} from "./fantasyField";
import type { RoundResult } from "./fantasyScoring";
import { meleeEventUrl, useFantasyEvent } from "./fantasyEvents";

export type ProfileRound = { round: number; result: RoundResult | null; draft: boolean };

export type MatchHistoryRow = {
  round: number;
  draft: boolean;
  opponent: FieldPlayer | null;
  opponentHref?: string;
  opponentDeck: string | null;
  result: RoundResult;
  games: string;
};

export type ProfileEvent = {
  title: string;
  headline: string;
  detail?: string;
  rounds: ProfileRound[];
  dayOneRounds: number;
  constructedFormat: string;
  meleeUrl?: string;
  deck?: { name: string; url: string | null };
  history?: MatchHistoryRow[];
};

export function PlayerProfileSheet({
  player,
  event,
  footer,
  prevHref,
  nextHref,
  onClose,
}: {
  player: FieldPlayer;
  event?: ProfileEvent;
  footer?: ReactNode;
  prevHref?: string;
  nextHref?: string;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const handleKey = (keyEvent: KeyboardEvent) => {
      if (keyEvent.key === "Escape") {
        onClose();
      }
      const target = keyEvent.key === "ArrowLeft" ? prevHref : keyEvent.key === "ArrowRight" ? nextHref : undefined;
      if (target) {
        navigate(target, { replace: true, state: location.state });
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose, prevHref, nextHref, location.state]);

  const history = event?.history;
  return createPortal(
    <div
      data-keeps-active-slot
      className={cn(
        "fixed inset-0 z-[200] flex justify-center bg-black/70 p-4 animate-fadeIn",
        "select-none [-webkit-touch-callout:none]",
        history ? "items-start lg:pt-[12vh]" : "items-center",
      )}
      onClick={onClose}
      onContextMenu={(clickEvent) => clickEvent.preventDefault()}
    >
      <div
        className={cn(
          "w-full max-w-[440px] max-h-full overflow-y-auto overflow-x-hidden rounded-xl",
          "border border-border2 bg-surface shadow-2xl",
          history && "lg:max-w-[900px]",
        )}
        onClick={(clickEvent) => clickEvent.stopPropagation()}
      >
        <div
          className={cn(
            "relative flex items-center gap-3 px-4 pt-3 pb-2",
            history && "lg:grid lg:grid-cols-[340px_1fr] lg:gap-0 lg:p-0",
          )}
        >
          <SectionLabel size={12} color="#b8c0d0" className={cn("shrink-0", history && "lg:pl-4 lg:pt-3 lg:pb-2")}>
            PLAYER PROFILE
          </SectionLabel>
          {history && event ? (
            <span
              className={cn(
                "hidden lg:grid grid-cols-[1fr_auto_1fr] items-center self-stretch",
                "border-l border-border pl-4 pr-[96px] pt-3 pb-2",
              )}
            >
              <SectionLabel size={12} color="#b8c0d0">
                DAY 1
              </SectionLabel>
              <FormatLegend format={event.constructedFormat} />
            </span>
          ) : null}
          <span className="ml-auto flex items-center gap-1 lg:absolute lg:right-4 lg:top-2.5">
            {prevHref || nextHref ? (
              <>
                <SheetNavLink href={prevHref} label="Previous player">
                  <ChevronLeft size={20} />
                </SheetNavLink>
                <SheetNavLink href={nextHref} label="Next player">
                  <ChevronRight size={20} />
                </SheetNavLink>
              </>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close profile"
              className="ml-1 p-1 text-subtle hover:text-text bg-transparent border-0 cursor-pointer"
            >
              <X size={20} />
            </button>
          </span>
        </div>
        <div className={cn(history && "lg:grid lg:grid-cols-[340px_1fr]")}>
          <div className="px-4 pb-2">
            <PlayerProfile player={player} compact dense event={event} showRounds={!history} />
          </div>
          {history && event ? (
            <div className="min-w-0 px-4 pb-4 border-t border-border pt-3 lg:border-t-0 lg:border-l lg:pt-0">
              <MatchHistory history={history} event={event} />
            </div>
          ) : null}
        </div>
        {footer ? <div className="px-4 pb-4">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}

function SheetNavLink({ href, label, children }: { href?: string; label: string; children: ReactNode }) {
  const location = useLocation();
  if (!href) {
    return (
      <span aria-hidden="true" className="p-1 text-muted opacity-40">
        {children}
      </span>
    );
  }
  return (
    <Link
      to={href}
      replace
      state={location.state}
      aria-label={label}
      className="p-1 flex text-subtle hover:text-text no-underline"
    >
      {children}
    </Link>
  );
}

export function PlayerProfile({
  player,
  compact = false,
  dense = false,
  event,
  showRounds = true,
  preview = false,
}: {
  player: FieldPlayer;
  compact?: boolean;
  dense?: boolean;
  event?: ProfileEvent;
  showRounds?: boolean;
  preview?: boolean;
}) {
  const stats = statsFor(player);
  const fantasyEventCode = useFantasyEvent().code;
  const nameOnOneLine = dense && fullName(player).length <= 12;
  const nameClass = "font-display leading-[0.95] tracking-[0.04em] min-w-0";
  const nameStyle = { fontSize: dense ? 24 : compact ? 26 : 32 };
  return (
    <ProfilePreviewContext.Provider value={preview}>
      <div className="flex flex-col">
        <div
          className={cn(
            "grid grid-cols-[auto_minmax(0,1fr)_auto] grid-rows-[1fr_auto_auto_auto] gap-x-3.5",
            !compact && "gap-x-5",
          )}
        >
          <span
            className={cn(
              "row-span-4 self-end relative shrink-0 aspect-[3/4] overflow-hidden",
              "bg-surface2 border-2 border-border2",
            )}
            style={{ width: dense ? 58 : compact ? 84 : 132 }}
          >
            <PlayerPortrait player={player} initialsSize={compact ? 26 : 40} />
          </span>
          <span className="col-start-2 row-start-1 self-end flex flex-col gap-1.5">
            {dense ? null : <CountryFlag code={player.countryCode} width={compact ? 22 : 30} />}
            {nameOnOneLine ? null : (
              <span className={nameClass} style={nameStyle}>
                {player.firstName.toUpperCase()}
              </span>
            )}
          </span>
          {event ? (
            <SectionLabel
              size={12}
              color="#b8c0d0"
              className="col-start-3 row-start-1 self-end text-right whitespace-nowrap"
            >
              {event.title}
            </SectionLabel>
          ) : null}
          <span className={cn(nameClass, "col-start-2 row-start-2 self-baseline")} style={nameStyle}>
            {nameOnOneLine ? fullName(player).toUpperCase() : player.lastName.toUpperCase()}
          </span>
          {event ? (
            <span
              className={cn(
                "col-start-3 row-start-2 self-baseline text-right",
                "font-display text-[22px] tracking-[0.04em] leading-none text-text whitespace-nowrap",
              )}
            >
              {event.headline}
            </span>
          ) : null}
          <span className="col-start-2 row-start-3 mt-1.5 flex items-center gap-1.5 text-[14px] text-subtle min-w-0">
            {dense ? <CountryFlag code={player.countryCode} width={18} /> : null}
            <span className="truncate">{player.country}</span>
          </span>
          {event?.detail ? (
            <span
              className={cn(
                "col-start-3 row-start-3 mt-1.5 justify-self-end max-w-[96px] text-right",
                "font-num text-[15px] leading-tight text-text",
              )}
            >
              {event.detail}
            </span>
          ) : null}
        </div>
        {event?.deck ? <DeckLine deck={event.deck} /> : null}

        {player.sources.length > 0 ? (
          <div className={cn("text-[14px] text-text", dense ? "mt-2.5" : compact ? "mt-3" : "mt-5")}>
            <span className="text-subtle">Qualified by </span>
            {qualificationLabel(qualificationOf(player), [player])}
          </div>
        ) : null}

        {event ? <EventRounds event={event} showRounds={showRounds} /> : null}

        {stats ? (
          <ProStats
            stats={stats}
            compact={compact}
            dense={dense}
            meleeUrl={event?.meleeUrl ?? meleeEventUrl(fantasyEventCode)}
          />
        ) : null}
      </div>
    </ProfilePreviewContext.Provider>
  );
}

export function PickButton({
  activeSlot,
  inLineup,
  onToggle,
}: {
  activeSlot: Slot | null;
  inLineup: boolean;
  onToggle: () => void;
}) {
  if (!inLineup && !activeSlot) {
    return <div className="text-center text-[14px] text-subtle">Select a card in your lineup to replace</div>;
  }
  if (inLineup || !activeSlot) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          "w-full py-2.5 flex items-center justify-center gap-2 font-display text-[15px] tracking-[0.14em]",
          "cursor-pointer border border-red/60 bg-red/10 text-red hover:bg-red/20 transition-colors",
        )}
      >
        <UserMinus size={17} className="-translate-y-px" />
        REMOVE FROM LINEUP
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onToggle}
      className="w-full py-2.5 font-display text-[15px] tracking-[0.14em] cursor-pointer border"
      style={{ background: activeSlot.accent, borderColor: activeSlot.accent, color: "#0a0c10" }}
    >
      {`PICK AS ${activeSlot.label.toUpperCase()}`}
    </button>
  );
}

function ProStats({
  stats,
  compact,
  dense,
  meleeUrl,
}: {
  stats: PlayerStats;
  compact: boolean;
  dense: boolean;
  meleeUrl?: string;
}) {
  const { recent, career } = stats;
  const preview = useContext(ProfilePreviewContext);
  const overall = combineRecords(recent.limited, recent.constructed);
  return (
    <>
      <SectionLabel size={14} color="#b8c0d0" className={cn(compact ? "mt-3 mb-1.5" : "mt-5 mb-2", dense && "mt-2.5")}>
        LAST 7 PT<span className="font-body font-semibold lowercase tracking-normal">s</span> & WORLDS
      </SectionLabel>
      <div className="grid grid-cols-3 gap-px bg-border border border-border">
        <Tally label="EVENTS" value={recent.events} compact={compact} />
        <Tally label="DAY 2" value={recent.day2s} compact={compact} />
        <Tally label="TOP 8" value={recent.top8s} compact={compact} />
      </div>

      <table className="w-full mt-1.5 border-collapse text-[14px]">
        <thead>
          <tr className="text-left">
            <th className="w-full py-1 font-normal" />
            <th className="py-1 px-2 font-normal text-center" title="Trophy Drafts">
              <span className="inline-flex translate-y-[2px]"><Trophy size={14} color="#ffc63a" /></span>
            </th>
            <th className="py-1 pl-2 font-display font-normal text-[13px] tracking-[0.14em] text-subtle text-right">RECORD</th>
            <th className="py-1 pl-5 font-display font-normal text-[13px] tracking-[0.14em] text-subtle text-right whitespace-nowrap">WIN %</th>
          </tr>
        </thead>
        <tbody>
          <RecordRow label="Overall" record={overall} compact={compact} />
          <RecordRow
            label="Limited"
            record={recent.limited}
            trophies={recent.trophyDrafts}
            accent={slotFor("drafter").accent}
            compact={compact}
          />
          <RecordRow label="Constructed" record={recent.constructed} accent={slotFor("constructed").accent} compact={compact} />
          <RecordRow label="Day 1" record={recent.dayOne} compact={compact} />
          <RecordRow label="Day 2" record={recent.dayTwo} compact={compact} />
        </tbody>
      </table>
      <SourceLine>
        Recent stats from <SourceLink href={meleeUrl ?? "https://melee.gg"}>melee.gg</SourceLink>
      </SourceLine>

      {preview ? null : <CareerSummary career={career} compact={compact} />}
    </>
  );
}

function SourceLine({ className, children }: { className?: string; children: ReactNode }) {
  return <p className={cn("mt-1 text-[12px] text-subtle leading-[1.5] text-right", className)}>{children}</p>;
}

function SourceLink({ href, children }: { href: string; children: ReactNode }) {
  if (useContext(ProfilePreviewContext)) {
    return <span className="text-green">{children}</span>;
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-green hover:underline">
      {children}
    </a>
  );
}

type DayRow = { label: string; segments: ProfileRound[][] };

const SEGMENT_GAP = 8;

function EventRounds({ event, showRounds }: { event: ProfileEvent; showRounds: boolean }) {
  if (!showRounds) {
    return null;
  }
  return (
    <div className="mt-3">
      <SplitRounds days={dayRows(event)} event={event} />
    </div>
  );
}

function SplitRounds({ days, event }: { days: DayRow[]; event: ProfileEvent }) {
  const header = days[0].segments;
  return (
    <div className="grid items-center gap-x-[3px] gap-y-1" style={{ gridTemplateColumns: segmentColumns(header) }}>
      <span />
      {header.map((segment, index) => (
        <Fragment key={segment[0].round}>
          {index > 0 ? <span /> : null}
          <span
            className="font-display text-[12px] tracking-[0.12em] pb-0.5"
            style={{ gridColumn: `span ${segment.length + 1}`, color: formatAccent(segment[0].draft) }}
          >
            {segmentLabel(segment, event)}
          </span>
        </Fragment>
      ))}
      {days.map((day) => (
        <DaySplitRow key={day.label} day={day} />
      ))}
    </div>
  );
}

function DaySplitRow({ day }: { day: DayRow }) {
  return (
    <>
      <span className="font-display text-[12px] tracking-[0.12em] text-subtle whitespace-nowrap">{day.label}</span>
      {day.segments.map((segment, index) => (
        <SegmentCells key={segment[0].round} segment={segment} spaced={index > 0} />
      ))}
    </>
  );
}

function SegmentCells({ segment, spaced }: { segment: ProfileRound[]; spaced: boolean }) {
  return (
    <>
      {spaced ? <span /> : null}
      <span className="justify-self-end pr-1 font-num text-[15px] font-semibold text-text whitespace-nowrap">
        {segmentRecord(segment) || "-"}
      </span>
      {segment.map(({ round, result }) => (
        <ResultCell key={round} result={result} />
      ))}
    </>
  );
}

function ResultCell({ result, accent }: { result: RoundResult | null; accent?: string }) {
  return (
    <span
      className={cn(
        "h-[22px] flex items-center justify-center border font-num text-[13px] font-semibold leading-none",
        result ? "border-border2 bg-surface2" : "border-border bg-transparent",
        result === "W" ? "text-text" : "text-subtle",
      )}
      style={accent && result ? { borderColor: `${accent}66`, background: `${accent}1f` } : undefined}
    >
      {result ?? ""}
    </span>
  );
}

function FormatLegend({ format }: { format: string }) {
  return (
    <span className="flex items-center gap-3 text-[13px] text-subtle whitespace-nowrap">
      <span className="flex items-center gap-1.5">
        <FormatBadge draft letter="D" />
        Draft
      </span>
      <span className="flex items-center gap-1.5">
        <FormatBadge draft={false} letter={format.charAt(0)} />
        {format}
      </span>
    </span>
  );
}

function MatchHistory({ history, event }: { history: MatchHistoryRow[]; event: ProfileEvent }) {
  const dayOne = history.filter((row) => row.round <= event.dayOneRounds);
  const dayTwo = history.filter((row) => row.round > event.dayOneRounds);
  const days = [
    { label: "DAY 1", rows: dayOne },
    { label: "DAY 2", rows: dayTwo },
  ];
  return (
    <div
      className={cn(
        "grid items-center gap-x-2.5",
        "grid-cols-[20px_20px_minmax(0,1fr)_auto]",
        "lg:grid-cols-[20px_20px_minmax(0,max-content)_minmax(0,1fr)_auto]",
      )}
    >
      {days
        .filter((day) => day.rows.length > 0)
        .map((day, index) => (
          <Fragment key={day.label}>
            <div
              className={cn(
                "col-span-full grid grid-cols-[1fr_auto_1fr] items-center mb-1",
                index > 0 ? "mt-3" : "lg:hidden",
              )}
            >
              <SectionLabel size={12} color="#b8c0d0">
                {day.label}
              </SectionLabel>
              {index === 0 ? (
                <span className="lg:hidden">
                  <FormatLegend format={event.constructedFormat} />
                </span>
              ) : null}
            </div>
            {day.rows.map((row, rowIndex) => (
              <HistoryRow
                key={row.round}
                row={row}
                formatLetter={event.constructedFormat.charAt(0)}
                last={rowIndex === day.rows.length - 1}
              />
            ))}
          </Fragment>
        ))}
    </div>
  );
}

function HistoryRow({ row, formatLetter, last }: { row: MatchHistoryRow; formatLetter: string; last: boolean }) {
  const location = useLocation();
  return (
    <div
      className={cn(
        "col-span-full grid grid-cols-subgrid items-center py-1 lg:py-1.5 text-[14px]",
        !last && "border-b border-border",
      )}
    >
      <FormatBadge draft={row.draft} letter={row.draft ? "D" : formatLetter} />
      <span className="text-right font-num text-subtle">{row.round}</span>
      <span className="min-w-0 flex flex-col">
        <span className="flex items-center gap-1.5 min-w-0">
          <span className="w-[18px] shrink-0 flex">
            {row.opponent ? <CountryFlag code={row.opponent.countryCode} width={18} /> : null}
          </span>
          {row.opponentHref && row.opponent ? (
            <Link
              to={row.opponentHref}
              replace
              state={location.state}
              className="truncate text-text no-underline hover:underline"
            >
              {fullName(row.opponent)}
            </Link>
          ) : (
            <span className="truncate text-text">{row.opponent ? fullName(row.opponent) : "Bye"}</span>
          )}
        </span>
        {row.opponentDeck ? (
          <span className="truncate text-[12px] text-subtle lg:hidden">{row.opponentDeck}</span>
        ) : null}
      </span>
      <span className="hidden lg:block min-w-0 truncate text-[13px] text-subtle">{row.opponentDeck}</span>
      <span
        className={cn(
          "font-num whitespace-nowrap text-left",
          row.result === "W" ? "text-green" : "text-subtle",
        )}
      >
        {RESULT_LABEL[row.result]} {row.games}
      </span>
    </div>
  );
}

const RESULT_LABEL: Record<RoundResult, string> = { W: "Win", L: "Loss", D: "Draw" };

function FormatBadge({ draft, letter }: { draft: boolean; letter: string }) {
  const accent = formatAccent(draft);
  return (
    <span
      className="w-5 h-5 shrink-0 rounded-full flex items-center justify-center font-display text-[12px] leading-none"
      style={{ background: `${accent}26`, color: accent, boxShadow: `inset 0 0 0 1px ${accent}88` }}
    >
      <span className="[text-box:trim-both_cap_alphabetic]">{letter}</span>
    </span>
  );
}

function DeckLine({ deck }: { deck: NonNullable<ProfileEvent["deck"]> }) {
  const preview = useContext(ProfilePreviewContext);
  return (
    <div className="mt-1.5 flex items-baseline justify-end gap-2 min-w-0 text-[13px]">
      <span className="font-display text-[12px] tracking-[0.12em] text-subtle whitespace-nowrap">DECK</span>
      {deck.url && preview ? (
        <span className="truncate text-green">{deck.name}</span>
      ) : deck.url ? (
        <a
          href={deck.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 min-w-0 text-green hover:underline"
        >
          <span className="truncate">{deck.name}</span>
          <ExternalLink size={12} className="shrink-0 -translate-y-px" />
        </a>
      ) : (
        <span className="truncate text-text">{deck.name}</span>
      )}
    </div>
  );
}

function dayRows(event: ProfileEvent): DayRow[] {
  const dayOne = event.rounds.filter((entry) => entry.round <= event.dayOneRounds);
  const dayTwo = event.rounds.filter((entry) => entry.round > event.dayOneRounds);
  return [
    { label: "DAY 1", segments: formatSegments(dayOne) },
    { label: "DAY 2", segments: formatSegments(dayTwo) },
  ];
}

function formatSegments(rounds: ProfileRound[]): ProfileRound[][] {
  const segments: ProfileRound[][] = [];
  for (const entry of rounds) {
    const current = segments[segments.length - 1];
    if (current && current[0].draft === entry.draft) {
      current.push(entry);
    } else {
      segments.push([entry]);
    }
  }
  return segments;
}

function segmentColumns(segments: ProfileRound[][]): string {
  const parts = ["44px"];
  segments.forEach((segment, index) => {
    if (index > 0) {
      parts.push(`${SEGMENT_GAP}px`);
    }
    parts.push("34px", `repeat(${segment.length}, minmax(0, 1fr))`);
  });
  return parts.join(" ");
}

function segmentLabel(segment: ProfileRound[], event: ProfileEvent): string {
  return segment[0].draft ? "DRAFT" : event.constructedFormat.toUpperCase();
}

function segmentRecord(segment: ProfileRound[]): string {
  const record = { wins: 0, losses: 0, draws: 0 };
  for (const { result } of segment) {
    if (result === "W") {
      record.wins += 1;
    } else if (result === "L") {
      record.losses += 1;
    } else if (result === "D") {
      record.draws += 1;
    }
  }
  const played = record.wins + record.losses + record.draws;
  return played === 0 ? "" : formatRecord(record);
}

function formatAccent(draft: boolean): string {
  return draft ? slotFor("drafter").accent : slotFor("constructed").accent;
}

function CareerSummary({ career, compact }: { career: CareerStats; compact: boolean }) {
  if (career.proTours === null) {
    return null;
  }
  const highlights = careerHighlights(career).slice(0, 3);
  const highlighted = new Set(highlights.map((highlight) => highlight.key));
  const worldsWon = career.worldsWins ? `, ${career.worldsWins} won` : "";
  const worlds = career.worldsTop8s ? `${career.worldsTop8s}${worldsWon}` : null;
  return (
    <div className={compact ? "mt-2" : "mt-4"}>
      <div className="flex items-baseline justify-between mb-1.5">
        <SectionLabel size={14} color="#b8c0d0">CAREER</SectionLabel>
        {career.hallOfFameYear ? (
          <span className="text-[13px] text-gold">Hall of Fame {career.hallOfFameYear}</span>
        ) : null}
      </div>
      {highlights.length > 0 ? (
        <div
          className="grid gap-px bg-border border border-border"
          style={{ gridTemplateColumns: `repeat(${highlights.length}, minmax(0, 1fr))` }}
        >
          {highlights.map((highlight) => (
            <Tally key={highlight.key} label={highlight.label} value={highlight.value} compact={compact} />
          ))}
        </div>
      ) : null}
      <div className="mt-1 flex flex-col text-[14px]">
        {worlds ? <CareerLine label="Worlds Top 8" value={worlds} /> : null}
        {career.gpTop8s && !highlighted.has("gpTop8s") ? (
          <CareerLine label="Grand Prix Top 8" value={String(career.gpTop8s)} />
        ) : null}
        {career.regionalTop8s && !highlighted.has("regionalTop8s") ? (
          <CareerLine label="Regional Top Finishes" value={String(career.regionalTop8s)} />
        ) : null}
        {career.proRecord ? (
          <CareerLine
            label={career.proRecordSince ? `Pro Record since ${career.proRecordSince}` : "Pro Record"}
            value={formatRecord(career.proRecord)}
          />
        ) : null}
      </div>
      <SourceLine>
        Career stats from <SourceLink href={eloUrl(career)}>MTG Elo Project</SourceLink> and{" "}
        <SourceLink href={mtgwikiUrl(career)}>mtg.wiki</SourceLink>
      </SourceLine>
    </div>
  );
}

function eloUrl(career: CareerStats): string {
  return career.eloId ? `https://mtgeloproject.net/profile/${career.eloId}` : "https://mtgeloproject.net";
}

function mtgwikiUrl(career: CareerStats): string {
  if (!career.mtgwikiPage) {
    return "https://mtg.wiki";
  }
  return `https://mtg.wiki/page/${encodeURIComponent(career.mtgwikiPage.replaceAll(" ", "_"))}`;
}

type CareerHighlight = { key: keyof CareerStats; label: string; value: number };

function careerHighlights(career: CareerStats): CareerHighlight[] {
  const candidates: CareerHighlight[] = [
    { key: "ptWins", label: "PT WINS", value: career.ptWins ?? 0 },
    { key: "topFinishes", label: "TOP FINISHES", value: career.topFinishes ?? 0 },
    { key: "proTours", label: "PRO TOURS", value: career.proTours ?? 0 },
    { key: "regionalTop8s", label: "REGIONAL TOP FINISHES", value: career.regionalTop8s ?? 0 },
    { key: "gpTop8s", label: "GP TOP 8", value: career.gpTop8s ?? 0 },
  ];
  return candidates.filter((candidate) => candidate.value > 0);
}

function CareerLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between py-0.5 border-b border-border last:border-b-0">
      <span className="text-text">{label}</span>
      <span className="font-num text-text">{value}</span>
    </div>
  );
}

function Tally({
  label,
  value,
  compact,
}: {
  label: string;
  value: number;
  compact: boolean;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center bg-surface", compact ? "py-1.5" : "py-3")}>
      <span
        className={cn("font-num font-semibold leading-none", compact ? "text-[18px]" : "text-[24px]")}
      >
        {value}
      </span>
      <span
        className={cn(
          "font-display tracking-[0.14em] text-subtle text-center leading-tight",
          compact ? "text-[12px] mt-1" : "text-[13px] mt-1.5",
        )}
      >
        {label}
      </span>
    </div>
  );
}

function RecordRow({
  label,
  record,
  trophies,
  accent,
  compact,
}: {
  label: string;
  record: MatchRecord;
  trophies?: number;
  accent?: string;
  compact: boolean;
}) {
  const played = record.wins + record.losses + record.draws;
  const winRate = played === 0 ? 0 : (record.wins / played) * 100;
  const cell = compact ? "py-1" : "py-2.5";
  return (
    <tr className="border-t border-border">
      <td className={cn(cell, "text-text")}>{label}</td>
      <td className={cn(cell, "px-2 text-center font-num")}>{trophies === undefined ? "" : trophies || "-"}</td>
      <td className={cn(cell, "pl-2 text-right font-num whitespace-nowrap")}>{formatRecord(record)}</td>
      <td className={cn(cell, "text-right font-num")} style={accent ? { color: accent } : undefined}>
        {winRate.toFixed(1)}
      </td>
    </tr>
  );
}

function combineRecords(first: MatchRecord, second: MatchRecord): MatchRecord {
  return {
    wins: first.wins + second.wins,
    losses: first.losses + second.losses,
    draws: first.draws + second.draws,
  };
}

const ProfilePreviewContext = createContext(false);
