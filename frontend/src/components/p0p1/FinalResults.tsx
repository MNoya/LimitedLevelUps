import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ChevronDown } from "lucide-react";
import { SectionLabel } from "../SectionLabel";
import { Tooltip } from "../Tooltip";
import { PickGrid } from "./CommunityGrid";
import { CardImagePreview } from "./CardImagePreview";
import { usePreloaded } from "../../lib/imageReveal";
import { breakdownStripAccent } from "./slotVisuals";
import { CHAMFER, MEDAL_COLOR } from "./P0P1BallotScorecard";
import { SLOTS, buildSlots, P0P1_CONTESTS } from "../../data/p0p1Slots";
import {
  buildRatingsByName,
  bestPossibleTeam,
  mostPopularTeam,
  groupBallotRows,
  rankBallots,
  buildStandingsList,
  findUserBallot,
  highlightsFeed,
  applyDevSelfPlacement,
  GIH_SAMPLE_FLOOR,
} from "../../data/p0p1Results";
import { p0p1DevEnabled, useP0P1DevSelfPlacement } from "../../data/p0p1DevState";
import type {
  RatingsSnapshot,
  TeamPick,
  TeamResult,
  CardRating,
  RankedBallot,
  SyntheticStanding,
  Highlight,
  HighlightVoter,
} from "../../data/p0p1Results";
import type { Card, P0P1BallotRow, P0P1PickStat, SlotKey } from "../../types/p0p1";
import type { PickEntry } from "./CommunityGrid";

const HIGHLIGHTS_COUNT = 5;

function SectionHeading({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <div className="flex justify-center">
        <SectionLabel size={22} className="text-white">{title}</SectionLabel>
      </div>
      {children && <p className="text-center text-[13.5px] text-subtle mt-1.5">{children}</p>}
    </div>
  );
}

function gihwrLabel(gihwr: number): string {
  return `${(gihwr * 100).toFixed(1)}%`;
}

function BallotAvatar({
  name,
  avatarUrl,
  className,
  fallbackClassName,
  style,
  title,
}: {
  name: string;
  avatarUrl: string | null;
  className: string;
  fallbackClassName: string;
  style?: React.CSSProperties;
  title?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (avatarUrl && !failed) {
    return (
      <img
        src={avatarUrl}
        alt={name}
        title={title}
        decoding="async"
        onError={() => setFailed(true)}
        className={className}
        style={style}
      />
    );
  }
  return (
    <div className={fallbackClassName} style={style} title={title}>
      {name.replace(/^\W+/, "").charAt(0).toUpperCase() || "?"}
    </div>
  );
}

function teamToEntries(picks: TeamPick[], setCode: string): PickEntry[] {
  const bySlot = new Map(picks.map((p) => [p.slot, p]));
  return SLOTS.map((slot) => {
    const pick = bySlot.get(slot.key);
    if (!pick?.cardName) return { slotKey: slot.key, label: slot.label, stats: [] };
    return {
      slotKey: slot.key,
      label: slot.label,
      stats: [{ setCode, slot: slot.key as SlotKey, cardName: pick.cardName, pickCount: 0, pickPct: 0 }],
      pctLabel: pick.gihwr > 0 ? gihwrLabel(pick.gihwr) : "—",
    };
  });
}

function ballotToEntries(ballot: RankedBallot, setCode: string, ratingsByName: Map<string, CardRating>): PickEntry[] {
  return SLOTS.map((slot) => {
    const cardName = ballot.picks.get(slot.key);
    if (!cardName) return { slotKey: slot.key, label: slot.label, stats: [] };
    const rating = ratingsByName.get(cardName);
    const gihwr =
      rating && rating.gih >= GIH_SAMPLE_FLOOR && rating.gihwr !== null ? rating.gihwr : null;
    return {
      slotKey: slot.key,
      label: slot.label,
      stats: [{ setCode, slot: slot.key as SlotKey, cardName, pickCount: 0, pickPct: 0 }],
      pctLabel: gihwr !== null ? gihwrLabel(gihwr) : "—",
    };
  });
}

// ── Per-slot contribution bar ─────────────────────────────────────────────────

interface SlotContrib {
  slotKey: SlotKey;
  label: string;
  cardName: string | null;
  card: Card | undefined;
  gihwr: number | null;
  points: number; // gihwr * 100, same units as ballot.score
}

function ballotContributions(
  ballot: RankedBallot,
  ratingsByName: Map<string, CardRating>,
  cardsByName: Map<string, Card>,
): SlotContrib[] {
  return SLOTS.map((slot) => {
    const cardName = ballot.picks.get(slot.key) ?? null;
    const card = cardName ? cardsByName.get(cardName) : undefined;
    const rating = cardName ? ratingsByName.get(cardName) : undefined;
    const gihwr =
      rating && rating.gih >= GIH_SAMPLE_FLOOR && rating.gihwr !== null
        ? rating.gihwr
        : null;
    return {
      slotKey: slot.key,
      label: slot.label,
      cardName,
      card,
      gihwr,
      points: gihwr !== null ? gihwr * 100 : 0,
    };
  });
}

function SegTooltipContent({ seg }: { seg: SlotContrib }) {
  const imageReady = usePreloaded(seg.card?.imageNormal ?? "");
  if (seg.card && !imageReady) return null;
  return (
    <div className="bg-surface2 border border-border2 rounded-sm shadow-xl overflow-hidden w-56">
      {seg.card ? (
        <img src={seg.card.imageNormal} alt={seg.card.name} className="w-full block" />
      ) : (
        <div className="px-2 py-1.5">
          <div className="font-display tracking-[0.1em] text-[10px] text-muted uppercase leading-none mb-0.5">
            {seg.label}
          </div>
          <div className="text-[12px] text-subtle">{seg.cardName ?? "—"}</div>
        </div>
      )}
    </div>
  );
}

function ContributionBar({
  ballot,
  maxScore,
  ratingsByName,
  cardsByName,
  stickyTop = 0,
}: {
  ballot: RankedBallot;
  maxScore: number;
  ratingsByName: Map<string, CardRating>;
  cardsByName: Map<string, Card>;
  /** Viewport offset (px) reserved by sticky page chrome — tooltips flip below the bar to clear it. */
  stickyTop?: number;
}) {
  const contribs = useMemo(
    () => ballotContributions(ballot, ratingsByName, cardsByName),
    [ballot, ratingsByName, cardsByName],
  );
  const activeContribs = contribs.filter((c) => c.points > 0);
  const fillPct = maxScore > 0 ? (ballot.score / maxScore) * 100 : 0;

  return (
    // self-stretch + negative vertical margins cancel the button's py-2.5/py-3 padding,
    // so the bar bleeds to the full row height while hover events still reach Layer 2.
    <div className="hidden lg:block flex-1 self-stretch -my-2.5 lg:-my-3 relative min-w-0" onClick={(e) => e.stopPropagation()}>
      {/* Track: full-width faint bar marks the max bar length / non-clickable extent */}
      <div className="absolute inset-0 bg-black/15 pointer-events-none" />

      {/* Layer 1: visual segments — overflow:hidden clips art to fill width */}
      <div
        className="absolute top-0 left-0 h-full flex gap-px overflow-hidden"
        style={{ width: `${fillPct}%` }}
      >
        {activeContribs.map(({ slotKey, card }) => (
          <div
            key={slotKey}
            className="relative h-full overflow-hidden flex-1 basis-0"
          >
            <div
              className="absolute top-0 left-0 right-0 h-[2px] z-10 pointer-events-none"
              style={{ background: breakdownStripAccent(slotKey) }}
            />
            {card && (
              // no loading="lazy" — these measure 0-height inside content-visibility rows and never load
              <img
                src={card.imageArtCrop}
                alt=""
                aria-hidden
                decoding="async"
                className="absolute inset-0 w-full xl:-top-1/4 object-cover pointer-events-none"
              />
            )}
            <div className="absolute inset-0 bg-black/55 pointer-events-none" />
          </div>
        ))}
      </div>

      {/* Layer 2: hover/tap targets — Tooltip portals to body so it escapes ancestor
          stacking contexts (e.g. the floating self-row) and clips to the viewport */}
      <div
        className="absolute top-0 left-0 h-full flex gap-px"
        style={{ width: `${fillPct}%` }}
      >
        {activeContribs.map((seg) => (
          <Tooltip
            key={seg.slotKey}
            label={<SegTooltipContent seg={seg} />}
            side="top"
            hideArrow
            delayDuration={0}
            collisionPadding={{ top: stickyTop + 8, bottom: 8, left: 8, right: 8 }}
            className="p-0 bg-transparent border-0 shadow-none"
          >
            <div className="relative h-full cursor-pointer flex-1 basis-0" />
          </Tooltip>
        ))}
      </div>
    </div>
  );
}

// ── Synthetic reference rows ─────────────────────────────────────────────────

const SYNTHETIC_STYLE: Record<SyntheticStanding["kind"], { label: string; color: string }> = {
  best: { label: "Best possible", color: "#3fe0d0" },
  crowd: { label: "Crowd Picks", color: "#7aa2ff" },
};

function BestPossibleBadge() {
  return (
    <span
      className="shrink-0 inline-flex items-center h-[18px] font-display uppercase tracking-[0.14em] px-[7px] text-[11px] text-bg"
      style={{ background: SYNTHETIC_STYLE.best.color }}
    >
      ✦ BEST POSSIBLE
    </span>
  );
}

function SelfBadge() {
  return (
    <span className="shrink-0 inline-flex items-center h-[18px] font-display uppercase tracking-[0.14em] px-[7px] text-[11px] bg-green text-bg">
      YOU
    </span>
  );
}

function syntheticToBallot(standing: SyntheticStanding): RankedBallot {
  const picks = new Map<SlotKey, string>();
  for (const p of standing.team.picks) {
    if (p.cardName) picks.set(p.slot, p.cardName);
  }
  return {
    ballotId: standing.kind === "best" ? -1 : -2,
    name: SYNTHETIC_STYLE[standing.kind].label,
    avatarUrl: null,
    picks,
    score: standing.team.score,
    rank: 0,
  };
}

function SyntheticRow({
  standing,
  setCode,
  maxScore,
  cardsByName,
  ratingsByName,
  stickyTop = 0,
}: {
  standing: SyntheticStanding;
  setCode: string;
  maxScore: number;
  cardsByName: Map<string, Card>;
  ratingsByName: Map<string, CardRating>;
  stickyTop?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const style = SYNTHETIC_STYLE[standing.kind];
  const ballot = useMemo(() => syntheticToBallot(standing), [standing]);
  const entries = useMemo(
    () => (expanded ? teamToEntries(standing.team.picks, setCode) : []),
    [expanded, standing, setCode],
  );

  return (
    <div
      className="border-b border-border2 last:border-b-0"
      style={{
        boxShadow: `inset 3px 0 0 ${style.color}`,
        backgroundImage: `linear-gradient(90deg, ${style.color}0d, transparent 55%)`,
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 lg:gap-3 px-3 lg:px-4 py-2.5 lg:py-3 text-left cursor-pointer bg-transparent border-0"
      >
        <span className="w-7 lg:w-8 shrink-0" />

        <div
          className="w-6 h-6 lg:w-7 lg:h-7 rounded-full shrink-0 bg-surface flex items-center justify-center text-[11px] lg:text-[12px]"
          style={{ color: style.color, boxShadow: `0 0 0 1.5px ${style.color}` }}
        >
          ✦
        </div>

        <span className="font-display tracking-wider flex-1 min-w-0 lg:flex-none lg:w-[150px] lg:shrink-0 text-[14px] lg:text-[15px] truncate text-subtle" style={{ color: style.color }}>
          {style.label}
        </span>

        <ContributionBar
          ballot={ballot}
          maxScore={maxScore}
          ratingsByName={ratingsByName}
          cardsByName={cardsByName}
          stickyTop={stickyTop}
        />

        <span
          className="font-mono tabular-nums text-[13px] lg:text-[14px] font-semibold shrink-0"
          style={{ color: style.color }}
        >
          {standing.team.score.toFixed(2)}
        </span>

        <ChevronDown
          size={14}
          className={`shrink-0 text-muted transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <div className="px-3 lg:px-4 pb-4 pt-1">
          <PickGrid entries={entries} cardsByName={cardsByName} setCode={setCode} />
        </div>
      )}
    </div>
  );
}

// ── Broadcast top-3 ─────────────────────────────────────────────────────────────

function BroadcastTop3({
  champion,
  runnersUp,
  self,
  setCode,
  cardsByName,
  ratingsByName,
  userBallotId,
  bestAchieverIds,
}: {
  champion: RankedBallot;
  runnersUp: RankedBallot[];
  self: RankedBallot | null;
  setCode: string;
  cardsByName: Map<string, Card>;
  ratingsByName: Map<string, CardRating>;
  userBallotId: number | null;
  bestAchieverIds: Set<number>;
}) {
  const entries = useMemo(
    () => ballotToEntries(champion, setCode, ratingsByName),
    [champion, setCode, ratingsByName],
  );

  return (
    <div className="animate-fadeUpIn flex flex-col gap-2.5">
      <div
        className="relative overflow-hidden"
        style={{
          transform: "skewX(-6deg)",
          marginInline: 10,
          background: "linear-gradient(100deg, #232a3a, #1d2330 55%)",
          border: "1px solid #3b4458",
          borderLeft: 0,
          boxShadow: "0 0 34px #ffc63a22",
        }}
      >
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: "repeating-linear-gradient(to bottom, #ffffff06 0 1px, transparent 1px 3px)",
          }}
        />
        <div
          className="absolute top-0 bottom-0 left-0 flex items-center justify-center shrink-0"
          style={{ width: 56, background: `linear-gradient(180deg, #ffd76a, ${MEDAL_COLOR[1]} 55%, #d99e12)` }}
        >
          <span
            className="font-display leading-none"
            style={{ fontSize: 40, color: "#0a0c10", transform: "skewX(6deg)" }}
          >
            1
          </span>
        </div>
        <div
          className="relative flex flex-row items-center gap-3 sm:gap-4 py-3 sm:py-4"
          style={{ transform: "skewX(6deg)", paddingLeft: 74, paddingRight: 20 }}
        >
          <div className="flex items-center gap-3 sm:gap-4 flex-1 min-w-0">
            <BallotAvatar
              name={champion.name}
              avatarUrl={champion.avatarUrl}
              className="w-10 h-10 sm:w-14 sm:h-14 rounded-full shrink-0 object-cover"
              fallbackClassName="w-10 h-10 sm:w-14 sm:h-14 rounded-full shrink-0 bg-surface flex items-center justify-center text-[14px] sm:text-[20px] text-muted font-mono"
              style={{ boxShadow: `0 0 0 2px #1d2330, 0 0 0 3px ${MEDAL_COLOR[1]}, 0 0 18px #ffc63a66` }}
            />

            <div className="flex-1 min-w-0">
              <div className="font-mono tracking-[0.22em] text-[10px] sm:text-[10.5px] uppercase text-gold">
                🏆 CHAMPION
              </div>
              <div className="flex flex-row items-center gap-1.5 sm:gap-2 min-w-0">
                <span className="font-display text-[24px] sm:text-[44px] leading-[0.95] tracking-[0.03em] truncate min-w-0">
                  {champion.name.toUpperCase()}
                </span>
                {(champion.ballotId === userBallotId || bestAchieverIds.has(champion.ballotId)) && (
                  <div className="flex items-center gap-1.5 shrink-0">
                    {champion.ballotId === userBallotId && <SelfBadge />}
                    {bestAchieverIds.has(champion.ballotId) && <BestPossibleBadge />}
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="text-right shrink-0 pl-3 sm:pl-4">
            <div className="hidden sm:block" style={{ borderLeft: "2px solid #ffc63a55", paddingLeft: 18 }}>
              <div
                className="font-mono tabular-nums text-[34px] font-bold leading-[1.05] text-gold"
                style={{ textShadow: "0 0 34px #ffc63a90" }}
              >
                {champion.score.toFixed(2)}
              </div>
              <div className="font-mono tracking-[0.24em] text-[10.5px] font-semibold text-gold/80 mt-1">FINAL SCORE</div>
            </div>
            <div className="sm:hidden">
              <div
                className="font-mono tabular-nums text-[22px] font-bold leading-[1.05] text-gold"
                style={{ textShadow: "0 0 34px #ffc63a90" }}
              >
                {champion.score.toFixed(2)}
              </div>
              <div className="font-mono tracking-[0.18em] text-[8px] font-semibold text-gold/80">FINAL SCORE</div>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-[10px]">
        <PickGrid entries={entries} cardsByName={cardsByName} setCode={setCode} />
      </div>

      <div className="flex flex-col gap-1.5 mt-1">
        {runnersUp.map((ballot) => (
          <BroadcastSubBar
            key={ballot.ballotId}
            ballot={ballot}
            accent={ballot.rank === 2 ? MEDAL_COLOR[2] : MEDAL_COLOR[3]}
            isSelf={ballot.ballotId === userBallotId}
            isBest={bestAchieverIds.has(ballot.ballotId)}
            setCode={setCode}
            cardsByName={cardsByName}
            ratingsByName={ratingsByName}
          />
        ))}
        {self && (
          <BroadcastSubBar
            key={self.ballotId}
            ballot={self}
            accent="#2ee85c"
            isSelf
            isBest={bestAchieverIds.has(self.ballotId)}
            setCode={setCode}
            cardsByName={cardsByName}
            ratingsByName={ratingsByName}
          />
        )}
      </div>
    </div>
  );
}

function BroadcastSubBar({
  ballot,
  accent,
  isSelf,
  isBest,
  setCode,
  cardsByName,
  ratingsByName,
}: {
  ballot: RankedBallot;
  accent: string;
  isSelf: boolean;
  isBest: boolean;
  setCode: string;
  cardsByName: Map<string, Card>;
  ratingsByName: Map<string, CardRating>;
}) {
  const [expanded, setExpanded] = useState(false);
  const entries = useMemo(
    () => (expanded ? ballotToEntries(ballot, setCode, ratingsByName) : []),
    [expanded, ballot, setCode, ratingsByName],
  );

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="relative flex items-stretch overflow-hidden cursor-pointer bg-transparent border-0 p-0 text-left"
        style={{
          transform: "skewX(-6deg)",
          marginInline: 10,
          background: "#1d2330",
          border: "1px solid #3b4458",
          borderLeft: 0,
        }}
      >
        <div
          className="flex items-center justify-center shrink-0 px-2"
          style={{ minWidth: 40, background: `linear-gradient(180deg, ${accent}dd, ${accent} 55%, ${accent}aa)` }}
        >
          <span className="font-display text-[19px]" style={{ color: "#0a0c10", transform: "skewX(6deg)" }}>
            {ballot.rank}
          </span>
        </div>
        <div className="flex-1 min-w-0 flex items-center gap-3 py-2 px-4" style={{ transform: "skewX(6deg)" }}>
          <BallotAvatar
            name={ballot.name}
            avatarUrl={ballot.avatarUrl}
            className="w-6 h-6 sm:w-7 sm:h-7 rounded-full shrink-0 object-cover"
            fallbackClassName="w-6 h-6 sm:w-7 sm:h-7 rounded-full shrink-0 bg-surface flex items-center justify-center text-[10px] sm:text-[11px] text-muted font-mono"
            style={{ boxShadow: `0 0 0 1.5px ${accent}` }}
          />
          <span className="flex flex-row items-center gap-1.5 sm:gap-2 flex-1 min-w-0">
            <span className="font-display text-[16px] sm:text-[20px] tracking-[0.04em] truncate min-w-0">
              {ballot.name.toUpperCase()}
            </span>
            {(isSelf || isBest) && (
              <span className="flex items-center gap-1.5 shrink-0">
                {isSelf && <SelfBadge />}
                {isBest && <BestPossibleBadge />}
              </span>
            )}
          </span>
          <span className="font-mono tabular-nums text-[14px] sm:text-[16px] font-bold shrink-0" style={{ color: accent }}>
            {ballot.score.toFixed(2)}
          </span>
          <ChevronDown
            size={14}
            className={`shrink-0 text-muted transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {expanded && (
        <div className="mx-[10px]">
          <PickGrid entries={entries} cardsByName={cardsByName} setCode={setCode} />
        </div>
      )}
    </div>
  );
}

const MEDAL_ROW_STYLE: Record<1 | 2 | 3, { color: string; label: string; tint: string }> = {
  1: { color: MEDAL_COLOR[1], label: "1ST", tint: `linear-gradient(90deg, ${MEDAL_COLOR[1]}12, transparent 55%)` },
  2: { color: MEDAL_COLOR[2], label: "2ND", tint: `linear-gradient(90deg, ${MEDAL_COLOR[2]}12, transparent 55%)` },
  3: { color: MEDAL_COLOR[3], label: "3RD", tint: `linear-gradient(90deg, ${MEDAL_COLOR[3]}12, transparent 55%)` },
};

function MedalRow({
  ballot,
  setCode,
  isSelf,
  maxScore,
  cardsByName,
  ratingsByName,
  rowRef,
  stickyTop = 0,
}: {
  ballot: RankedBallot;
  setCode: string;
  isSelf: boolean;
  maxScore: number;
  cardsByName: Map<string, Card>;
  ratingsByName: Map<string, CardRating>;
  rowRef?: (el: HTMLDivElement | null) => void;
  stickyTop?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const entries = useMemo(
    () => (expanded ? ballotToEntries(ballot, setCode, ratingsByName) : []),
    [expanded, ballot, setCode, ratingsByName],
  );
  const medal = MEDAL_ROW_STYLE[ballot.rank as 1 | 2 | 3];

  return (
    <div
      ref={rowRef}
      className={`border-b border-border2 last:border-b-0 ${isSelf ? "bg-green/[0.07]" : ""}`}
      style={{
        boxShadow: `inset 3px 0 0 ${isSelf ? "#2ee85c" : medal.color}`,
        backgroundImage: isSelf ? undefined : medal.tint,
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 lg:gap-3 px-3 lg:px-4 py-2.5 lg:py-3 text-left cursor-pointer bg-transparent border-0"
      >
        <span
          className="w-7 lg:w-8 shrink-0 text-right font-display tracking-[0.06em] text-[15px] lg:text-[17px]"
          style={{ color: medal.color }}
        >
          {medal.label}
        </span>

        <BallotAvatar
          name={ballot.name}
          avatarUrl={ballot.avatarUrl}
          className="w-6 h-6 lg:w-7 lg:h-7 rounded-full shrink-0 object-cover"
          fallbackClassName="w-6 h-6 lg:w-7 lg:h-7 rounded-full shrink-0 bg-surface flex items-center justify-center text-[10px] lg:text-[11px] text-muted font-mono"
          style={{ boxShadow: `0 0 0 1.5px ${medal.color}` }}
        />

        <div className="flex-1 min-w-0 lg:flex-none lg:w-[150px] lg:shrink-0 flex items-center gap-2">
          <span
            className={`min-w-0 truncate text-[14px] lg:text-[15px] ${isSelf ? "text-white font-semibold" : "text-text"}`}
          >
            {ballot.name}
          </span>
          {isSelf && <SelfBadge />}
        </div>

        <ContributionBar
          ballot={ballot}
          maxScore={maxScore}
          ratingsByName={ratingsByName}
          cardsByName={cardsByName}
          stickyTop={stickyTop}
        />

        <span
          className="font-mono tabular-nums text-[13px] lg:text-[14px] font-semibold shrink-0"
          style={{ color: medal.color }}
        >
          {ballot.score.toFixed(2)}
        </span>

        <ChevronDown
          size={14}
          className={`shrink-0 text-muted transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <div className="px-3 lg:px-4 pb-4 pt-1">
          <PickGrid entries={entries} cardsByName={cardsByName} setCode={setCode} />
        </div>
      )}
    </div>
  );
}

// ── Leaderboard ───────────────────────────────────────────────────────────────

function LeaderboardRow({
  ballot,
  setCode,
  isSelf,
  maxScore,
  cardsByName,
  ratingsByName,
  rowRef,
  stickyTop = 0,
}: {
  ballot: RankedBallot;
  setCode: string;
  isSelf: boolean;
  maxScore: number;
  cardsByName: Map<string, Card>;
  ratingsByName: Map<string, CardRating>;
  rowRef?: (el: HTMLDivElement | null) => void;
  stickyTop?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const entries = useMemo(
    () => (expanded ? ballotToEntries(ballot, setCode, ratingsByName) : []),
    [expanded, ballot, setCode, ratingsByName],
  );

  return (
    <div
      ref={rowRef}
      className={`border-b border-border2 last:border-b-0 ${isSelf ? "bg-green/[0.07] shadow-[inset_3px_0_0_0_#2ee85c]" : ""}`}
      style={{ contentVisibility: "auto", containIntrinsicSize: "auto 52px" }}
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center gap-2 lg:gap-3 px-3 lg:px-4 py-2.5 lg:py-3 text-left cursor-pointer bg-transparent border-0"
      >
        <span className="w-7 lg:w-8 shrink-0 text-right font-mono tabular-nums text-[12px] lg:text-[13px] text-muted">
          #{ballot.rank}
        </span>

        <BallotAvatar
          name={ballot.name}
          avatarUrl={ballot.avatarUrl}
          className="w-6 h-6 lg:w-7 lg:h-7 rounded-full shrink-0 object-cover"
          fallbackClassName="w-6 h-6 lg:w-7 lg:h-7 rounded-full shrink-0 bg-surface flex items-center justify-center text-[10px] lg:text-[11px] text-muted font-mono"
        />

        <div className="flex-1 min-w-0 lg:flex-none lg:w-[150px] lg:shrink-0 flex items-center gap-2">
          <span
            className={`min-w-0 truncate text-[14px] lg:text-[15px] ${isSelf ? "text-white font-semibold" : "text-text"}`}
          >
            {ballot.name}
          </span>
          {isSelf && <SelfBadge />}
        </div>

        {/* bar lives here in the flex row — self-stretch fills full row height */}
        <ContributionBar
          ballot={ballot}
          maxScore={maxScore}
          ratingsByName={ratingsByName}
          cardsByName={cardsByName}
          stickyTop={stickyTop}
        />

        <span className="font-mono tabular-nums text-[13px] lg:text-[14px] text-subtle shrink-0">
          {ballot.score.toFixed(2)}
        </span>

        <ChevronDown
          size={14}
          className={`shrink-0 text-muted transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <div className="px-3 lg:px-4 pb-4 pt-1">
          <PickGrid entries={entries} cardsByName={cardsByName} setCode={setCode} />
        </div>
      )}
    </div>
  );
}

// The signed-in viewer's own standing, pinned to the top of the standings while their
// real row is scrolled out of view. Mirrors FloatingOwnRow in LeaderboardTable.tsx.
function FloatingSelfRow({
  ballot,
  setCode,
  maxScore,
  cardsByName,
  ratingsByName,
  hidden,
  stickyTop,
  onScrollToRow,
}: {
  ballot: RankedBallot | undefined;
  setCode: string;
  maxScore: number;
  cardsByName: Map<string, Card>;
  ratingsByName: Map<string, CardRating>;
  hidden: boolean;
  stickyTop: number;
  onScrollToRow: () => void;
}) {
  if (!ballot || hidden) return null;
  return (
    <div className="sticky z-20 border-b border-border2 bg-surface2" style={{ top: stickyTop }}>
      <div
        onClick={onScrollToRow}
        className="flex items-center gap-2 lg:gap-3 px-3 lg:px-4 py-2.5 lg:py-3 cursor-pointer bg-green/[0.07] shadow-[inset_3px_0_0_0_#2ee85c]"
      >
        <span className="w-7 lg:w-8 shrink-0 text-right font-mono tabular-nums text-[12px] lg:text-[13px] text-muted">
          #{ballot.rank}
        </span>

        <BallotAvatar
          name={ballot.name}
          avatarUrl={ballot.avatarUrl}
          className="w-6 h-6 lg:w-7 lg:h-7 rounded-full shrink-0 object-cover"
          fallbackClassName="w-6 h-6 lg:w-7 lg:h-7 rounded-full shrink-0 bg-surface flex items-center justify-center text-[10px] lg:text-[11px] text-muted font-mono"
        />

        <div className="flex-1 min-w-0 lg:flex-none lg:w-[150px] lg:shrink-0 flex items-center gap-2">
          <span className="min-w-0 truncate text-[14px] lg:text-[15px] text-white font-semibold">
            {ballot.name}
          </span>
          <SelfBadge />
        </div>

        <ContributionBar
          ballot={ballot}
          maxScore={maxScore}
          ratingsByName={ratingsByName}
          cardsByName={cardsByName}
          stickyTop={stickyTop}
        />

        <span className="font-mono tabular-nums text-[13px] lg:text-[14px] text-subtle shrink-0">
          {ballot.score.toFixed(2)}
        </span>

        <ChevronDown
          size={14}
          className={`shrink-0 text-muted transition-transform duration-150`}
        />
      </div>
    </div>
  );
}

const COLLAPSED_COUNT = 3;
const ROW_CHUNK = 30;

function Leaderboard({
  rankedBallots,
  bestTeam,
  crowdTeam,
  setCode,
  userBallotId,
  cardsByName,
  ratingsByName,
  mode = "full",
  onSeeAll,
  stickyTop = 0,
}: {
  rankedBallots: RankedBallot[];
  bestTeam: TeamResult;
  crowdTeam: TeamResult;
  setCode: string;
  userBallotId: number | null;
  cardsByName: Map<string, Card>;
  ratingsByName: Map<string, CardRating>;
  mode?: "peek" | "full";
  onSeeAll?: () => void;
  /** Viewport offset (px) below which the floating self-row pins — clears sticky page chrome. */
  stickyTop?: number;
}) {
  const standings = useMemo(
    () => buildStandingsList(rankedBallots, bestTeam, crowdTeam),
    [rankedBallots, bestTeam, crowdTeam],
  );
  const isPeek = mode === "peek";
  const maxScore = standings.entries.reduce(
    (m, e) => Math.max(m, e.kind === "ballot" ? e.ballot.score : e.standing.team.score),
    1,
  );

  const [selfRowEl, setSelfRowEl] = useState<HTMLDivElement | null>(null);
  const [selfRowVisible, setSelfRowVisible] = useState(true);
  useEffect(() => {
    if (!selfRowEl) {
      setSelfRowVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => setSelfRowVisible(entry.isIntersecting),
      { rootMargin: `${-stickyTop}px 0px 0px 0px`, threshold: 0 },
    );
    observer.observe(selfRowEl);
    return () => observer.disconnect();
  }, [selfRowEl, stickyTop]);

  // Rows mount in chunks as the sentinel approaches the viewport, so a 300-ballot
  // field never pays one synchronous mount of ~8 art crops per row
  const [visibleCount, setVisibleCount] = useState(ROW_CHUNK);
  const [sentinelEl, setSentinelEl] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!sentinelEl) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisibleCount((c) => c + ROW_CHUNK);
      },
      { rootMargin: "1200px 0px" },
    );
    observer.observe(sentinelEl);
    return () => observer.disconnect();
  }, [sentinelEl, visibleCount]);

  const [pendingScrollToSelf, setPendingScrollToSelf] = useState(false);
  useEffect(() => {
    if (pendingScrollToSelf && selfRowEl) {
      selfRowEl.scrollIntoView({ behavior: "smooth", block: "center" });
      setPendingScrollToSelf(false);
    }
  }, [pendingScrollToSelf, selfRowEl]);

  if (isPeek) {
    const champion = rankedBallots.find((b) => b.rank === 1);
    if (!champion) return null;
    const runnersUp = rankedBallots.filter((b) => b.rank === 2 || b.rank === 3);
    const broadcastSelf =
      rankedBallots.find((b) => b.ballotId === userBallotId && b.rank > COLLAPSED_COUNT) ?? null;
    return (
      <div className="flex flex-col gap-3">
        <BroadcastTop3
          champion={champion}
          runnersUp={runnersUp}
          self={broadcastSelf}
          setCode={setCode}
          cardsByName={cardsByName}
          ratingsByName={ratingsByName}
          userBallotId={userBallotId}
          bestAchieverIds={standings.bestAchieverIds}
        />
        {rankedBallots.length > COLLAPSED_COUNT && onSeeAll && (
          <div className="flex justify-center mt-2.5">
            <button
              type="button"
              onClick={onSeeAll}
              className="group inline-flex items-center gap-2 font-mono tracking-[0.16em] text-[11px] text-subtle hover:text-text border border-border2 rounded-sm bg-surface2 hover:bg-surface px-4 py-2 transition-colors"
            >
              SEE FULL STANDINGS
              <ArrowDown size={13} className="transition-transform group-hover:translate-y-0.5" />
            </button>
          </div>
        )}
      </div>
    );
  }

  const selfEntryIndex = standings.entries.findIndex(
    (e) => e.kind === "ballot" && e.ballot.ballotId === userBallotId,
  );
  const selfMounted = selfEntryIndex !== -1 && selfEntryIndex < visibleCount;
  const mountedEntries = standings.entries.slice(0, visibleCount);

  return (
    <div className="relative">
      <div className="border-t border-border2 bg-surface2">
        <FloatingSelfRow
          ballot={rankedBallots.find((b) => b.ballotId === userBallotId)}
          setCode={setCode}
          maxScore={maxScore}
          cardsByName={cardsByName}
          ratingsByName={ratingsByName}
          hidden={selfMounted && selfRowVisible}
          stickyTop={stickyTop}
          onScrollToRow={() => {
            if (selfRowEl) {
              selfRowEl.scrollIntoView({ behavior: "smooth", block: "center" });
              return;
            }
            if (selfEntryIndex === -1) return;
            setVisibleCount((c) => Math.max(c, selfEntryIndex + ROW_CHUNK));
            setPendingScrollToSelf(true);
          }}
        />
        {mountedEntries.map((entry) => {
          if (entry.kind === "synthetic") {
            return (
              <SyntheticRow
                key={`synthetic-${entry.standing.kind}`}
                standing={entry.standing}
                setCode={setCode}
                maxScore={maxScore}
                cardsByName={cardsByName}
                ratingsByName={ratingsByName}
                stickyTop={stickyTop}
              />
            );
          }
          const { ballot } = entry;
          const Row = ballot.rank <= 3 ? MedalRow : LeaderboardRow;
          return (
            <Row
              key={ballot.ballotId}
              ballot={ballot}
              setCode={setCode}
              isSelf={ballot.ballotId === userBallotId}
              maxScore={maxScore}
              cardsByName={cardsByName}
              ratingsByName={ratingsByName}
              rowRef={ballot.ballotId === userBallotId ? setSelfRowEl : undefined}
              stickyTop={stickyTop}
            />
          );
        })}
      </div>
      {visibleCount < standings.entries.length && <div ref={setSentinelEl} className="h-px" />}
    </div>
  );
}

// ── Highlights reel ───────────────────────────────────────────────────────────

const HIGHLIGHT_ACCENT: Record<Highlight["kind"], string> = {
  trap: "#ff5e5e",
  sleeper: "#2ee85c",
};

const HIGHLIGHT_STAMP: Record<Highlight["kind"], string> = {
  trap: "TRAP",
  sleeper: "SLEEPER",
};

const HIGHLIGHT_STAT_LABEL: Record<Highlight["kind"], string> = {
  trap: "BEHIND THE BEST CARD",
  sleeper: "OVER THE CROWD FAVORITE",
};

const TILE_BG = "#181a21";

const VOTER_STACK_MAX = 10;

function ppStat(h: Highlight): string {
  const delta =
    h.kind === "trap" ? h.gihwr - h.slotBestGihwr : h.gihwr - h.crowdFavGihwr;
  const sign = delta < 0 ? "−" : "+";
  return `${sign}${Math.abs(delta * 100).toFixed(1)}`;
}

function shareLabel(share: number): string {
  const pct = Math.round(share * 100);
  return pct === 0 ? "<1%" : `${pct}%`;
}

function joinNames(names: string[]): string {
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function highlightStory(h: Highlight) {
  if (h.kind === "trap") {
    return (
      <>
        <b className="text-subtle font-medium">
          {h.pickCount} {h.pickCount === 1 ? "player" : "players"} ({shareLabel(h.pickShare)})
        </b>{" "}
        picked it
      </>
    );
  }
  if (h.teamCount === 0) {
    return (
      <>
        <b className="text-subtle font-medium">Everyone</b> missed it
      </>
    );
  }
  if (h.teamCount <= 3) {
    return (
      <>
        Only{" "}
        <b className="text-subtle font-medium">
          {joinNames(h.voters.map((v) => v.name))}
        </b>{" "}
        found it
      </>
    );
  }
  return (
    <>
      <b className="text-subtle font-medium">
        {h.teamCount} players ({shareLabel(h.teamShare)})
      </b>{" "}
      picked it
    </>
  );
}

function VoterStack({ voters }: { voters: HighlightVoter[] }) {
  const shown = voters.slice(0, VOTER_STACK_MAX);
  const extra = voters.length - shown.length;
  const ring = "[box-shadow:0_0_0_1.5px_#1d2330,0_0_0_2.5px_#1d2330]";

  return (
    <div className="flex -space-x-1.5">
      {shown.map((v) => (
        <BallotAvatar
          key={v.name}
          name={v.name}
          avatarUrl={v.avatarUrl}
          title={v.name}
          className={`w-[22px] h-[22px] rounded-full shrink-0 ${ring}`}
          fallbackClassName={`w-[22px] h-[22px] rounded-full shrink-0 bg-surface flex items-center justify-center font-mono text-[10px] text-green ${ring}`}
        />
      ))}
      {extra > 0 && (
        <span
          className={`w-[22px] h-[22px] rounded-full shrink-0 bg-surface flex items-center justify-center font-mono text-[9px] text-green ${ring}`}
        >
          +{extra}
        </span>
      )}
    </div>
  );
}

function SprocketRail() {
  return (
    <div
      className="h-2"
      style={{
        backgroundImage: "radial-gradient(circle at 4px 4px, #2a3142 2.6px, transparent 3px)",
        backgroundSize: "22px 8px",
        backgroundRepeat: "repeat-x",
      }}
    />
  );
}

function HighlightTile({
  highlight,
  index,
  cardsByName,
}: {
  highlight: Highlight;
  index: number;
  cardsByName: Map<string, Card>;
}) {
  const card = cardsByName.get(highlight.cardName);
  const accent = HIGHLIGHT_ACCENT[highlight.kind];

  const inner = (
      <div
        className="relative overflow-hidden flex flex-col min-h-[150px] sm:h-full"
        style={{ clipPath: CHAMFER, background: TILE_BG }}
      >
        <div className="absolute inset-y-0 left-0 w-[168px] sm:right-0 sm:w-auto">
          {card && (
            <img
              src={card.imageArtCrop}
              alt={`${highlight.cardName} art`}
              className="w-full h-full sm:h-[176px] object-cover saturate-[0.72] contrast-[1.02]"
            />
          )}
          <div
            className="absolute inset-0 sm:hidden"
            style={{
              background: `linear-gradient(to bottom, ${TILE_BG} 0%, color-mix(in srgb, ${TILE_BG} 45%, transparent) 10%, transparent 22%), linear-gradient(to top, ${TILE_BG} 0%, transparent 14%), linear-gradient(to right, ${TILE_BG} 0%, transparent 12%), linear-gradient(to right, transparent 40%, ${TILE_BG} 92%)`,
            }}
          />
          <div
            className="absolute inset-0 hidden sm:block"
            style={{
              background: `linear-gradient(to bottom, color-mix(in srgb, ${accent} 14%, transparent) 0px, transparent 67px), linear-gradient(to bottom, transparent 53px, ${TILE_BG} 169px)`,
            }}
          />
          {highlight.kind === "sleeper" && highlight.voters.length > 0 && (
            <div className="absolute bottom-1.5 left-2 sm:left-auto sm:right-2 sm:bottom-auto sm:top-[150px] z-10">
              <VoterStack voters={highlight.voters} />
            </div>
          )}
        </div>

        <div className="relative flex-1 flex flex-col ml-[148px] pt-3 pr-4 pb-3.5 sm:ml-0 sm:mt-[124px] sm:pt-0 sm:px-5 sm:pb-4">
          <span
            className="font-display text-[17px] tracking-[0.2em] [text-shadow:0_1px_2px_#000,0_0_5px_#000a]"
            style={{ color: accent }}
          >
            {HIGHLIGHT_STAMP[highlight.kind]}
          </span>

          <div
            className="font-mono font-bold tabular-nums leading-none mt-2 sm:mt-1.5 text-[30px] sm:text-[38px] [text-shadow:0_1px_2px_#000,0_0_5px_#000a,var(--pp-glow)]"
            style={{
              color: accent,
              ["--pp-glow" as string]: `0 0 16px color-mix(in srgb, ${accent} 30%, transparent)`,
            }}
          >
            {ppStat(highlight)}
            <span className="text-[15px] sm:text-[18px]">%</span>
          </div>
          <div className="font-display text-[12px] tracking-[0.2em] text-subtle mt-1">
            {HIGHLIGHT_STAT_LABEL[highlight.kind]}
          </div>

          <div className="font-semibold text-[15.5px] leading-tight mt-2 sm:mt-2.5 truncate">
            {highlight.cardName}
          </div>
          <div className="font-mono text-[11px] text-muted mt-0.5 truncate">
            {highlight.slotLabel}, {gihwrLabel(highlight.gihwr)} GIH
          </div>

          <div className="mt-2.5">
            <p className="text-[12.5px] leading-[1.45] text-subtle">
              {highlightStory(highlight)}
            </p>
          </div>
        </div>
      </div>
  );

  return (
    <div
      className="w-full sm:w-[240px] motion-safe:animate-fadeUpIn relative hover:z-10"
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <article
        className="block sm:h-full transition-transform duration-150 hover:scale-[1.04]"
        style={{
          clipPath: CHAMFER,
          padding: 1,
          background: `linear-gradient(165deg, ${accent} 0%, color-mix(in srgb, ${accent} 28%, #3b4458) 30%, #3b4458 70%, color-mix(in srgb, ${accent} 22%, #3b4458) 100%)`,
        }}
      >
        {card ? (
          <CardImagePreview imageUrl={card.imageNormal} alt={card.name} className="block sm:h-full">
            {inner}
          </CardImagePreview>
        ) : (
          inner
        )}
      </article>
    </div>
  );
}

function HighlightsReel({
  highlights,
  cardsByName,
}: {
  highlights: Highlight[];
  cardsByName: Map<string, Card>;
}) {
  if (highlights.length === 0) return null;

  return (
    <div className="flex flex-col">
      <SectionHeading title="CARD HIGHLIGHTS" />

        <div className="flex flex-col sm:flex-row sm:flex-wrap sm:justify-center gap-3.5 px-1 py-3.5 sm:px-3">
          {highlights.map((h, i) => (
            <HighlightTile
              key={`${h.kind}-${h.slot}-${h.cardName}`}
              highlight={h}
              index={i}
              cardsByName={cardsByName}
            />
          ))}
        </div>
    </div>
  );
}

// ── Orchestrator ──────────────────────────────────────────────────────────────

export function FinalResults({
  ratingsSnapshot,
  pickStats,
  ballots,
  cards,
  cardsByName,
  picksBySlot,
  user,
  hasParticipated,
  stickyTop = 0,
}: {
  ratingsSnapshot: RatingsSnapshot;
  pickStats: P0P1PickStat[];
  ballots: P0P1BallotRow[];
  cards: Card[];
  cardsByName: Map<string, Card>;
  picksBySlot: Map<string, string>;
  user: { discordId?: string } | null;
  hasParticipated: boolean;
  /** Viewport offset (px) below which the FULL RESULTS floating self-row pins — clears sticky page chrome. */
  stickyTop?: number;
}) {
  const { setCode } = ratingsSnapshot;
  const contestSlots = useMemo(() => buildSlots(P0P1_CONTESTS[setCode]), [setCode]);
  const ratingsByName = useMemo(
    () => buildRatingsByName(ratingsSnapshot),
    [ratingsSnapshot],
  );
  const crowdTeam = useMemo(
    () => mostPopularTeam(pickStats, contestSlots, ratingsByName),
    [pickStats, contestSlots, ratingsByName],
  );
  const bestTeam = useMemo(
    () => bestPossibleTeam(cards, contestSlots, ratingsByName),
    [cards, contestSlots, ratingsByName],
  );
  const rankedBallots = useMemo(() => {
    const grouped = groupBallotRows(ballots);
    return rankBallots(grouped, ratingsByName);
  }, [ballots, ratingsByName]);
  const selfPlacement = useP0P1DevSelfPlacement();
  const rankedForDisplay = useMemo(
    () =>
      applyDevSelfPlacement(rankedBallots, 0, bestTeam, p0p1DevEnabled ? selfPlacement : "auto"),
    [rankedBallots, bestTeam, selfPlacement],
  );
  const highlights = useMemo(
    () => highlightsFeed(pickStats, ballots, cards, contestSlots, ratingsByName, HIGHLIGHTS_COUNT),
    [pickStats, ballots, cards, contestSlots, ratingsByName],
  );
  const showYourPicks = Boolean(user) && hasParticipated;

  const userBallot = useMemo(
    () => (showYourPicks ? findUserBallot(rankedForDisplay, picksBySlot, user?.discordId) : null),
    [showYourPicks, rankedForDisplay, picksBySlot, user],
  );

  const fullSectionRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex flex-col gap-8">
      {/* Top-3 broadcast */}
      {rankedForDisplay.length > 0 && (
        <div className="flex flex-col gap-3">
          <SectionHeading title="PODIUM" />
          <Leaderboard
            rankedBallots={rankedForDisplay}
            bestTeam={bestTeam}
            crowdTeam={crowdTeam}
            setCode={setCode}
            userBallotId={userBallot?.ballotId ?? null}
            cardsByName={cardsByName}
            ratingsByName={ratingsByName}
            mode="peek"
            onSeeAll={() => fullSectionRef.current?.scrollIntoView({ behavior: "smooth" })}
            stickyTop={stickyTop}
          />
        </div>
      )}

      <SprocketRail />

      {/* Highlights reel */}
      <HighlightsReel highlights={highlights} cardsByName={cardsByName} />

      <SprocketRail />

      {/* Full standings */}
      {rankedForDisplay.length > 0 && (
        <div
          ref={fullSectionRef}
          className="flex flex-col gap-3 pb-24"
          style={{ scrollMarginTop: stickyTop + 20 }}
        >
          <SectionHeading title="FULL STANDINGS">
            Every player ranked alongside the best possible team and the crowd's picks
          </SectionHeading>
          <Leaderboard
            rankedBallots={rankedForDisplay}
            bestTeam={bestTeam}
            crowdTeam={crowdTeam}
            setCode={setCode}
            userBallotId={userBallot?.ballotId ?? null}
            cardsByName={cardsByName}
            ratingsByName={ratingsByName}
            mode="full"
            stickyTop={stickyTop}
          />
        </div>
      )}
    </div>
  );
}
