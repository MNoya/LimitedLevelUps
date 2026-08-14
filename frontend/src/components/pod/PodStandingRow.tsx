import { Link, useNavigate } from "react-router-dom";

import { AAvatar } from "../Brand";
import { LuScrollText, TbCards } from "../Icons";
import { Pips } from "../ManaPips";
import { Record } from "../Record";
import { Tooltip } from "../Tooltip";
import { cn } from "../../lib/utils";
import { podDiscordName } from "../../data/utils";
import type { PodEventParticipantRow } from "../../types/leaderboard";

export const STANDING_COLS_CLASS =
  "[grid-template-columns:30px_1fr_60px_50px_38px] " +
  "lg:[grid-template-columns:44px_1fr_80px_70px_150px]";

// Team rows carry no rank, so their first column only indents them under the team heading
export const TEAM_STANDING_COLS_CLASS =
  "[grid-template-columns:16px_1fr_60px_50px_38px] " +
  "lg:[grid-template-columns:16px_1fr_80px_70px_150px]";

export const STANDING_ROW_PAD_X = "pl-3 pr-3 lg:pr-5";

export const STANDING_ROW_PAD = `py-2.5 ${STANDING_ROW_PAD_X}`;

export function recordParts(record: string | null): { wins: number; losses: number; played: boolean } {
  const wins = Number((record ?? "").split("-")[0] || 0);
  const losses = Number((record ?? "").split("-")[1] || 0);
  return { wins, losses, played: record != null && wins + losses > 0 };
}

export function PodStandingRow({
  p,
  rank,
  cols = STANDING_COLS_CLASS,
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
  selected?: boolean;
  nameHref?: string | null;
  logHref?: string | null;
  onShowDeck?: () => void;
  onRowClick?: () => void;
  onHover?: (hovering: boolean) => void;
}) {
  const navigate = useNavigate();
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
        STANDING_ROW_PAD,
        cols,
        selected ? "bg-green/10" : "bg-surface",
        interactive && "cursor-pointer hover:bg-surface2",
      )}
    >
      <span className="mono text-[14px] text-center tabular-nums text-muted">{rank ?? ""}</span>
      {nameHref ? (
        <Tooltip label={`View ${name}'s Profile`} side="top" align="start" delayDuration={0}>
          <Link
            to={nameHref}
            onClick={(e) => e.stopPropagation()}
            className="group/name peer/name flex items-center gap-2 lg:gap-2.5 min-w-0 max-w-full justify-self-start w-fit no-underline text-text hover:text-green transition-colors"
          >
            <AAvatar displayName={name} avatarUrl={p.avatarUrl} size={28} />
            <PlayerName name={name} />
          </Link>
        </Tooltip>
      ) : (
        <div className="flex items-center gap-2 lg:gap-2.5 min-w-0">
          <AAvatar displayName={name} avatarUrl={p.avatarUrl} size={28} />
          <PlayerName name={name} />
        </div>
      )}
      <div className="flex items-center">
        {p.deckColors ? (
          <Pips colors={p.deckColors} size={14} />
        ) : (
          <span className="text-dim text-[12px]">—</span>
        )}
      </div>
      {played ? (
        <Record className="mono text-center text-[13px]" wins={wins} losses={losses} />
      ) : (
        <span className="mono text-center text-[13px] text-dim">—</span>
      )}
      {hasDeck ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onShowDeck?.();
          }}
          className={ACTION_CLASS}
          style={{ height: 34 }}
        >
          <ActionLabel>VIEW DECK</ActionLabel>
          <TbCards size={17} aria-hidden="true" className="transition-colors" />
        </button>
      ) : draftLog ? (
        <Link
          to={draftLog}
          onClick={(e) => e.stopPropagation()}
          className={cn(ACTION_CLASS, "no-underline")}
          style={{ height: 34 }}
        >
          <ActionLabel>DRAFT LOG</ActionLabel>
          <LuScrollText size={16} aria-hidden="true" className="transition-colors" />
        </Link>
      ) : (
        <span />
      )}
    </div>
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

function PlayerName({ name }: { name: string }) {
  return (
    <span
      className="font-display leading-none tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis"
      style={{ fontSize: 16 }}
    >
      {name.toUpperCase()}
    </span>
  );
}

export function PodStandingRowSkeleton({ cols = STANDING_COLS_CLASS }: { cols?: string }) {
  return (
    <div className={cn("grid items-center gap-x-2 lg:gap-x-3 bg-surface", STANDING_ROW_PAD, cols)}>
      <div className="h-3 w-3 bg-surface2 animate-pulse mx-auto" />
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 bg-surface2 shrink-0" />
        <div className="h-3.5 w-32 bg-surface2 animate-pulse" />
      </div>
      <div className="h-3.5 w-14 bg-surface2 animate-pulse" />
      <div className="h-3.5 w-10 bg-surface2 animate-pulse mx-auto" />
      <div className="h-[34px] w-full bg-surface2 animate-pulse" />
    </div>
  );
}
