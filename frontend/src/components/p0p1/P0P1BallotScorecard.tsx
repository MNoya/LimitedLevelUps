import { useMemo, useState, type ReactNode } from "react";
import { HelpCircle } from "lucide-react";
import { Tooltip } from "../Tooltip";
import { CUT_CORNER_CHAMFER } from "../ChamferCta";
import { groupBySlot, findExtremes, classifyYourPick } from "../../data/p0p1Stats";
import { slotsForSet } from "../../data/p0p1Slots";
import {
  buildRatingsByName,
  bestPossibleTeam,
  slotTopCards,
  mostPopularTeam,
  scoreBallot,
  groupBallotRows,
  rankBallots,
  findUserBallot,
  applyDevSelfPlacement,
} from "../../data/p0p1Results";
import type { RatingsSnapshot } from "../../data/p0p1Results";
import type { Card, P0P1BallotRow, P0P1PickStat, SlotKey } from "../../types/p0p1";
import { p0p1DevEnabled, useP0P1DevSelfPlacement } from "../../data/p0p1DevState";
import type { useP0P1Ballot } from "../../data/useP0P1Ballot";

type Ballot = ReturnType<typeof useP0P1Ballot>;

type PickState = "fav" | "pack" | "rogue";
type ScoredPick = { state: PickState; cardName: string; pickCount: number };

export const CHAMFER = "polygon(10px 0, 100% 0, calc(100% - 10px) 100%, 0 100%)";
export const MEDAL_COLOR: Record<1 | 2 | 3, string> = {
  1: "#ffc63a",
  2: "#c0c8d6",
  3: "#c87941",
};
const GREEN = "#2ee85c";
const FRAME_COLOR = "#3b4458";
const CELL_ORDER: Record<PickState, number> = { fav: 0, pack: 1, rogue: 2 };
const CAT_COLOR: Record<PickState, string> = {
  fav: GREEN,
  pack: "#4aa8ff",
  rogue: "#a98eff",
};

export function yourBallotScorecard(ballot: Ballot, compact = false): ReactNode {
  const { user, isPastDeadline, isComplete, pickStats, phase, resultsDataReady, ratingsSnapshot, cards, ballots } = ballot;
  const { picksBySlot, featured } = ballot;
  if (!user || !isPastDeadline || !isComplete || !pickStats || pickStats.length === 0) {
    return null;
  }
  if (phase === "final" && resultsDataReady && ratingsSnapshot && cards && ballots) {
    return (
      <FinalBallotScorecard
        ratingsSnapshot={ratingsSnapshot}
        pickStats={pickStats}
        ballots={ballots}
        cards={cards}
        picksBySlot={picksBySlot}
        discordId={user.discordId}
      />
    );
  }
  if (phase === "midway" && resultsDataReady && ratingsSnapshot && cards) {
    return (
      <MidwayBallotScorecard ratingsSnapshot={ratingsSnapshot} cards={cards} picksBySlot={picksBySlot} compact={compact} />
    );
  }
  return (
    <P0P1BallotScorecard pickStats={pickStats} picksBySlot={picksBySlot} setCode={featured?.code ?? ""} compact={compact} />
  );
}

function P0P1BallotScorecard({
  pickStats,
  picksBySlot,
  setCode,
  compact,
}: {
  pickStats: P0P1PickStat[];
  picksBySlot: Map<string, string>;
  setCode: string;
  compact: boolean;
}) {
  const picks = ballotPicks(pickStats, picksBySlot, setCode);
  if (picks.length === 0) {
    return null;
  }
  const favs = picks.filter((p) => p.state === "fav").length;
  const mids = picks.filter((p) => p.state === "pack").length;
  const rogues = picks.filter((p) => p.state === "rogue");
  const boldest = boldestRogue(rogues);
  const sorted = [...picks].sort((a, b) => CELL_ORDER[a.state] - CELL_ORDER[b.state]);

  return (
    <ScorecardShell
      title="YOUR BALLOT"
      legend={<BallotLegend />}
      compact={compact}
      stats={
        <>
          <StatInline n={favs} label="CROWD" color={CAT_COLOR.fav} compact={compact} />
          <StatInline n={mids} label="SPLIT" color={CAT_COLOR.pack} compact={compact} />
          <StatInline
            n={rogues.length}
            label="ROGUE"
            color={CAT_COLOR.rogue}
            compact={compact}
            className={compact ? undefined : "mr-[5px]"}
          />
        </>
      }
      bar={
        <div className={`flex gap-1 ${barOffset(compact)}`} aria-hidden>
          {sorted.map((pick, i) => (
            <div key={i} className={`${barHeight(compact)} flex-1 rounded-[1px]`} style={{ background: CAT_COLOR[pick.state] }} />
          ))}
        </div>
      }
      footnote={
        boldest && (
          <p className={`font-body text-subtle text-[12px] leading-snug ${compact ? "" : "-ml-[10px]"}`}>
            <span className="mr-1">🌶️</span>
            {rarityPrefix(boldest.pickCount)}{" "}
            <span className="text-text">{boldest.cardName}</span>
          </p>
        )
      }
    />
  );
}

function ScorecardShell({
  title,
  legend,
  stats,
  bar,
  footnote,
  frameColor,
  compact,
}: {
  title: string;
  legend: ReactNode;
  stats: ReactNode;
  bar: ReactNode;
  footnote?: ReactNode;
  frameColor?: string;
  compact: boolean;
}) {
  const [legendOpen, setLegendOpen] = useState(false);

  if (compact) {
    return (
      <button
        type="button"
        onClick={() => setLegendOpen((o) => !o)}
        aria-expanded={legendOpen}
        className="block w-full bg-transparent border-0 p-0 text-left cursor-pointer"
      >
        <ScorecardFrame compact frameColor={frameColor} animate>
          <div className="w-full flex items-center gap-3">
            <span className="flex items-center gap-1 shrink-0">
              <HelpCircle size={12} strokeWidth={2} className="text-white" />
              <span className="font-display text-white" style={{ fontSize: 12, letterSpacing: "0.22em" }}>{title}</span>
            </span>
            <div className="flex-1 min-w-0 flex items-baseline justify-end gap-3">{stats}</div>
          </div>
          {bar}
          {legendOpen && (
            <div className="flex flex-col gap-1.5 pt-1 text-[12px]">
              {legend}
              {footnote}
            </div>
          )}
        </ScorecardFrame>
      </button>
    );
  }

  return (
    <ScorecardFrame compact={false} frameColor={frameColor} animate>
      <Tooltip label={legend} side="bottom" align="start" hideArrow className="max-w-[320px]">
        <button
          type="button"
          className="group inline-flex items-center gap-1.5 self-start bg-transparent border-0 p-0"
        >
          <HelpCircle size={15} strokeWidth={2} className="text-white transition-colors" />
          <span className="font-display text-white" style={{ fontSize: 15, letterSpacing: "0.22em" }}>{title}</span>
        </button>
      </Tooltip>
      <div className="flex items-baseline justify-between">{stats}</div>
      {bar}
      {footnote}
    </ScorecardFrame>
  );
}

export function ScorecardFrame({
  compact,
  frameColor = FRAME_COLOR,
  animate = false,
  children,
}: {
  compact: boolean;
  frameColor?: string;
  animate?: boolean;
  children: ReactNode;
}) {
  const clipPath = compact ? CUT_CORNER_CHAMFER : CHAMFER;
  const outer = compact ? "block w-full" : "inline-block";
  const inner = compact
    ? "px-4 py-2 flex flex-col gap-1.5"
    : "w-[clamp(280px,22vw,340px)] px-5 py-2.5 flex flex-col gap-2";
  return (
    <div className={`${outer} ${animate ? "animate-fadeUpIn" : ""}`} style={{ clipPath, background: frameColor, padding: 1 }}>
      <div className={`bg-surface2 ${inner}`} style={{ clipPath }}>
        {children}
      </div>
    </div>
  );
}

function barHeight(compact: boolean): string {
  return compact ? "h-1.5" : "h-2.5";
}

function barOffset(compact: boolean): string {
  return compact ? "" : "-ml-[5px]";
}

export function BallotScorecardSkeleton({ setCode = "", compact = false }: { setCode?: string; compact?: boolean }) {
  if (compact) {
    return (
      <ScorecardFrame compact>
        <div className="flex items-center justify-between gap-3">
          <div className="h-3 w-24 bg-surface animate-pulse" />
          <div className="h-4 w-36 bg-surface animate-pulse" />
        </div>
        <div className="h-1.5 w-full bg-surface animate-pulse rounded-[1px]" />
      </ScorecardFrame>
    );
  }
  return (
    <ScorecardFrame compact={false}>
      <div className="h-[15px] w-28 bg-surface animate-pulse" />
      <div className="h-6 w-40 bg-surface animate-pulse" />
      <div className="flex gap-1 -ml-[5px]" aria-hidden>
        {Array.from({ length: slotsForSet(setCode).length }, (_, i) => (
          <div key={i} className="h-2.5 flex-1 rounded-[1px] bg-surface animate-pulse" />
        ))}
      </div>
    </ScorecardFrame>
  );
}

function StatInline({
  n,
  label,
  color,
  compact,
  className,
}: {
  n: number | string;
  label: string;
  color: string;
  compact: boolean;
  className?: string;
}) {
  return (
    <span className={`flex items-baseline ${compact ? "gap-1" : "gap-1.5"} ${className ?? ""}`}>
      <span className="font-display leading-none" style={{ fontSize: compact ? 17 : 24, color }}>{n}</span>
      <span className={`font-body leading-none ${compact ? "text-[11px]" : "text-[12px]"}`} style={{ color }}>{label}</span>
    </span>
  );
}

function BallotLegend() {
  return (
    <div className="flex flex-col gap-1.5 text-left">
      <LegendRow color={CAT_COLOR.fav} term="Crowd" def={<>you picked the <b className="font-semibold text-text">most popular</b> card</>} />
      <LegendRow color={CAT_COLOR.pack} term="Split" def={<>you picked a card in the <b className="font-semibold text-text">middle</b> of the pack</>} />
      <LegendRow color={CAT_COLOR.rogue} term="Rogue" def={<>you picked one of the <b className="font-semibold text-text">least popular</b> cards</>} />
    </div>
  );
}

function LegendRow({ color, term, def }: { color: string; term: string; def: ReactNode }) {
  return (
    <div className="leading-snug">
      <span className="font-semibold" style={{ color }}>{term}</span> <span className="text-subtle">- {def}</span>
    </div>
  );
}

function ballotPicks(pickStats: P0P1PickStat[], picksBySlot: Map<string, string>, setCode: string): ScoredPick[] {
  const grouped = groupBySlot(pickStats);
  const picks: ScoredPick[] = [];
  for (const slot of slotsForSet(setCode)) {
    const cardName = picksBySlot.get(slot.key);
    if (!cardName) {
      continue;
    }
    const slotStats = grouped.get(slot.key);
    const yourStat = slotStats?.find((s) => s.cardName === cardName);
    if (!slotStats || !yourStat) {
      continue;
    }
    const { most, least } = findExtremes(slotStats);
    const state = classifyYourPick(yourStat, most, least).state;
    picks.push({
      state: state === "most" ? "fav" : state === "rogue" ? "rogue" : "pack",
      cardName,
      pickCount: yourStat.pickCount,
    });
  }
  return picks;
}

function boldestRogue(rogues: ScoredPick[]): ScoredPick | null {
  let boldest: ScoredPick | null = null;
  for (const rogue of rogues) {
    if (!boldest || rogue.pickCount < boldest.pickCount) {
      boldest = rogue;
    }
  }
  return boldest;
}

function rarityPrefix(pickCount: number): string {
  const others = pickCount - 1;
  if (others <= 0) {
    return "You were the only one to pick";
  }
  if (others === 1) {
    return "Only you and 1 other picked";
  }
  return `Only you and ${others} others picked`;
}

// ── Midway variant ─────────────────────────────────────────────────────────────

function MidwayBallotScorecard({
  ratingsSnapshot,
  cards,
  picksBySlot,
  compact,
}: {
  ratingsSnapshot: RatingsSnapshot;
  cards: Card[];
  picksBySlot: Map<string, string>;
  compact: boolean;
}) {
  const contestSlots = slotsForSet(ratingsSnapshot.setCode);
  const aligned = useMemo(() => {
    const ratingsByName = buildRatingsByName(ratingsSnapshot);
    const bestBySlot = slotTopCards(cards, contestSlots, ratingsByName);
    let count = 0;
    for (const slot of contestSlots) {
      const your = picksBySlot.get(slot.key);
      const bestCard = bestBySlot.get(slot.key as SlotKey);
      if (your && bestCard && your === bestCard) count++;
    }
    return count;
  }, [ratingsSnapshot, cards, picksBySlot, contestSlots]);

  const segments = Array.from({ length: contestSlots.length }, (_, i) => i < aligned);

  return (
    <ScorecardShell
      title="YOUR BALLOT"
      legend={<MidwayBallotLegend />}
      compact={compact}
      stats={<StatInline n={aligned} label="BEST POSSIBLE PICKS" color={GREEN} compact={compact} />}
      bar={
        <div className={`flex gap-1 ${barOffset(compact)}`} aria-hidden>
          {segments.map((hit, i) => (
            <div key={i} className={`${barHeight(compact)} flex-1 rounded-[1px]`} style={{ background: hit ? GREEN : FRAME_COLOR }} />
          ))}
        </div>
      }
    />
  );
}

function MidwayBallotLegend() {
  return (
    <div className="text-left leading-snug">
      <span className="font-semibold" style={{ color: GREEN }}>Best possible picks</span>{" "}
      <span className="text-subtle">- the top card for a given slot based on GIH win rate</span>
    </div>
  );
}

// ── Final variant ──────────────────────────────────────────────────────────────

const MEDAL_EMOJI: Record<1 | 2 | 3, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

function FinalBallotScorecard({
  ratingsSnapshot,
  pickStats,
  ballots,
  cards,
  picksBySlot,
  discordId,
}: {
  ratingsSnapshot: RatingsSnapshot;
  pickStats: P0P1PickStat[];
  ballots: P0P1BallotRow[];
  cards: Card[];
  picksBySlot: Map<string, string>;
  discordId?: string;
}) {
  const selfPlacement = useP0P1DevSelfPlacement();
  const result = useMemo(() => {
    const slots = slotsForSet(ratingsSnapshot.setCode);
    const ratingsByName = buildRatingsByName(ratingsSnapshot);
    const bestTeam = bestPossibleTeam(cards, slots, ratingsByName);
    const rankedBallots = applyDevSelfPlacement(
      rankBallots(groupBallotRows(ballots), ratingsByName),
      0,
      bestTeam,
      p0p1DevEnabled ? selfPlacement : "auto",
    );
    const userBallot = findUserBallot(rankedBallots, picksBySlot, discordId);
    const completeScores = rankedBallots
      .filter((b) => b.picks.size === slots.length)
      .map((b) => b.score);
    return {
      score: userBallot?.score ?? scoreBallot(picksBySlot as Map<SlotKey, string>, ratingsByName),
      rank: userBallot?.rank ?? null,
      total: rankedBallots.length,
      bestScore: bestTeam.score,
      crowdScore: mostPopularTeam(pickStats, slots, ratingsByName).score,
      floor: completeScores.length > 0 ? Math.min(...completeScores) : 0,
    };
  }, [ratingsSnapshot, pickStats, ballots, cards, picksBySlot, selfPlacement, discordId]);

  const medal = result.rank !== null && result.rank <= 3 ? (result.rank as 1 | 2 | 3) : null;
  const accent = medal ? MEDAL_COLOR[medal] : GREEN;
  // Track spans lowest complete ballot → best possible; 0-based when that range collapses
  const floor = result.bestScore > result.floor ? result.floor : 0;
  const span = result.bestScore - floor;
  const barPct = (value: number) =>
    span > 0 ? Math.min(100, Math.max(0, ((value - floor) / span) * 100)) : 0;
  const fillPct = result.score > 0 ? Math.max(3, barPct(result.score)) : 0;
  const crowdPct = barPct(result.crowdScore);

  return (
    <ScorecardShell
      title="YOUR RESULT"
      legend={<FinalBallotLegend />}
      compact={false}
      frameColor={medal ? `${accent}8c` : undefined}
      stats={
        <>
          <span className="flex items-baseline gap-1.5">
            <span className="font-num tabular-nums leading-none" style={{ fontSize: 24, color: accent }}>
              {result.score.toFixed(1)}
            </span>
            <span className="font-body text-[12px] leading-none" style={{ color: accent }}>GIH WR total</span>
          </span>
          {result.rank !== null && (
            <span
              className={`font-mono tabular-nums text-[12px] leading-none ${medal ? "" : "text-subtle"}`}
              style={medal ? { color: accent } : undefined}
            >
              {medal ? `${MEDAL_EMOJI[medal]} ` : ""}#{result.rank} of {result.total}
            </span>
          )}
        </>
      }
      bar={
        <div className="h-2.5 rounded-[1px] relative -ml-[5px]" style={{ background: FRAME_COLOR }} aria-hidden>
          <div
            className="absolute top-0 left-0 h-full rounded-[1px]"
            style={{ width: `${fillPct}%`, background: accent }}
          />
          <div className="absolute top-0 h-full w-px bg-white/50" style={{ left: `${crowdPct}%` }} />
        </div>
      }
    />
  );
}

function FinalBallotLegend() {
  return (
    <div className="flex flex-col gap-1.5 text-left leading-snug">
      <div>
        <span className="font-semibold" style={{ color: GREEN }}>Score</span>{" "}
        <span className="text-subtle">- your ballot's summed <b className="font-semibold text-text">GIH win rate</b></span>
      </div>
      <div className="text-subtle">
        The bar spans the <b className="font-semibold text-text">lowest completed ballot</b> to
        the <b className="font-semibold text-text">best possible</b> ballot;
        the white line marks the performance of the <b className="font-semibold text-text">crowd picks</b>
      </div>
    </div>
  );
}
