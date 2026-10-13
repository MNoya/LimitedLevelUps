import { useMemo, type MouseEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowDown, ArrowUp } from "lucide-react";
import { cn } from "../../lib/utils";
import { CountryFlag, PlayerPortrait, formatRecord, fullName, type FieldPlayer } from "./fantasyField";
import { standingsAfter, standingsRound, type StandingsRow, type StandingsSource } from "./fantasyReplay";

export function ReplayStandings({
  source,
  compact,
  playerHref,
  onOpen,
  onHover,
  onLeave,
}: {
  source: StandingsSource;
  compact: boolean;
  playerHref?: (player: FieldPlayer) => string;
  onOpen?: (player: FieldPlayer) => void;
  onHover: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave: () => void;
}) {
  const [searchParams] = useSearchParams();
  const round = standingsRound(source, searchParams.get("round"));
  const rows = useMemo(() => standingsAfter(source, round), [source, round]);
  return (
    <div className="flex flex-col gap-4 max-w-[980px] mx-auto">
      <RoundChips source={source} round={round} hrefFor={(option) => roundHref(searchParams, option)} />
      <div className="border border-border">
        <StandingsHeader compact={compact} />
        {rows.map((row) => (
          <StandingsLine
            key={fullName(row.player)}
            row={row}
            compact={compact}
            topEightLine={round === source.swissRounds && row.rank === 8}
            href={playerHref?.(row.player)}
            onOpen={onOpen}
            onHover={onHover}
            onLeave={onLeave}
          />
        ))}
      </div>
    </div>
  );
}

export function StandingsSkeleton({ compact, rows }: { compact: boolean; rows: number }) {
  const nameWidths = [62, 48, 70, 55, 66, 44, 58, 74, 50, 64];
  return (
    <div className="border border-border max-w-[980px] mx-auto">
      <StandingsHeader compact={compact} />
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className={cn(
            "grid items-center gap-x-3 px-3 py-1.5 border-t border-border bg-surface",
            standingsColumns(compact),
          )}
        >
          <span className="justify-self-end font-num font-semibold text-subtle text-[14px]">{index + 1}</span>
          <span />
          <span className="flex items-center gap-2.5 min-w-0">
            <span className="w-7 h-7 shrink-0 bg-surface2" />
            <SkeletonBar width={`${nameWidths[index % nameWidths.length]}%`} />
          </span>
          {compact ? (
            <SkeletonBar width="36px" className="justify-self-end" />
          ) : (
            <>
              <SkeletonBar width={`${nameWidths[(index + 3) % nameWidths.length]}%`} />
              <SkeletonBar width="14px" className="justify-self-center" />
              <SkeletonBar width="14px" className="justify-self-center" />
              <SkeletonBar width="14px" className="justify-self-center" />
            </>
          )}
        </div>
      ))}
    </div>
  );
}

function StandingsHeader({ compact }: { compact: boolean }) {
  return (
    <div
      className={cn(
        "grid items-center gap-x-3 px-3 py-2 bg-surface2 font-display text-[13px] tracking-[0.14em] text-subtle",
        standingsColumns(compact),
      )}
    >
      <span className="text-right">RANK</span>
      <span />
      <span>NAME</span>
      {compact ? (
        <span className="text-right">RECORD</span>
      ) : (
        <>
          <span>DECK</span>
          <span className="text-center">WIN</span>
          <span className="text-center">LOSS</span>
          <span className="text-center">DRAW</span>
        </>
      )}
    </div>
  );
}

function SkeletonBar({ width, className }: { width: string; className?: string }) {
  return <span className={cn("h-3 bg-surface2", className)} style={{ width }} />;
}

function standingsColumns(compact: boolean): string {
  return compact ? "grid-cols-[34px_36px_1fr_auto]" : "grid-cols-[44px_44px_1fr_220px_44px_44px_44px]";
}

function RoundChips({
  source,
  round,
  hrefFor,
}: {
  source: StandingsSource;
  round: number;
  hrefFor: (round: number) => string;
}) {
  const days = [
    { label: "DAY 1", rounds: roundRange(1, Math.min(source.cutRound, source.lastRound)) },
    { label: "DAY 2", rounds: roundRange(source.cutRound + 1, source.lastRound) },
  ].filter((day) => day.rounds.length > 0);
  return (
    <div className="-mx-3 px-3 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
      <div className="w-max flex items-center gap-x-5 mx-auto">
        <span className="font-display text-[13px] tracking-[0.14em] text-subtle">AFTER ROUND</span>
        {days.map((day) => (
          <span key={day.label} className="flex items-center gap-1.5">
            <span className="font-display text-[12px] tracking-[0.12em] text-subtle mr-1">{day.label}</span>
            {day.rounds.map((option) => (
              <Link
                key={option}
                to={hrefFor(option)}
                replace
                className={cn(
                  "min-w-[32px] px-2 py-1 border font-num text-[13px] text-center no-underline transition-colors",
                  option === round
                    ? "border-green/60 bg-green/10 text-text"
                    : "border-border2 bg-surface text-subtle hover:text-text",
                )}
              >
                {option}
              </Link>
            ))}
          </span>
        ))}
      </div>
    </div>
  );
}

function StandingsLine({
  row,
  compact,
  topEightLine,
  href,
  onOpen,
  onHover,
  onLeave,
}: {
  row: StandingsRow;
  compact: boolean;
  topEightLine: boolean;
  href?: string;
  onOpen?: (player: FieldPlayer) => void;
  onHover: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave: () => void;
}) {
  const { player, rank, movement, record } = row;
  const className = cn(
    "w-full grid items-center gap-x-3 px-3 py-1.5 border-0 border-t border-border bg-surface text-left",
    "no-underline text-text hover:bg-surface2 transition-colors text-[14px] cursor-pointer",
    standingsColumns(compact),
    topEightLine && "border-b-2 border-b-green/60",
  );
  const hoverProps = {
    onMouseEnter: (event: MouseEvent<HTMLElement>) => onHover(player, event.currentTarget),
    onMouseLeave: onLeave,
  };
  const content = (
    <>
      <span className="text-right font-num font-semibold text-text">{rank}</span>
      <Movement movement={movement} />
      <span className="flex items-center gap-2.5 min-w-0">
        <span className="w-7 h-7 shrink-0 overflow-hidden bg-surface2">
          <PlayerPortrait player={player} initialsSize={11} />
        </span>
        <span className="w-[18px] shrink-0 flex">
          <CountryFlag code={player.countryCode} width={18} />
        </span>
        <span className="flex flex-col min-w-0">
          <span className="truncate text-text font-semibold">{fullName(player)}</span>
          {compact && player.deck ? <span className="truncate text-[12px] text-subtle">{player.deck}</span> : null}
        </span>
      </span>
      {compact ? (
        <span className="text-right font-num text-text">{formatRecord(record)}</span>
      ) : (
        <>
          <span className="truncate text-subtle">{player.deck}</span>
          <span className="text-center font-num text-text">{record.wins}</span>
          <span className="text-center font-num text-text">{record.losses}</span>
          <span className="text-center font-num text-text">{record.draws}</span>
        </>
      )}
    </>
  );
  if (href) {
    return (
      <Link to={href} state={{ fromList: true }} className={className} {...hoverProps}>
        {content}
      </Link>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onOpen?.(player)}
      onContextMenu={(event) => {
        event.preventDefault();
        onOpen?.(player);
      }}
      className={className}
      {...hoverProps}
    >
      {content}
    </button>
  );
}

function Movement({ movement }: { movement: number | null }) {
  if (!movement) {
    return <span />;
  }
  const up = movement > 0;
  return (
    <span className={cn("flex items-center gap-0.5 font-num text-[12px]", up ? "text-green" : "text-red")}>
      {up ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
      {Math.abs(movement)}
    </span>
  );
}

function roundHref(searchParams: URLSearchParams, round: number): string {
  const params = new URLSearchParams(searchParams);
  params.set("round", String(round));
  params.delete("player");
  return `?${params}`;
}

function roundRange(first: number, last: number): number[] {
  const rounds = [];
  for (let round = first; round <= last; round += 1) {
    rounds.push(round);
  }
  return rounds;
}
