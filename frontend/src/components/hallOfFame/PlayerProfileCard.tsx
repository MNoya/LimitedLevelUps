import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronDown } from "lucide-react";
import { AAvatar, Trophy } from "../Brand";
import { FitText } from "../FitText";
import { Pips } from "../ManaPips";
import { RankBadge } from "../RankBadge";
import { Record } from "../Record";
import { SectionLabel } from "../SectionLabel";
import { TrophyCount } from "../TrophyCount";
import { aggregate, BreakdownPanel } from "../player/BreakdownPanel";
import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";
import { DonutChart, type DonutEntry } from "../DonutChart";
import { comboColors, FMT_COLORS, FMT_DEFAULT_COLOR, shortFormat } from "../../data/format-display";
import { colorsDisplayName } from "../../data/filters";
import { playerPath } from "../../data/utils";
import type { LeaderboardRow } from "../../types/leaderboard";
import type { ChampionshipPlayer } from "./useChampionship";

const LEAN_DECK_ROWS = 5;
const LEAN_DONUT_SIZE = 88;

export function PlayerProfileCard(props: { player: ChampionshipPlayer; setCode: string; loading: boolean }) {
  const isMobile = useIsMobile();
  return isMobile ? <LeanPlayerCard {...props} /> : <FullPlayerCard {...props} />;
}

function FullPlayerCard({
  player,
  setCode,
  loading,
}: {
  player: ChampionshipPlayer;
  setCode: string;
  loading: boolean;
}) {
  const { board, formats, events } = player;
  const name = player.name.toUpperCase();
  const nameText = <FitText text={name} max={22} min={14} className="font-display tracking-[0.03em] text-text" />;
  const nameNode = player.slug ? (
    <Link
      to={playerPath(player.slug, setCode)}
      className="flex w-full min-w-0 no-underline [&:hover_span]:text-green"
    >
      {nameText}
    </Link>
  ) : (
    <span className="flex w-full min-w-0">{nameText}</span>
  );
  return (
    <div className="flex flex-col border border-border2 bg-surface">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
        <AAvatar displayName={player.name} avatarUrl={player.avatarUrl} size={52} green />
        <div className="flex-1 min-w-0 flex flex-col items-start gap-2">
          {nameNode}
          {board ? <RankBadge rank={board.rank} size="sm" /> : null}
        </div>
        {loading || !board ? (
          <div className="h-[52px] w-[200px] bg-surface2 animate-pulse" />
        ) : (
          <StatStrip board={board} />
        )}
      </div>
      {loading ? (
        <div className="m-4 h-[250px] bg-surface2 animate-pulse" />
      ) : (
        <BreakdownPanel
          breakdown={formats}
          totalScore={board?.score ?? 0}
          events={events}
          selfReported={[]}
          showPoints={formats.length > 0}
          bordered={false}
          compact
          labels={false}
          colorsPlayed={false}
          className="px-4 py-3 min-[1360px]:pl-4 pr-4"
        />
      )}
    </div>
  );
}

function LeanPlayerCard({
  player,
  setCode,
  loading,
}: {
  player: ChampionshipPlayer;
  setCode: string;
  loading: boolean;
}) {
  const [open, setOpen] = useState(false);
  const { board, formats, events } = player;
  const name = player.name.toUpperCase();
  const topFormats = [...formats].sort((a, b) => b.scoreContribution - a.scoreContribution);
  const { comboCount, comboTrophies } = aggregate(events);
  const topDecks = Object.entries(comboCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, LEAN_DECK_ROWS);
  return (
    <div className="flex flex-col border border-border2 bg-surface">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="w-full flex items-center gap-3 px-3 py-2.5 border-0 bg-transparent text-left cursor-pointer"
      >
        <AAvatar displayName={player.name} avatarUrl={player.avatarUrl} size={40} green />
        <span className="flex-1 min-w-0 flex flex-col gap-1.5">
          <span className="flex items-center gap-2 min-w-0">
            <FitText text={name} max={18} min={13} className="font-display tracking-[0.03em] text-text" />
            {board ? <RankBadge rank={board.rank} size="sm" /> : null}
          </span>
          {loading || !board ? (
            <span className="h-[14px] w-[140px] bg-surface2 animate-pulse" />
          ) : (
            <span className="grid grid-cols-[48px_74px_44px] items-center font-num text-[13px] text-subtle">
              <span className="flex items-center gap-1 text-text">
                <Trophy size={12} color="#ffc63a" />
                {board.trophies}
              </span>
              <Record mono wins={board.wins} losses={board.losses} />
              <span>{winRate(board.wins, board.losses)}</span>
            </span>
          )}
        </span>
        <ChevronDown size={18} className={cn("shrink-0 text-subtle transition-transform", open && "rotate-180")} />
      </button>
      {open && !loading ? (
        <div className="flex flex-col gap-3 px-3 pb-3 pt-3 border-t border-border">
          <LeanSection
            donut={topFormats.map((format) => ({
              key: format.formatLabel,
              value: format.scoreContribution,
              color: FMT_COLORS[format.formatLabel] ?? FMT_DEFAULT_COLOR,
            }))}
          >
            {topFormats.map((format) => (
              <LeanRow key={format.formatLabel} columns="1fr 30px 60px 38px">
                <span
                  className="font-display text-[14px] tracking-[0.06em]"
                  style={{ color: FMT_COLORS[format.formatLabel] ?? FMT_DEFAULT_COLOR }}
                >
                  {shortFormat(format.formatLabel)}
                </span>
                <TrophyCount count={format.trophies} display className="text-subtle justify-self-end" />
                <Record
                  mono
                  wins={format.wins}
                  losses={format.losses}
                  className="font-num text-[13px] text-right text-subtle"
                />
                <span className="font-num text-[13px] text-right text-text">
                  {winRate(format.wins, format.losses)}
                </span>
              </LeanRow>
            ))}
          </LeanSection>
          <LeanSection
            donut={Object.entries(comboCount).map(([combo, count]) => ({
              key: combo,
              value: count,
              colors: comboColors(combo),
            }))}
          >
            {topDecks.map(([combo, count]) => (
              <LeanRow key={combo} columns="auto 1fr 30px 34px">
                <Pips colors={combo} size={13} />
                <span className="truncate font-display text-[14px] tracking-[0.06em] text-text">
                  {colorsDisplayName(combo)}
                </span>
                <TrophyCount count={comboTrophies[combo] ?? 0} display className="text-subtle justify-self-end" />
                <span className="font-num text-[13px] text-right text-subtle">×{count}</span>
              </LeanRow>
            ))}
          </LeanSection>
          {player.slug ? (
            <Link
              to={playerPath(player.slug, setCode)}
              className="flex items-center justify-between pt-2 border-t border-border no-underline text-green
                font-display text-[13px] tracking-[0.14em]"
            >
              VIEW PROFILE
              <ArrowRight size={14} />
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function LeanSection({ donut, children }: { donut: DonutEntry[]; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <DonutChart pieHole={0.5} entries={donut} radius={34} strokeWidth={12} size={LEAN_DONUT_SIZE} padding={2} />
      <div className="flex-1 min-w-0 flex flex-col gap-1">{children}</div>
    </div>
  );
}

function LeanRow({ columns, children }: { columns: string; children: ReactNode }) {
  return (
    <div className="grid items-center gap-2 h-[22px]" style={{ gridTemplateColumns: columns }}>
      {children}
    </div>
  );
}

function StatStrip({ board }: { board: LeaderboardRow }) {
  const valueClass = "font-display text-[18px] leading-none whitespace-nowrap";
  const tiles: [string, ReactNode][] = [
    [
      "TROPHIES",
      <span key="trophies" className="flex items-center gap-1">
        <Trophy size={14} color="#ffc63a" />
        <span className={valueClass}>{board.trophies}</span>
      </span>,
    ],
    ["EVENTS", <span key="events" className={valueClass}>{board.events}</span>],
    ["RECORD", <Record key="record" mono wins={board.wins} losses={board.losses} className={valueClass} />],
    ["WIN %", <span key="win" className={valueClass}>{winPercent(board.wins, board.losses, 1)}</span>],
  ];
  return (
    <div className="shrink-0 flex border border-border2 bg-bg">
      {tiles.map(([label, value], index) => (
        <div
          key={label}
          className={cn(
            "flex flex-col items-center gap-1.5 py-2 px-1.5 whitespace-nowrap",
            index < tiles.length - 1 && "border-r border-border2",
          )}
        >
          <SectionLabel size={12} letterSpacing="0.1em">
            {label}
          </SectionLabel>
          {value}
        </div>
      ))}
    </div>
  );
}

function winPercent(wins: number, losses: number, decimals: number): string {
  const games = wins + losses;
  return games === 0 ? "-" : ((wins / games) * 100).toFixed(decimals);
}

function winRate(wins: number, losses: number): string {
  const percent = winPercent(wins, losses, 0);
  return percent === "-" ? percent : `${percent}%`;
}
