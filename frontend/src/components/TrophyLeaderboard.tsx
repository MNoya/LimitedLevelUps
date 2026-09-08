import React from "react";
import { Link } from "react-router-dom";
import { AAvatar, Trophy } from "./Brand";
import { Pips } from "./ManaPips";
import { playerPath } from "../data/utils";
import { cn } from "../lib/utils";
import type { TrophyLeaderboardRow } from "../types/leaderboard";

// Standalone board for MTGO flashback sets: ranked purely by self-reported trophy count, with no
// scored columns. The scored LeaderboardTable can't back this — those sets have no 17lands data.

const COLS = "44px 1fr auto";
const MAX_DECK_PIPS = 8;

export function TrophyLeaderboard({
  rows,
  loading = false,
}: {
  rows: TrophyLeaderboardRow[] | undefined;
  loading?: boolean;
}) {
  if (loading) return <LoadingRows />;
  if (!rows || rows.length === 0) return <EmptyState />;

  return (
    <div>
      <div
        className="grid gap-x-3 py-2.5 pl-2 pr-5 mb-1 font-display text-[11px] tracking-[0.2em] text-muted"
        style={{ gridTemplateColumns: COLS }}
      >
        <span className="text-center">RANK</span>
        <span>PLAYER</span>
        <span className="text-right">TROPHIES</span>
      </div>
      <div className="flex flex-col gap-[1px]">
        {rows.map((r) => (
          <Link
            key={r.slug}
            to={playerPath(r.slug, r.setCode)}
            className="group/row grid items-center gap-x-3 py-2.5 pl-2 pr-5 bg-surface hover:bg-surface2 transition-colors no-underline text-inherit"
            style={{ gridTemplateColumns: COLS }}
          >
            <span className="font-num text-[13px] text-muted text-center">{r.rank}</span>
            <div className="flex items-center gap-2.5 min-w-0">
              <AAvatar displayName={r.displayName} avatarUrl={r.avatarUrl} size={30} />
              <div className="min-w-0">
                <div className="font-display text-[18px] leading-none tracking-[0.04em] whitespace-nowrap overflow-hidden text-ellipsis transition-colors group-hover/row:text-green">
                  {r.displayName.toUpperCase()}
                </div>
                <DeckPips decks={r.decks.filter((d) => d.isTrophy)} />
              </div>
            </div>
            <div className="text-right flex items-center justify-end gap-1.5">
              <Trophy size={18} color="#ffc63a" />
              <span className="font-display tracking-[0.02em] tabular-nums leading-none text-[18px]">
                {r.trophies}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function DeckPips({ decks }: { decks: TrophyLeaderboardRow["decks"] }) {
  if (decks.length === 0) return null;
  return (
    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
      {decks.slice(0, MAX_DECK_PIPS).map((d, i) => (
        <Pips key={`${d.sourceMessageId}-${i}`} colors={d.colors} size={12} />
      ))}
      {decks.length > MAX_DECK_PIPS && (
        <span className="font-num text-[11px] text-dim">+{decks.length - MAX_DECK_PIPS}</span>
      )}
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="py-3 px-3.5">
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="grid gap-2.5 py-2.5 border-b border-border items-center"
          style={{ gridTemplateColumns: "32px 1fr 60px" }}
        >
          <div className="h-8 bg-surface2" />
          <div className="h-3.5 bg-surface2 animate-pulse" style={{ width: `${50 + i * 8}%` }} />
          <div className="h-3.5 bg-surface2" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="p-10 text-center">
      <div className="font-display text-[22px] tracking-[0.04em] text-text">NO TROPHIES YET</div>
      <div className="font-mono text-[11px] text-muted mt-2">
        NO TROPHIES LOGGED FOR THIS SET YET. LOG ONE WITH /trophy IN DISCORD.
      </div>
    </div>
  );
}
