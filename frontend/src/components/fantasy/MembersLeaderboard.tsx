import { useMemo, useState, type MouseEvent } from "react";
import { ChevronDown, Trophy } from "lucide-react";
import { cn } from "../../lib/utils";
import { MEDAL_COLOR } from "../p0p1/P0P1BallotScorecard";
import { SelfBadge } from "../p0p1/FinalResults";
import { PlayerPortrait, SLOTS, fullName, shortLastName, slotFor, type FieldPlayer } from "./fantasyField";
import { dayPoints, slotDayPoints, type MemberStanding, type SlotBreakdown, type StandingsDay } from "./fantasyMembers";
import {
  BRACKET_MATCHES,
  correctCalls,
  pickedWinner,
  type BracketPicks,
  type BracketResults,
} from "./fantasyTop8";

type LeaderboardProps = {
  rows: MemberStanding[];
  days: StandingsDay[];
  results: BracketResults | null;
  seeded: FieldPlayer[];
  compact: boolean;
  onInspect?: (player: FieldPlayer) => void;
  onHover?: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave?: () => void;
};

type PlayerHandlers = Pick<LeaderboardProps, "onInspect" | "onHover" | "onLeave">;

const DAY_LABEL: Record<StandingsDay, string> = {
  overall: "Overall",
  day1: "Day 1",
  day2: "Day 2",
  top8: "Top 8",
};

export function MembersLeaderboard(props: LeaderboardProps) {
  const { rows, days, results, compact, onInspect, onHover, onLeave } = props;
  const handlers = { onInspect, onHover, onLeave };
  const [day, setDay] = useState<StandingsDay>("overall");
  const ranked = useMemo(() => rankForDay(rows, day), [rows, day]);
  const showPodium = Boolean(results?.final);
  const selfRow = rows.find((row) => row.member.isSelf) ?? null;

  return (
    <div className="flex flex-col gap-4">
      {showPodium ? <Podium rows={rows.slice(0, 3)} self={selfRow} compact={compact} handlers={handlers} /> : null}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          {days.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setDay(option)}
              className={cn(
                "px-2 py-1 border text-[13px] whitespace-nowrap cursor-pointer transition-colors",
                day === option ? "border-green/60 bg-green/10 text-text" : "border-border2 bg-surface text-subtle hover:text-text",
              )}
            >
              {DAY_LABEL[option]}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-col border border-border2">
        {!compact ? <HeaderRow showBracket={Boolean(results)} /> : null}
        {ranked.map((entry) => (
          <MemberRow key={entry.row.member.name} entry={entry} day={day} {...props} />
        ))}
      </div>
    </div>
  );
}

export function LeaderboardSkeleton({ compact, rows }: { compact: boolean; rows: number }) {
  const nameWidths = [96, 72, 120, 84, 104, 64, 112, 90];
  return (
    <div className="flex flex-col border border-border2">
      {!compact ? <HeaderRow showBracket={false} /> : null}
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className={cn(
            "flex items-center gap-3 px-3 py-2 border-b border-border last:border-b-0",
            compact && "flex-wrap",
          )}
        >
          <span className="w-8 shrink-0 text-right font-display text-[17px] tracking-[0.06em] text-subtle">
            {index + 1}
          </span>
          <span className={cn("flex items-center gap-2", compact ? "flex-1" : "w-[176px] shrink-0")}>
            <span className="w-6 h-6 shrink-0 rounded-full bg-surface2" />
            <span className="h-3 bg-surface2" style={{ width: nameWidths[index % nameWidths.length] }} />
          </span>
          <span className={cn("flex items-center gap-1.5", compact ? "w-full pl-11" : "flex-1")}>
            {SLOTS.map((slot) => (
              <span
                key={slot.key}
                className="flex-1 h-7 border bg-surface"
                style={{ borderColor: `${slot.accent}40` }}
              />
            ))}
          </span>
          {!compact ? (
            <span className="w-[56px] shrink-0 flex justify-end">
              <span className="w-6 h-3 bg-surface2" />
            </span>
          ) : null}
          {!compact ? <span className="w-[14px]" /> : null}
        </div>
      ))}
    </div>
  );
}

function HeaderRow({ showBracket }: { showBracket: boolean }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 border-b border-border2 bg-surface font-display text-[13px] tracking-[0.12em] text-subtle">
      <span className="w-8 text-right">#</span>
      <span className="w-[176px]">MEMBER</span>
      <span className="flex-1">LINEUP</span>
      {showBracket ? <span className="w-[64px] text-right">TOP 8</span> : null}
      <span className="w-[56px] text-right">PTS</span>
      <span className="w-[14px]" />
    </div>
  );
}

function MemberRow({
  entry,
  day,
  results,
  seeded,
  compact,
  onInspect,
  onHover,
  onLeave,
}: LeaderboardProps & { entry: RankedEntry; day: StandingsDay }) {
  const [open, setOpen] = useState(false);
  const { row, rank } = entry;
  const isSelf = row.member.isSelf;
  const medal = rank <= 3 && day === "overall" && results?.final ? MEDAL_COLOR[rank as 1 | 2 | 3] : null;
  const accent = isSelf ? "#2ee85c" : medal;
  return (
    <div
      className={cn("border-b border-border last:border-b-0", isSelf && "bg-green/[0.07]")}
      style={accent ? { boxShadow: `inset 3px 0 0 ${accent}` } : undefined}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "w-full flex items-center gap-3 px-3 text-left bg-transparent border-0 cursor-pointer hover:bg-surface/60",
          compact ? "py-2 flex-wrap" : "py-2",
        )}
      >
        <span
          className="w-8 shrink-0 text-right font-display text-[17px] tracking-[0.06em] text-text"
          style={medal ? { color: medal } : undefined}
        >
          {rank}
        </span>
        <span className={cn("flex items-center gap-2 min-w-0", compact ? "flex-1" : "w-[176px] shrink-0")}>
          <MemberAvatar name={row.member.name} isSelf={isSelf} />
          <span className={cn("truncate text-[14px]", isSelf ? "font-semibold text-white" : "text-text")}>
            {row.member.name}
          </span>
        </span>
        {compact ? <RowPoints points={dayPoints(row, day)} bracketPoints={row.bracketPoints} medal={medal} /> : null}
        <span className={cn("flex items-center gap-1.5 min-w-0", compact ? "w-full pl-11" : "flex-1")}>
          {row.slots.map((slot) => (
            <PickChip
              key={slot.slot}
              slot={slot}
              day={day}
              compact={compact}
              onInspect={onInspect}
              onHover={onHover}
              onLeave={onLeave}
            />
          ))}
        </span>
        {!compact && results ? (
          <span className="w-[64px] shrink-0 text-right font-num text-[14px] text-subtle">{row.bracketPoints ?? ""}</span>
        ) : null}
        {!compact ? (
          <span
            className={cn("w-[56px] shrink-0 text-right font-num tabular-nums text-[14px]", pointsClass(medal))}
            style={medal ? { color: medal } : undefined}
          >
            {dayPoints(row, day)}
          </span>
        ) : null}
        {!compact ? (
          <ChevronDown size={14} className={cn("shrink-0 text-subtle transition-transform", open && "rotate-180")} />
        ) : null}
      </button>
      {open ? <MemberReview row={row} results={results} seeded={seeded} compact={compact} /> : null}
    </div>
  );
}

function RowPoints({
  points,
  bracketPoints,
  medal,
}: {
  points: number;
  bracketPoints: number | null;
  medal: string | null;
}) {
  return (
    <span className="flex items-baseline gap-2 shrink-0">
      {bracketPoints !== null ? <span className="font-num text-[12px] text-subtle">{bracketPoints} Top 8</span> : null}
      <span
        className={cn("font-num tabular-nums text-[14px]", pointsClass(medal))}
        style={medal ? { color: medal } : undefined}
      >
        {points}
      </span>
    </span>
  );
}

function pointsClass(medal: string | null): string {
  return medal ? "font-semibold" : "text-subtle";
}

function PickChip({
  slot,
  day,
  compact,
  onInspect,
  onHover,
  onLeave,
}: PlayerHandlers & {
  slot: SlotBreakdown;
  day: StandingsDay;
  compact: boolean;
}) {
  const accent = slotFor(slot.slot).accent;
  const player = day === "day1" ? slot.dayOne : slot.current;
  const replaced = fullName(slot.dayOne) !== fullName(slot.current);
  return (
    <span
      onMouseEnter={(event) => onHover?.(player, event.currentTarget)}
      onMouseLeave={onLeave}
      onContextMenu={inspectOnRightClick(player, onInspect)}
      className="flex-1 min-w-0 flex items-center gap-1.5 bg-surface"
      style={{ boxShadow: `inset 0 0 0 1px ${accent}66` }}
    >
      <span className="relative w-7 h-7 shrink-0 overflow-hidden">
        <PlayerPortrait player={player} initialsSize={11} />
      </span>
      {!compact ? <span className="flex-1 min-w-0 truncate text-[13px] text-text">{shortLastName(player)}</span> : null}
      {replaced && day !== "day1" && !compact ? (
        <span className="font-display text-[12px] tracking-[0.06em]" style={{ color: accent }}>
          SUB
        </span>
      ) : null}
      <span className={cn("pr-1.5 font-num text-[13px] font-semibold text-text", compact && "flex-1 text-right")}>
        {slotDayPoints(slot, day)}
      </span>
    </span>
  );
}

function MemberReview({
  row,
  results,
  seeded,
  compact,
}: {
  row: MemberStanding;
  results: BracketResults | null;
  seeded: FieldPlayer[];
  compact: boolean;
}) {
  return (
    <div className="px-3 pb-3 pt-1">
      <div className={cn("grid gap-2", compact ? "grid-cols-1" : results ? "grid-cols-5" : "grid-cols-4")}>
        {row.slots.map((slot) => (
          <SlotReview key={slot.slot} slot={slot} />
        ))}
        {results ? <BracketReview row={row} results={results} seeded={seeded} /> : null}
      </div>
    </div>
  );
}

function BracketReview({
  row,
  results,
  seeded,
}: {
  row: MemberStanding;
  results: BracketResults;
  seeded: FieldPlayer[];
}) {
  const champion = pickedWinner(row.member.bracket, "final", seeded);
  const finalWinner = results.final?.winner;
  const championRight = champion !== undefined && finalWinner !== undefined && fullName(champion) === fullName(finalWinner);
  const calls = correctCalls(row.member.bracket, results);
  return (
    <div className="flex flex-col gap-1.5 p-2 bg-surface" style={{ boxShadow: `inset 0 0 0 1px ${MEDAL_COLOR[1]}55` }}>
      <span className="font-display text-[13px] tracking-[0.12em]" style={{ color: MEDAL_COLOR[1] }}>
        TOP 8
      </span>
      <BracketLine label="Correct Picks" value={`${calls.right} of ${calls.decided}`} />
      <BracketLine label="Exact Results" value={String(exactGames(row.member.bracket, results))} />
      <div className="flex items-center gap-2 text-[13px]">
        <Trophy size={13} className="shrink-0 text-gold" />
        <span className={cn("flex-1 min-w-0 truncate", championRight ? "text-green" : "text-text")}>
          {champion ? fullName(champion) : "No champion pick"}
        </span>
      </div>
      <div className="flex items-baseline justify-between border-t border-border pt-1 text-[13px]">
        <span className="text-subtle">Total</span>
        <span className="font-num font-semibold text-green">{row.bracketPoints}</span>
      </div>
    </div>
  );
}

function BracketLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 text-[13px]">
      <span className="text-subtle">{label}</span>
      <span className="font-num text-text">{value}</span>
    </div>
  );
}

function exactGames(picks: BracketPicks, results: BracketResults): number {
  let count = 0;
  for (const match of BRACKET_MATCHES) {
    const pick = picks[match.key];
    const result = results[match.key];
    if (result && pick?.winner === fullName(result.winner) && pick.games === result.games) {
      count += 1;
    }
  }
  return count;
}

function SlotReview({ slot }: { slot: SlotBreakdown }) {
  const accent = slotFor(slot.slot).accent;
  const replaced = fullName(slot.dayOne) !== fullName(slot.current);
  return (
    <div className="flex flex-col gap-1.5 p-2 bg-surface" style={{ boxShadow: `inset 0 0 0 1px ${accent}55` }}>
      <span className="font-display text-[13px] tracking-[0.12em]" style={{ color: accent }}>
        {slotFor(slot.slot).label.toUpperCase()}
      </span>
      <ReviewLine label="Day 1" player={slot.dayOne} points={slot.day1} />
      <ReviewLine label="Day 2" player={slot.current} points={slot.day2} faded={!replaced} />
      <ReviewLine label="Top 8" player={slot.current} points={slot.top8} faded />
      <div className="flex items-baseline justify-between border-t border-border pt-1 text-[13px]">
        <span className="text-subtle">Total</span>
        <span className="font-num font-semibold text-green">{slot.total}</span>
      </div>
    </div>
  );
}

function ReviewLine({
  label,
  player,
  points,
  faded = false,
}: {
  label: string;
  player: FieldPlayer;
  points: number;
  faded?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 text-[13px]">
      <span className="w-11 shrink-0 text-subtle">{label}</span>
      <span className={cn("flex-1 min-w-0 truncate", faded ? "text-subtle" : "text-text")}>{fullName(player)}</span>
      <span className="font-num text-text">{points}</span>
    </div>
  );
}

function Podium({
  rows,
  self,
  compact,
  handlers,
}: {
  rows: MemberStanding[];
  self: MemberStanding | null;
  compact: boolean;
  handlers: PlayerHandlers;
}) {
  const [champion, ...runnersUp] = rows;
  if (!champion) {
    return null;
  }
  const selfOffPodium = self && self.rank > 3 ? self : null;
  return (
    <div className="flex flex-col gap-2.5">
      <div className="relative overflow-hidden" style={{ ...PODIUM_SKEW, ...CHAMPION_FRAME }}>
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ backgroundImage: "repeating-linear-gradient(to bottom, #ffffff06 0 1px, transparent 1px 3px)" }}
        />
        <div
          className="absolute top-0 bottom-0 left-0 flex items-center justify-center"
          style={{ width: 56, background: `linear-gradient(180deg, #ffd76a, ${MEDAL_COLOR[1]} 55%, #d99e12)` }}
        >
          <span className="font-display leading-none" style={{ fontSize: 40, color: "#0a0c10", transform: UNSKEW }}>
            1
          </span>
        </div>
        <div
          className="relative flex items-center gap-3 sm:gap-4 py-3 sm:py-4"
          style={{ transform: UNSKEW, paddingLeft: 74, paddingRight: 20 }}
        >
          <MemberAvatar
            name={champion.member.name}
            isSelf={champion.member.isSelf}
            size={compact ? 40 : 56}
            ring={MEDAL_COLOR[1]}
          />
          <div className="flex-1 min-w-0">
            <div
              className={cn(
                "font-mono tracking-[0.22em] text-[10px] sm:text-[10.5px] uppercase text-gold",
                "whitespace-nowrap truncate",
              )}
            >
              🏆 CHAMPION
            </div>
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="font-display text-[24px] sm:text-[44px] leading-[0.95] tracking-[0.03em] truncate min-w-0"
              >
                {champion.member.name.toUpperCase()}
              </span>
              {champion.member.isSelf ? <SelfBadge /> : null}
            </div>
          </div>
          {compact ? (
            <div className="text-right shrink-0 pl-3">
              <div
                className="font-num tabular-nums font-bold leading-[1.05] text-gold text-[22px]"
                style={{ textShadow: "0 0 34px #ffc63a90" }}
              >
                {champion.total}
              </div>
              <div className="font-display text-gold/80 tracking-[0.14em] text-[11px]">POINTS</div>
            </div>
          ) : (
            <ChampionScoreboard row={champion} handlers={handlers} />
          )}
        </div>
      </div>

      {compact ? (
        <div className="flex justify-center">
          <LineupStrip row={champion} size={40} handlers={handlers} />
        </div>
      ) : null}

      <div className="flex flex-col gap-1.5 mt-1">
        {runnersUp.map((row, index) => (
          <PodiumBar
            key={row.member.name}
            row={row}
            accent={MEDAL_COLOR[(index + 2) as 2 | 3]}
            compact={compact}
            handlers={handlers}
          />
        ))}
        {selfOffPodium ? (
          <PodiumBar row={selfOffPodium} accent="#2ee85c" compact={compact} handlers={handlers} />
        ) : null}
      </div>
    </div>
  );
}

function PodiumBar({
  row,
  accent,
  compact,
  handlers,
}: {
  row: MemberStanding;
  accent: string;
  compact: boolean;
  handlers: PlayerHandlers;
}) {
  return (
    <div
      className="relative flex items-stretch overflow-hidden"
      style={{ ...PODIUM_SKEW, background: "#1d2330", border: "1px solid #3b4458", borderLeft: 0 }}
    >
      <div
        className="flex items-center justify-center shrink-0 px-2"
        style={{ minWidth: 40, background: `linear-gradient(180deg, ${accent}dd, ${accent} 55%, ${accent}aa)` }}
      >
        <span className="font-display text-[19px]" style={{ color: "#0a0c10", transform: UNSKEW }}>
          {row.rank}
        </span>
      </div>
      <div className="flex-1 min-w-0 flex items-center gap-3 py-1.5 px-4" style={{ transform: UNSKEW }}>
        <MemberAvatar name={row.member.name} isSelf={row.member.isSelf} size={28} ring={accent} />
        <span className="flex items-center gap-2 flex-1 min-w-0">
          <span className="font-display text-[16px] sm:text-[20px] tracking-[0.04em] truncate min-w-0">
            {row.member.name.toUpperCase()}
          </span>
          {row.member.isSelf ? <SelfBadge /> : null}
        </span>
        {compact ? null : <LineupStrip row={row} size={34} handlers={handlers} />}
        <span
          className="w-12 text-right font-num tabular-nums text-[14px] sm:text-[16px] font-bold shrink-0"
          style={{ color: accent }}
        >
          {row.total}
        </span>
      </div>
    </div>
  );
}

function ChampionScoreboard({ row, handlers }: { row: MemberStanding; handlers: PlayerHandlers }) {
  const picks = SLOTS.map((slot) => ({ slot, pick: row.slots.find((entry) => entry.slot === slot.key) }));
  return (
    <div
      className="grid items-center gap-x-2 gap-y-2 shrink-0"
      style={{ gridTemplateColumns: `repeat(${picks.length}, auto) auto` }}
    >
      {picks.map(({ slot, pick }) => (
        <span
          key={slot.key}
          className="overflow-hidden bg-surface2"
          style={{ width: 58, height: 58, boxShadow: `0 0 0 2px ${slot.accent}` }}
          onMouseEnter={(event) => (pick ? handlers.onHover?.(pick.current, event.currentTarget) : undefined)}
          onMouseLeave={handlers.onLeave}
          onContextMenu={pick ? inspectOnRightClick(pick.current, handlers.onInspect) : undefined}
        >
          {pick ? <PlayerPortrait player={pick.current} initialsSize={19} /> : null}
        </span>
      ))}
      <span className="pl-5 flex flex-col items-end" style={{ gridColumn: picks.length + 1, gridRow: "1 / span 2" }}>
        <span
          className="font-num tabular-nums font-bold leading-[1.05] text-gold text-[34px]"
          style={{ textShadow: "0 0 34px #ffc63a90" }}
        >
          {row.total}
        </span>
        <span className="font-display text-gold/80 tracking-[0.14em] text-[13px] leading-none">POINTS</span>
      </span>
      {picks.map(({ slot, pick }) => (
        <span key={slot.key} className="text-center font-num text-[13px] leading-none text-text">
          {pick?.total ?? ""}
        </span>
      ))}
    </div>
  );
}

function LineupStrip({
  row,
  size,
  handlers,
  className,
}: {
  row: MemberStanding;
  size: number;
  handlers: PlayerHandlers;
  className?: string;
}) {
  return (
    <span className={cn("flex items-end gap-2 shrink-0", className)}>
      {SLOTS.map((slot) => {
        const pick = row.slots.find((entry) => entry.slot === slot.key);
        if (!pick) {
          return null;
        }
        return (
          <span
            key={slot.key}
            className="flex flex-col items-center gap-2"
            onMouseEnter={(event) => handlers.onHover?.(pick.current, event.currentTarget)}
            onMouseLeave={handlers.onLeave}
            onContextMenu={inspectOnRightClick(pick.current, handlers.onInspect)}
          >
            <span
              className="overflow-hidden bg-surface2"
              style={{ width: size, height: size, boxShadow: `0 0 0 2px ${slot.accent}` }}
            >
              <PlayerPortrait player={pick.current} initialsSize={Math.round(size / 3)} />
            </span>
            {size >= 40 ? (
              <span className="font-num text-[13px] leading-[16px] text-text translate-y-px">{pick.total}</span>
            ) : null}
          </span>
        );
      })}
    </span>
  );
}

function inspectOnRightClick(player: FieldPlayer, onInspect?: (player: FieldPlayer) => void) {
  if (!onInspect) {
    return undefined;
  }
  return (event: MouseEvent<HTMLElement>) => {
    event.preventDefault();
    onInspect(player);
  };
}

const PODIUM_SKEW = { transform: "skewX(-6deg)", transformOrigin: "0 100%", marginRight: 12 };
const UNSKEW = "skewX(6deg)";
const CHAMPION_FRAME = {
  background: "linear-gradient(100deg, #232a3a, #1d2330 55%)",
  border: "1px solid #3b4458",
  borderLeft: 0,
  boxShadow: "0 0 34px #ffc63a22",
};

function MemberAvatar({
  name,
  isSelf,
  size = 26,
  ring,
}: {
  name: string;
  isSelf: boolean;
  size?: number;
  ring?: string;
}) {
  const hue = hueOf(name);
  return (
    <span
      className="shrink-0 rounded-full flex items-center justify-center font-display text-white"
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.46),
        background: isSelf ? "#1f8f3e" : `hsl(${hue} 35% 32%)`,
        boxShadow: ring ? `0 0 0 2px #1d2330, 0 0 0 3px ${ring}` : undefined,
      }}
    >
      {name.replace(/^\W+/, "").charAt(0).toUpperCase()}
    </span>
  );
}

type RankedEntry = { row: MemberStanding; rank: number };

function rankForDay(rows: MemberStanding[], day: StandingsDay): RankedEntry[] {
  if (day === "overall") {
    return rows.map((row) => ({ row, rank: row.rank }));
  }
  const sorted = [...rows].sort((a, b) => dayPoints(b, day) - dayPoints(a, day) || a.rank - b.rank);
  return sorted.map((row, index) => ({ row, rank: index + 1 }));
}

function hueOf(name: string): number {
  let hash = 0;
  for (const char of name) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return hash % 360;
}

