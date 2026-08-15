import { Link, useNavigate } from "react-router-dom";

import { AAvatar, AVATAR_CLIP } from "../Brand";
import { LuScrollText, TbCards } from "../Icons";
import { Pips } from "../ManaPips";
import { Record } from "../Record";
import { Tooltip } from "../Tooltip";
import { cn } from "../../lib/utils";
import { orderedDeckColors, podDiscordName } from "../../data/utils";
import type { PodEventParticipantRow } from "../../types/leaderboard";

export const STANDING_COLS_CLASS =
  "[grid-template-columns:30px_1fr_70px_50px_38px] " +
  "lg:[grid-template-columns:44px_1fr_80px_70px_150px]";

// Team rows carry no rank, so their first column only indents them under the team heading
export const TEAM_STANDING_COLS_CLASS =
  "[grid-template-columns:16px_1fr_70px_50px_38px] " +
  "lg:[grid-template-columns:16px_1fr_80px_70px_150px]";

export const STANDING_ROW_PAD_X = "pl-3 pr-3 lg:pr-5";

export const STANDING_ROW_PAD = `py-2.5 ${STANDING_ROW_PAD_X}`;

// The pods index expands a whole field inline, so its rows run tighter than a pod page's
export const COMPACT_STANDING_COLS_CLASS =
  "[grid-template-columns:24px_1fr_66px_46px_34px] " +
  "lg:[grid-template-columns:34px_1fr_74px_62px_40px]";

export const TEAM_TONE = {
  A: { bg: "bg-[#4ade80]", text: "text-[#4ade80]" },
  B: { bg: "bg-[#5aa9e6]", text: "text-[#5aa9e6]" },
} as const;

export function recordParts(record: string | null): { wins: number; losses: number; played: boolean } {
  const wins = Number((record ?? "").split("-")[0] || 0);
  const losses = Number((record ?? "").split("-")[1] || 0);
  return { wins, losses, played: record != null && wins + losses > 0 };
}

export function PodStandingRow({
  p,
  rank,
  cols = STANDING_COLS_CLASS,
  compact = false,
  teamSide = null,
  selected = false,
  nameHref,
  logHref,
  onShowDeck,
  onRowClick,
  onHover,
}: {
  p: PodEventParticipantRow;
  rank: number | null;
  cols?: string;
  compact?: boolean;
  teamSide?: "A" | "B" | null;
  selected?: boolean;
  nameHref?: string | null;
  logHref?: string | null;
  onShowDeck?: () => void;
  onRowClick?: () => void;
  onHover?: (hovering: boolean) => void;
}) {
  const navigate = useNavigate();
  const avatarSize = compact ? 26 : 28;
  const { wins, losses, played } = recordParts(p.record);
  const name = podDiscordName(p);
  const hasDeck = !!onShowDeck;
  const draftLog = !hasDeck ? (logHref ?? null) : null;
  const interactive = !!onRowClick || hasDeck || !!draftLog;
  const handleRowClick = () => {
    if (onRowClick) onRowClick();
    else if (onShowDeck) onShowDeck();
    else if (draftLog) navigate(draftLog);
  };
  return (
    <div
      onClick={interactive ? handleRowClick : undefined}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      className={cn(
        "group/row grid items-center gap-x-2 lg:gap-x-3 transition-colors",
        compact ? `py-[7px] ${STANDING_ROW_PAD_X}` : STANDING_ROW_PAD,
        cols,
        selected ? "bg-green/10" : "bg-surface",
        interactive && "cursor-pointer hover:bg-surface2",
      )}
    >
      <span className={cn("mono text-center tabular-nums text-muted", compact ? "text-[12px]" : "text-[14px]")}>
        {rank ?? ""}
      </span>
      {nameHref ? (
        <Tooltip label={`View ${name}'s Profile`} side="top" align="start" delayDuration={0}>
          <Link
            to={nameHref}
            onClick={(e) => e.stopPropagation()}
            className="group/name peer/name flex items-center gap-2 lg:gap-2.5 min-w-0 max-w-full justify-self-start w-fit no-underline text-text hover:text-green transition-colors"
          >
            <SeatAvatar name={name} avatarUrl={p.avatarUrl} size={avatarSize} teamSide={teamSide} />
            <PlayerName name={name} compact={compact} />
          </Link>
        </Tooltip>
      ) : (
        <div className="flex items-center gap-2 lg:gap-2.5 min-w-0">
          <SeatAvatar name={name} avatarUrl={p.avatarUrl} size={avatarSize} teamSide={teamSide} />
          <PlayerName name={name} compact={compact} />
        </div>
      )}
      <div className="flex items-center">
        {p.deckColors ? (
          <Pips colors={orderedDeckColors(p.deckColors)} size={deckPipSize(p.deckColors, compact ? 13 : 14)} />
        ) : (
          <span className="text-dim text-[12px]">—</span>
        )}
      </div>
      {played ? (
        <Record
          className={cn("mono text-center", compact ? "text-[13px]" : "text-[13px]")}
          wins={wins}
          losses={losses}
        />
      ) : (
        <span className={cn("mono text-center text-dim", compact ? "text-[13px]" : "text-[13px]")}>—</span>
      )}
      {hasDeck ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onShowDeck?.();
          }}
          className={ACTION_CLASS}
          style={{ height: compact ? 30 : 34 }}
        >
          {!compact && <ActionLabel>VIEW DECK</ActionLabel>}
          <TbCards size={compact ? 16 : 17} aria-hidden="true" className="transition-colors" />
        </button>
      ) : draftLog ? (
        <Link
          to={draftLog}
          onClick={(e) => e.stopPropagation()}
          className={cn(ACTION_CLASS, "no-underline")}
          style={{ height: compact ? 30 : 34 }}
        >
          {!compact && <ActionLabel>DRAFT LOG</ActionLabel>}
          <LuScrollText size={compact ? 15 : 16} aria-hidden="true" className="transition-colors" />
        </Link>
      ) : (
        <span />
      )}
    </div>
  );
}

// Absolute ring, and an opaque backdrop so a transparent PNG cannot let it through as a fill
export function SeatAvatar({
  name,
  avatarUrl,
  size,
  teamSide,
}: {
  name: string;
  avatarUrl: string | null;
  size: number;
  teamSide: "A" | "B" | null;
}) {
  return (
    <span className="relative isolate shrink-0 flex">
      {teamSide && (
        <span
          aria-hidden="true"
          className={cn(
            "absolute -inset-[2px] -z-10",
            TEAM_TONE[teamSide].bg,
          )}
          style={{ clipPath: AVATAR_CLIP }}
        />
      )}
      <span className="block bg-surface2" style={{ clipPath: AVATAR_CLIP }}>
        <AAvatar displayName={name} avatarUrl={avatarUrl} size={size} />
      </span>
    </span>
  );
}

const ACTION_CLASS =
  "group/action inline-flex items-center justify-center gap-2 px-1.5 lg:px-3 whitespace-nowrap transition-colors " +
  "bg-bg border border-border text-text hover:border-green/60 hover:bg-green/10 hover:text-green " +
  "group-hover/row:border-green/60 group-hover/row:bg-green/10 group-hover/row:text-green " +
  "peer-hover/name:!border-border peer-hover/name:!bg-bg peer-hover/name:!text-text cursor-pointer";

function ActionLabel({ children }: { children: string }) {
  return (
    <span
      className="hidden lg:inline font-display tracking-[0.16em] transition-colors leading-none"
      style={{ fontSize: 14 }}
    >
      {children}
    </span>
  );
}

// The colour cell is a fixed grid track, so a four or five colour deck steps its pips down to fit
// rather than run into the record beside it
export function deckPipSize(colors: string, base: number): number {
  if (colors.length <= 3) return base;
  if (colors.length === 4) return base - 2;
  if (colors.length === 5) return base - 3;
  return base - 4;
}

function PlayerName({ name, compact = false }: { name: string; compact?: boolean }) {
  return (
    <span
      className="font-display leading-none tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis"
      style={{ fontSize: compact ? 15 : 16 }}
    >
      {name.toUpperCase()}
    </span>
  );
}

export function PodStandingRowSkeleton({
  cols = STANDING_COLS_CLASS,
  compact = false,
}: {
  cols?: string;
  compact?: boolean;
}) {
  const avatar = compact ? 26 : 28;
  return (
    <div
      className={cn(
        "grid items-center gap-x-2 lg:gap-x-3 bg-surface",
        compact ? `py-[7px] ${STANDING_ROW_PAD_X}` : STANDING_ROW_PAD,
        cols,
      )}
    >
      <div className="h-3 w-3 bg-surface2 animate-pulse mx-auto" />
      <div className="flex items-center gap-2 lg:gap-2.5">
        <div className="bg-surface2 shrink-0" style={{ width: avatar, height: avatar }} />
        <div className="h-3.5 w-32 bg-surface2 animate-pulse" />
      </div>
      <div className="h-3.5 w-14 bg-surface2 animate-pulse" />
      <div className="h-3.5 w-10 bg-surface2 animate-pulse mx-auto" />
      <div className="w-full bg-surface2 animate-pulse" style={{ height: compact ? 30 : 34 }} />
    </div>
  );
}
