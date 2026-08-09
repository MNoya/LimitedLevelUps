import { useMemo, type ReactNode } from "react";
import { HelpCircle } from "lucide-react";
import { Tooltip } from "../Tooltip";
import { groupBySlot, findExtremes, classifyYourPick } from "../../data/p0p1Stats";
import { SLOTS } from "../../data/p0p1Slots";
import {
  buildRatingsByName,
  bestPossibleTeam,
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

type PickState = "fav" | "pack" | "rogue";
type ScoredPick = { state: PickState; cardName: string; pickCount: number };

export const CHAMFER = "polygon(10px 0, 100% 0, calc(100% - 10px) 100%, 0 100%)";
export const MEDAL_COLOR: Record<1 | 2 | 3, string> = {
  1: "#ffc63a",
  2: "#c0c8d6",
  3: "#c87941",
};
const GREEN = "#2ee85c";
const CELL_ORDER: Record<PickState, number> = { fav: 0, pack: 1, rogue: 2 };
const CAT_COLOR: Record<PickState, string> = {
  fav: GREEN,
  pack: "#4aa8ff",
  rogue: "#a98eff",
};

export function P0P1BallotScorecard({
  pickStats,
  picksBySlot,
}: {
  pickStats: P0P1PickStat[];
  picksBySlot: Map<string, string>;
}) {
  const picks = ballotPicks(pickStats, picksBySlot);
  if (picks.length === 0) {
    return null;
  }
  const favs = picks.filter((p) => p.state === "fav").length;
  const mids = picks.filter((p) => p.state === "pack").length;
  const rogues = picks.filter((p) => p.state === "rogue");
  const boldest = boldestRogue(rogues);
  const sorted = [...picks].sort((a, b) => CELL_ORDER[a.state] - CELL_ORDER[b.state]);

  return (
    <div className="inline-block animate-fadeUpIn" style={{ clipPath: CHAMFER, background: "#3b4458", padding: 1 }}>
      <div className="bg-surface2 w-[clamp(280px,22vw,340px)] px-5 py-2.5 flex flex-col gap-2" style={{ clipPath: CHAMFER }}>
        <Tooltip label={<BallotLegend />} side="bottom" align="start" hideArrow className="max-w-[320px]">
          <button
            type="button"
            className="group inline-flex items-center gap-1.5 self-start cursor-help bg-transparent border-0 p-0"
          >
            <HelpCircle size={15} strokeWidth={2} className="text-white transition-colors" />
            <span className="font-display text-white" style={{ fontSize: 15, letterSpacing: "0.22em" }}>YOUR BALLOT</span>
          </button>
        </Tooltip>

        <div className="flex items-center justify-between">
          <StatInline n={favs} label="CROWD" color={CAT_COLOR.fav} />
          <StatInline n={mids} label="SPLIT" color={CAT_COLOR.pack} />
          <StatInline n={rogues.length} label="ROGUE" color={CAT_COLOR.rogue} className="mr-[5px]" />
        </div>

        <div className="flex gap-1 -ml-[5px]" aria-hidden>
          {sorted.map((pick, i) => (
            <div key={i} className="h-2.5 flex-1 rounded-[1px]" style={{ background: CAT_COLOR[pick.state] }} />
          ))}
        </div>

        {boldest && (
          <p className="font-body text-subtle text-[12px] leading-snug -ml-[10px]">
            <span className="mr-1">🌶️</span>
            {rarityPrefix(boldest.pickCount)}{" "}
            <span className="text-text">{boldest.cardName}</span>
          </p>
        )}
      </div>
    </div>
  );
}

export function BallotScorecardSkeleton() {
  return (
    <div className="inline-block" style={{ clipPath: CHAMFER, background: "#3b4458", padding: 1 }}>
      <div className="bg-surface2 w-[clamp(280px,22vw,340px)] px-5 py-2.5 flex flex-col gap-2" style={{ clipPath: CHAMFER }}>
        <div className="h-[15px] w-28 bg-surface animate-pulse" />
        <div className="h-6 w-40 bg-surface animate-pulse" />
        <div className="flex gap-1 -ml-[5px]" aria-hidden>
          {Array.from({ length: SLOTS.length }, (_, i) => (
            <div key={i} className="h-2.5 flex-1 rounded-[1px] bg-surface animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  );
}

function StatInline({ n, label, color, className }: { n: number; label: string; color: string; className?: string }) {
  return (
    <span className={`flex items-baseline gap-1.5 ${className ?? ""}`}>
      <span className="font-display leading-none" style={{ fontSize: 24, color }}>{n}</span>
      <span className="font-body text-[12px] leading-none" style={{ color }}>{label}</span>
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

function ballotPicks(pickStats: P0P1PickStat[], picksBySlot: Map<string, string>): ScoredPick[] {
  const grouped = groupBySlot(pickStats);
  const picks: ScoredPick[] = [];
  for (const slot of SLOTS) {
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

export function MidwayBallotScorecard({
  ratingsSnapshot,
  cards,
  picksBySlot,
}: {
  ratingsSnapshot: RatingsSnapshot;
  cards: Card[];
  picksBySlot: Map<string, string>;
}) {
  const aligned = useMemo(() => {
    const ratingsByName = buildRatingsByName(ratingsSnapshot);
    const best = bestPossibleTeam(cards, SLOTS, ratingsByName);
    const bestBySlot = new Map(best.picks.map((p) => [p.slot, p.cardName]));
    let count = 0;
    for (const slot of SLOTS) {
      const your = picksBySlot.get(slot.key);
      const bestCard = bestBySlot.get(slot.key as SlotKey);
      if (your && bestCard && your === bestCard) count++;
    }
    return count;
  }, [ratingsSnapshot, cards, picksBySlot]);

  const segments = Array.from({ length: SLOTS.length }, (_, i) => i < aligned);

  return (
    <div className="inline-block animate-fadeUpIn" style={{ clipPath: CHAMFER, background: "#3b4458", padding: 1 }}>
      <div className="bg-surface2 w-[clamp(280px,22vw,340px)] px-5 py-2.5 flex flex-col gap-2" style={{ clipPath: CHAMFER }}>
        <Tooltip label={<MidwayBallotLegend />} side="bottom" align="start" hideArrow className="max-w-[320px]">
          <button
            type="button"
            className="group inline-flex items-center gap-1.5 self-start cursor-help bg-transparent border-0 p-0"
          >
            <HelpCircle size={15} strokeWidth={2} className="text-white transition-colors" />
            <span className="font-display text-white" style={{ fontSize: 15, letterSpacing: "0.22em" }}>YOUR BALLOT</span>
          </button>
        </Tooltip>

        <div className="flex items-baseline gap-1.5">
          <span className="font-display leading-none" style={{ fontSize: 24, color: GREEN }}>{aligned}</span>
          <span className="font-body text-[12px] leading-none" style={{ color: GREEN }}>BEST POSSIBLE PICKS</span>
        </div>

        <div className="flex gap-1 -ml-[5px]" aria-hidden>
          {segments.map((hit, i) => (
            <div key={i} className="h-2.5 flex-1 rounded-[1px]" style={{ background: hit ? GREEN : "#3b4458" }} />
          ))}
        </div>
      </div>
    </div>
  );
}

function MidwayBallotLegend() {
  return (
    <div className="text-left leading-snug">
      <span className="font-semibold" style={{ color: GREEN }}>Best possible picks</span>{" "}
      <span className="text-subtle">— the top card for a given slot based on GIH win rate</span>
    </div>
  );
}

// ── Final variant ──────────────────────────────────────────────────────────────

const MEDAL_EMOJI: Record<1 | 2 | 3, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

export function FinalBallotScorecard({
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
    const ratingsByName = buildRatingsByName(ratingsSnapshot);
    const bestTeam = bestPossibleTeam(cards, SLOTS, ratingsByName);
    const rankedBallots = applyDevSelfPlacement(
      rankBallots(groupBallotRows(ballots), ratingsByName),
      0,
      bestTeam,
      p0p1DevEnabled ? selfPlacement : "auto",
    );
    const userBallot = findUserBallot(rankedBallots, picksBySlot, discordId);
    const completeScores = rankedBallots
      .filter((b) => b.picks.size === SLOTS.length)
      .map((b) => b.score);
    return {
      score: userBallot?.score ?? scoreBallot(picksBySlot as Map<SlotKey, string>, ratingsByName),
      rank: userBallot?.rank ?? null,
      total: rankedBallots.length,
      bestScore: bestTeam.score,
      crowdScore: mostPopularTeam(pickStats, SLOTS, ratingsByName).score,
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
    <div
      className="inline-block animate-fadeUpIn"
      style={{ clipPath: CHAMFER, background: medal ? `${accent}8c` : "#3b4458", padding: 1 }}
    >
      <div className="bg-surface2 w-[clamp(280px,22vw,340px)] px-5 py-2.5 flex flex-col gap-2" style={{ clipPath: CHAMFER }}>
        <Tooltip label={<FinalBallotLegend />} side="bottom" align="start" hideArrow className="max-w-[320px]">
          <button
            type="button"
            className="group inline-flex items-center gap-1.5 self-start cursor-help bg-transparent border-0 p-0"
          >
            <HelpCircle size={15} strokeWidth={2} className="text-white transition-colors" />
            <span className="font-display text-white" style={{ fontSize: 15, letterSpacing: "0.22em" }}>YOUR RESULT</span>
          </button>
        </Tooltip>

        <div className="flex items-baseline justify-between">
          <span className="flex items-baseline gap-1.5">
            <span className="font-mono tabular-nums leading-none" style={{ fontSize: 24, color: accent }}>
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
        </div>

        <div className="h-2.5 rounded-[1px] relative -ml-[5px]" style={{ background: "#3b4458" }} aria-hidden>
          <div
            className="absolute top-0 left-0 h-full rounded-[1px]"
            style={{ width: `${fillPct}%`, background: accent }}
          />
          <div className="absolute top-0 h-full w-px bg-white/50" style={{ left: `${crowdPct}%` }} />
        </div>
      </div>
    </div>
  );
}

function FinalBallotLegend() {
  return (
    <div className="flex flex-col gap-1.5 text-left leading-snug">
      <div>
        <span className="font-semibold" style={{ color: GREEN }}>Score</span>{" "}
        <span className="text-subtle">— your ballot's summed <b className="font-semibold text-text">GIH win rate</b></span>
      </div>
      <div className="text-subtle">
        The bar spans the <b className="font-semibold text-text">lowest completed ballot</b> to
        the <b className="font-semibold text-text">best possible</b> ballot;
        the white line marks the performance of the <b className="font-semibold text-text">crowd picks</b>
      </div>
    </div>
  );
}
