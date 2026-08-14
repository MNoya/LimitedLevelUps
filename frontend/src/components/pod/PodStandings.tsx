import type { ReactNode } from "react";

import { Trophy } from "../Brand";
import { ChevronLeft } from "../Icons";
import { cn } from "../../lib/utils";
import { podDiscordName } from "../../data/utils";
import {
  PodStandingRow,
  PodStandingRowSkeleton,
  recordParts,
  STANDING_COLS_CLASS,
  STANDING_ROW_PAD_X,
  TEAM_STANDING_COLS_CLASS,
} from "./PodStandingRow";
import type { PodEventParticipantRow, PodSeat } from "../../types/leaderboard";

export { recordParts } from "./PodStandingRow";

/** Placement order, falling back to match wins for a field the bot never placed */
export function compareStandings(a: PodEventParticipantRow, b: PodEventParticipantRow): number {
  const aPlacement = a.placement ?? Number.MAX_SAFE_INTEGER;
  const bPlacement = b.placement ?? Number.MAX_SAFE_INTEGER;
  if (aPlacement !== bPlacement) return aPlacement - bPlacement;
  const aWins = recordParts(a.record).wins;
  const bWins = recordParts(b.record).wins;
  if (aWins !== bWins) return bWins - aWins;
  return podDiscordName(a).localeCompare(podDiscordName(b));
}

export function hasStandings(seats: PodSeat[]): boolean {
  return seats.some((s) => s.placement != null || recordParts(s.record).played);
}

export interface PodStandingsActions {
  eventSlug: string;
  hasDraftLog: boolean;
  canViewSeat: (avatarUrl: string | null | undefined) => boolean;
  onShowDeck: (seat: PodSeat) => void;
}

export function PodStandings({
  seats,
  teamDraft = false,
  finalized,
  selectedSeat,
  onSelect,
  onHover,
  actions,
}: {
  seats: PodSeat[];
  teamDraft?: boolean;
  finalized: boolean;
  selectedSeat: number | null;
  onSelect: (seat: number) => void;
  onHover?: (seat: number | null) => void;
  actions: PodStandingsActions;
}) {
  const row = (seat: PodSeat, rank: number | null, cols?: string) => {
    const viewable = actions.canViewSeat(seat.avatarUrl);
    const hasDeck = viewable && (!!seat.deckScreenshotUrl || !!seat.hasDeckList);
    return (
      <PodStandingRow
        key={seat.seatIndex}
        p={seat}
        rank={rank}
        cols={cols}
        selected={seat.seatIndex === selectedSeat}
        logHref={
          actions.hasDraftLog && viewable
            ? `/pods/${actions.eventSlug}/${seat.playerSlug ?? seat.seatIndex}`
            : null
        }
        onShowDeck={hasDeck ? () => actions.onShowDeck(seat) : undefined}
        onRowClick={() => onSelect(seat.seatIndex)}
        onHover={(hovering) => onHover?.(hovering ? seat.seatIndex : null)}
      />
    );
  };

  if (teamDraft) {
    return (
      <div className="flex flex-col">
        <StandingsHeading finalized={finalized} cols={TEAM_STANDING_COLS_CLASS} />
        <div className="flex flex-col gap-[1px] pb-[1px] bg-bg">
          {teamSides(seats).map(({ team, members, wins, won }) => (
            <div key={team} className="flex flex-col gap-[1px]">
              <TeamHeading team={team} wins={wins} won={won} />
              {members.map((seat) => row(seat, null, TEAM_STANDING_COLS_CLASS))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  const ranked = [...seats].sort(compareStandings);
  return (
    <div className="flex flex-col">
      <StandingsHeading finalized={finalized} />
      <div className="flex flex-col gap-[1px] pb-[1px] bg-bg">
        {ranked.map((seat, index) => row(seat, seat.placement ?? index + 1))}
      </div>
    </div>
  );
}

export function PodStandingsSkeleton({
  rows = 8,
  finalized = true,
  teamDraft = false,
}: {
  rows?: number;
  finalized?: boolean;
  teamDraft?: boolean;
}) {
  const cols = teamDraft ? TEAM_STANDING_COLS_CLASS : STANDING_COLS_CLASS;
  return (
    <div className="flex flex-col">
      <StandingsHeading finalized={finalized} cols={cols} />
      <div className="flex flex-col gap-[1px] pb-[1px] bg-bg">
        {Array.from({ length: rows }, (_, i) => (
          <PodStandingRowSkeleton key={i} cols={cols} />
        ))}
      </div>
    </div>
  );
}

const BAR_HEIGHT = 40;
const BAR_CHROME = "shrink-0 bg-surface2 border-b border-border";
const BAR_LABEL = "font-display tracking-[0.14em] leading-none";
const BAR_LABEL_SIZE = 16;
const CHEVRON_SLOT = 22;
const CHEVRON_INSET = "pl-[22px]";

export function StandingsBackBar({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        BAR_CHROME,
        STANDING_ROW_PAD_X,
        "flex items-center w-full text-left text-muted hover:text-text transition-colors cursor-pointer",
      )}
      style={{ height: BAR_HEIGHT }}
    >
      <ChevronLeft size={16} className="shrink-0" />
      <span className={cn(BAR_LABEL, "ml-1.5")} style={{ fontSize: BAR_LABEL_SIZE }}>
        BACK TO STANDINGS
      </span>
    </button>
  );
}

function StandingsHeading({ finalized, cols = STANDING_COLS_CLASS }: { finalized: boolean; cols?: string }) {
  return (
    <div
      className={cn("grid items-center gap-x-2 lg:gap-x-3", BAR_CHROME, STANDING_ROW_PAD_X, cols)}
      style={{ height: BAR_HEIGHT }}
    >
      <span
        className={cn("col-span-2 text-text", BAR_LABEL, CHEVRON_INSET)}
        style={{ fontSize: BAR_LABEL_SIZE }}
      >
        {finalized ? "FINAL STANDINGS" : "STANDINGS"}
      </span>
      <HeadingLabel>COLORS</HeadingLabel>
      <HeadingLabel className="text-center">RESULT</HeadingLabel>
      <span />
    </div>
  );
}

function HeadingLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn("font-display text-muted tracking-[0.16em] leading-none whitespace-nowrap", className)}
      style={{ fontSize: 12 }}
    >
      {children}
    </span>
  );
}

interface TeamSide {
  team: string;
  members: PodSeat[];
  wins: number;
  won: boolean;
}

/** Green/Blue sides by draft-seat parity, the same split Draftmancer's team mode seats */
function teamSides(seats: PodSeat[]): TeamSide[] {
  const sides = ["A", "B"].map((team) => {
    const members = seats
      .filter((s) => (s.seatIndex % 2 === 0 ? "A" : "B") === team)
      .sort(compareStandings);
    const wins = members.reduce((sum, s) => sum + recordParts(s.record).wins, 0);
    return { team, members, wins, won: false };
  });
  const [a, b] = sides;
  return sides.map((side) => ({ ...side, won: a.wins !== b.wins && side.wins === Math.max(a.wins, b.wins) }));
}

function TeamHeading({ team, wins, won }: { team: string; wins: number; won: boolean }) {
  const tone = team === "A" ? "text-green" : "text-blue";
  return (
    <div
      className={cn(
        "grid items-center gap-x-2 lg:gap-x-3 bg-surface2/60",
        STANDING_ROW_PAD_X,
        TEAM_STANDING_COLS_CLASS,
      )}
      style={{ height: BAR_HEIGHT }}
    >
      <span className={cn("col-span-2 flex items-center text-[15px]", BAR_LABEL, tone)}>
        <span className="inline-flex justify-center shrink-0" style={{ width: CHEVRON_SLOT }}>
          {won && <Trophy size={14} color="#ffc63a" />}
        </span>
        {team === "A" ? "GREEN TEAM" : "BLUE TEAM"}
        <span className="mono text-[14px] ml-2.5">{wins}</span>
      </span>
      <span />
      <span />
      <span />
    </div>
  );
}
