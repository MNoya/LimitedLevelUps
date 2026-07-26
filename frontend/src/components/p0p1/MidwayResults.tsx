import { useMemo, useState } from "react";
import { HelpCircle } from "lucide-react";
import { Tooltip } from "../Tooltip";
import { cn } from "../../lib/utils";
import { PickGrid } from "./CommunityGrid";
import { MidwayBreakdownList } from "./MidwayBreakdownList";
import { useMidwayVersusPager, MidwayVersusModal } from "./MidwayVersusCard";
import { SLOTS } from "../../data/p0p1Slots";
import {
  buildRatingsByName,
  scoreBallot,
  bestPossibleTeam,
  mostPopularTeam,
  buildMidwaySlotVersus,
  gihwrBounds,
  GIH_SAMPLE_FLOOR,
} from "../../data/p0p1Results";
import type { RatingsSnapshot, TeamPick, CardRating } from "../../data/p0p1Results";
import type { Card, P0P1PickStat, SlotKey } from "../../types/p0p1";
import type { PickEntry } from "./CommunityGrid";

const GREEN = "#2ee85c";

function gihwrLabel(gihwr: number): string {
  return `${(gihwr * 100).toFixed(1)}%`;
}

function teamToEntries(picks: TeamPick[], setCode: string): PickEntry[] {
  const bySlot = new Map(picks.map((p) => [p.slot, p]));
  return SLOTS.map((slot) => {
    const pick = bySlot.get(slot.key);
    if (!pick?.cardName) return { slotKey: slot.key, label: slot.label, stats: [] };
    return {
      slotKey: slot.key,
      label: slot.label,
      stats: [{ setCode, slot: slot.key, cardName: pick.cardName, pickCount: 0, pickPct: 0 }],
      pctLabel: pick.gihwr > 0 ? gihwrLabel(pick.gihwr) : "—",
    };
  });
}

function yourPicksEntries(
  picksBySlot: Map<string, string>,
  setCode: string,
  ratingsByName: Map<string, CardRating>,
): PickEntry[] {
  return SLOTS.map((slot) => {
    const cardName = picksBySlot.get(slot.key);
    if (!cardName) return { slotKey: slot.key, label: slot.label, stats: [] };
    const rating = ratingsByName.get(cardName);
    const gihwr =
      rating && rating.gih >= GIH_SAMPLE_FLOOR && rating.gihwr !== null ? rating.gihwr : null;
    return {
      slotKey: slot.key,
      label: slot.label,
      stats: [{ setCode, slot: slot.key, cardName, pickCount: 0, pickPct: 0 }],
      pctLabel: gihwr !== null ? gihwrLabel(gihwr) : "—",
    };
  });
}

export function MidwayResults({
  ratingsSnapshot,
  pickStats,
  cards,
  cardsByName,
  picksBySlot,
  user,
  hasParticipated,
}: {
  ratingsSnapshot: RatingsSnapshot;
  pickStats: P0P1PickStat[];
  cards: Card[];
  cardsByName: Map<string, Card>;
  picksBySlot: Map<string, string>;
  user: object | null;
  hasParticipated: boolean;
}) {
  const { setCode } = ratingsSnapshot;
  const ratingsByName = useMemo(() => buildRatingsByName(ratingsSnapshot), [ratingsSnapshot]);
  const bounds = useMemo(() => gihwrBounds(pickStats, ratingsByName), [pickStats, ratingsByName]);
  const crowdTeam = useMemo(
    () => mostPopularTeam(pickStats, SLOTS, ratingsByName),
    [pickStats, ratingsByName],
  );
  const bestTeam = useMemo(
    () => bestPossibleTeam(cards, SLOTS, ratingsByName),
    [cards, ratingsByName],
  );

  const showYourPicks = Boolean(user) && hasParticipated;
  const [topView, setTopView] = useState<TopView>("yours");
  const viewingYours = showYourPicks && topView === "yours";

  const yourScore = showYourPicks ? scoreBallot(picksBySlot as Map<SlotKey, string>, ratingsByName) : 0;

  const yourEntries = useMemo(
    () => (showYourPicks ? yourPicksEntries(picksBySlot, setCode, ratingsByName) : []),
    [showYourPicks, picksBySlot, setCode, ratingsByName],
  );
  const crowdEntries = useMemo(() => teamToEntries(crowdTeam.picks, setCode), [crowdTeam.picks, setCode]);
  const bestEntries = useMemo(() => teamToEntries(bestTeam.picks, setCode), [bestTeam.picks, setCode]);

  const versusList = useMemo(
    () =>
      buildMidwaySlotVersus(SLOTS, picksBySlot, crowdTeam, bestTeam, ratingsByName, cardsByName, showYourPicks),
    [picksBySlot, crowdTeam, bestTeam, ratingsByName, cardsByName, showYourPicks],
  );
  const pager = useMidwayVersusPager(versusList);

  const onSlotOpen = (slotKey: SlotKey) => {
    const idx = SLOTS.findIndex((s) => s.key === slotKey);
    if (idx !== -1) pager.open(idx);
  };

  const yourCardBySlot = useMemo(
    () => (showYourPicks ? (picksBySlot as Map<SlotKey, string>) : new Map<SlotKey, string>()),
    [showYourPicks, picksBySlot],
  );

  return (
    <div className="flex flex-col gap-3 lg:gap-6">
      <TeamRow
        label={viewingYours ? "YOUR PICKS" : "CROWD PICKS"}
        labelToggle={showYourPicks}
        labelColor="#ffffff"
        score={viewingYours ? yourScore : crowdTeam.score}
        entries={viewingYours ? yourEntries : crowdEntries}
        cardsByName={cardsByName}
        setCode={setCode}
        onTileOpen={onSlotOpen}
        aligned={showYourPicks}
        toggle={showYourPicks ? { viewingYours, onClick: () => setTopView(topView === "yours" ? "crowd" : "yours") } : undefined}
      />

      <TeamRow
        label="BEST POSSIBLE"
        labelColor={GREEN}
        score={bestTeam.score}
        scoreColor="text-green"
        showHelp={false}
        aligned={showYourPicks}
        entries={bestEntries}
        cardsByName={cardsByName}
        setCode={setCode}
        onTileOpen={onSlotOpen}
      />

      <MidwayVersusModal pager={pager} bounds={bounds} />

      <MidwayBreakdownList
        cards={cards}
        cardsByName={cardsByName}
        ratingsByName={ratingsByName}
        yourCardBySlot={yourCardBySlot}
        pickStats={pickStats}
        bounds={bounds}
        setCode={setCode}
      />
    </div>
  );
}

type TopView = "yours" | "crowd";
interface Toggle {
  viewingYours: boolean;
  onClick: () => void;
}

const TOP_LABELS = ["YOUR PICKS", "CROWD PICKS"];

function TeamRow({
  label,
  labelToggle = false,
  labelColor,
  score,
  scoreColor = "text-subtle",
  showHelp = true,
  entries,
  cardsByName,
  setCode,
  onTileOpen,
  toggle,
  aligned = false,
}: {
  label: string;
  labelToggle?: boolean;
  labelColor: string;
  score: number;
  scoreColor?: string;
  showHelp?: boolean;
  entries: PickEntry[];
  cardsByName: Map<string, Card>;
  setCode?: string;
  onTileOpen: (slotKey: SlotKey) => void;
  toggle?: Toggle;
  aligned?: boolean;
}) {
  const labelEl = (
    <span
      className="whitespace-nowrap font-display leading-none tracking-[0.12em] text-[18px] lg:tracking-[0.22em] lg:text-[20px]"
      style={{ color: labelColor }}
    >
      {labelToggle ? <StableText options={TOP_LABELS} active={label} /> : label}
    </span>
  );
  const scoreEl = <ScoreDisplay score={score} scoreColor={scoreColor} showHelp={showHelp} />;
  const toggleEl = toggle ? <CrowdToggle toggle={toggle} /> : null;

  return (
    <div>
      {aligned ? (
        <div className="mb-1.5 grid grid-cols-[1fr_auto_1fr] items-center gap-2 lg:hidden">
          <div className="justify-self-start pl-1">{labelEl}</div>
          <div className="justify-self-center">{scoreEl}</div>
          <div className="justify-self-end">{toggleEl}</div>
        </div>
      ) : (
        <div className="mb-1.5 flex items-center justify-center gap-6 lg:hidden">
          {labelEl}
          {scoreEl}
        </div>
      )}

      <div className="mb-2 hidden items-baseline lg:grid lg:grid-cols-[1fr_auto_1fr] lg:gap-5">
        <div className="lg:col-start-2">{labelEl}</div>
        <div className="flex items-baseline gap-4 lg:col-start-3 lg:justify-self-start">
          {scoreEl}
          {toggleEl}
        </div>
      </div>

      <PickGrid entries={entries} cardsByName={cardsByName} setCode={setCode} onTileOpen={onTileOpen} />
    </div>
  );
}

function ScoreDisplay({ score, scoreColor, showHelp }: { score: number; scoreColor: string; showHelp: boolean }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className={cn("font-mono text-[16px] font-semibold leading-none tabular-nums lg:text-[20px]", scoreColor)}>
        {score.toFixed(1)}
      </span>
      {showHelp && (
        <Tooltip label="Game In Hand Win Rate" side="top">
          <button type="button" className="inline-flex cursor-help items-center self-center border-0 bg-transparent p-0 text-muted">
            <HelpCircle size={16} />
          </button>
        </Tooltip>
      )}
    </span>
  );
}

function CrowdToggle({ toggle }: { toggle: Toggle }) {
  const full = toggle.viewingYours ? "VIEW CROWD PICKS" : "VIEW YOUR PICKS";
  const short = toggle.viewingYours ? "VIEW CROWD" : "VIEW YOURS";
  return (
    <button
      type="button"
      onClick={toggle.onClick}
      className="rounded border border-border2 px-2.5 py-1 font-display text-[13px] tracking-[0.12em] text-subtle transition-colors hover:border-green hover:text-green"
    >
      <StableText options={["VIEW CROWD PICKS", "VIEW YOUR PICKS"]} active={full} className="hidden lg:grid" />
      <StableText options={["VIEW CROWD", "VIEW YOURS"]} active={short} className="grid lg:hidden" />
    </button>
  );
}

function StableText({ options, active, className }: { options: string[]; active: string; className?: string }) {
  return (
    <span className={cn("grid justify-items-center", className)}>
      {options.map((option) => (
        <span
          key={option}
          aria-hidden={option !== active}
          className={cn("col-start-1 row-start-1", option === active ? "" : "invisible")}
        >
          {option}
        </span>
      ))}
    </span>
  );
}
