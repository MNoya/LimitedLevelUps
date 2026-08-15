import { Fragment, useLayoutEffect, useRef, useState } from "react";
import { Pips } from "../ManaPips";
import { Record } from "../Record";
import { keyruneClass, Trophy } from "../Brand";
import { cn } from "../../lib/utils";
import { HeroSection } from "../HeroSection";
import { type DeckTab } from "./DeckScreenshotModal";
import { highlightEventLabel } from "./EventLabel";
import { PlayerSeatPanel } from "./PlayerSeatPanel";
import { PodStandings, PodStandingsSkeleton, recordParts, StandingsBackBar, type PodStandingsActions } from "./PodStandings";
import { isPodTrophyRecord } from "../../data/utils";
import type { PodEventMatchRow, PodEventReplayRow, PodSeat } from "../../types/leaderboard";

interface Props {
  participants: PodSeat[];
  participantsBySeatName: Map<string, PodSeat>;
  matches: PodEventMatchRow[];
  replays: PodEventReplayRow[];
  selectedSeat: number | null;
  onSelect: (seat: number | null) => void;
  onShowDeck: (p: PodSeat, tab?: DeckTab) => void;
  canViewSeat?: (playerSlug: string | null | undefined) => boolean;
  podFinalized?: boolean;
  eventLabel: string;
  setCode: string;
  eventSlug: string;
  hasDraftLog: boolean;
  formatLabel?: string | null;
  isMock?: boolean;
  standingsAvailable?: boolean;
  teamDraft?: boolean;
  standingsActions?: PodStandingsActions;
}

const GRID_REF_WIDTH = 380;
const GRID_MAX_WIDTH = 560;
const REF_TILE = { w: 74, h: 64 };
const REF_ARROW = 16;

export function MobileSeatStackSkeleton({
  seatCount = 8,
  variant = "standings",
  finalized = true,
  teamDraft = false,
}: {
  seatCount?: number;
  variant?: "player" | "standings";
  finalized?: boolean;
  teamDraft?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      if (w > 0) setScale(w / GRID_REF_WIDTH);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const cols = Math.ceil(seatCount / 2);
  const topCount = cols;
  const bottomCount = seatCount - cols;
  const tileW = REF_TILE.w * scale;
  const tileH = REF_TILE.h * scale;

  return (
    <div className="flex flex-col">
      <HeroSection className="px-[18px] pt-5 pb-5">
        <div
          ref={ref}
          className="w-full mx-auto"
          style={{ maxWidth: GRID_MAX_WIDTH }}
        >
          <SkeletonRow count={topCount} tileW={tileW} tileH={tileH} scale={scale} />
          <div
            className="flex items-center justify-between gap-2"
            style={{ paddingTop: 10 * scale, paddingBottom: 10 * scale }}
          >
            <div style={{ width: tileW }} />
            <div
              className="h-3 bg-surface2 animate-pulse"
              style={{ width: 120 * scale }}
            />
            <div style={{ width: tileW }} />
          </div>
          <SkeletonRow count={bottomCount} tileW={tileW} tileH={tileH} scale={scale} />
        </div>
      </HeroSection>
      {variant === "standings" ? (
        <div className="bg-surface">
          <PodStandingsSkeleton rows={seatCount} finalized={finalized} teamDraft={teamDraft} />
        </div>
      ) : (
        <div className="bg-surface border-b border-border px-4 py-4 flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <div className="w-[52px] h-[52px] bg-surface2 animate-pulse shrink-0" />
            <div className="flex flex-col gap-2 min-w-0 flex-1">
              <div className="h-6 w-2/3 bg-surface2 animate-pulse" />
              <div className="h-3 w-1/3 bg-surface2 animate-pulse" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-[38px] flex-1 bg-surface2 animate-pulse" />
            <div className="h-[38px] flex-1 bg-surface2 animate-pulse" />
          </div>
        </div>
      )}
    </div>
  );
}

function SkeletonRow({
  count,
  tileW,
  tileH,
  scale,
}: {
  count: number;
  tileW: number;
  tileH: number;
  scale: number;
}) {
  return (
    <div className="flex items-center justify-between">
      {Array.from({ length: count }, (_, i) => (
        <Fragment key={i}>
          <div
            className="bg-surface2 border border-border animate-pulse"
            style={{ width: tileW, height: tileH }}
          />
          {i < count - 1 && (
            <div
              className="bg-surface2 animate-pulse"
              style={{ width: REF_ARROW * scale, height: 2 * scale }}
            />
          )}
        </Fragment>
      ))}
    </div>
  );
}

export function MobileSeatStack({
  participants,
  participantsBySeatName,
  matches,
  replays,
  selectedSeat,
  onSelect,
  onShowDeck,
  canViewSeat = () => true,
  podFinalized = true,
  eventLabel,
  setCode,
  eventSlug,
  hasDraftLog,
  formatLabel,
  isMock = false,
  standingsAvailable = false,
  teamDraft = false,
  standingsActions,
}: Props) {
  const sorted = [...participants].sort((a, b) => a.seatIndex - b.seatIndex);
  const selected = selectedSeat == null
    ? null
    : participants.find((p) => p.seatIndex === selectedSeat) ?? null;
  const showStandings = standingsAvailable && !!standingsActions && selected == null;

  return (
    <div className="flex flex-col">
      <HeroSection className="px-[18px] pt-5 pb-5">
        <TileGrid
          participants={sorted}
          selectedSeat={selectedSeat}
          onSelect={onSelect}
          eventLabel={eventLabel}
          setCode={setCode}
          formatLabel={formatLabel}
        />
      </HeroSection>

      {standingsAvailable && standingsActions && (
        <div
          className="grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none"
          style={{ gridTemplateRows: showStandings ? "1fr" : "0fr" }}
        >
          <div className="overflow-hidden">
            <div className="bg-surface">
              <PodStandings
                seats={participants}
                teamDraft={teamDraft}
                finalized={podFinalized}
                selectedSeat={selectedSeat}
                onSelect={onSelect}
                actions={standingsActions}
              />
            </div>
          </div>
        </div>
      )}

      <div
        className="grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none"
        style={{ gridTemplateRows: selected ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          {selected && (
            <div className="bg-surface">
              {standingsAvailable && <StandingsBackBar onClick={() => onSelect(null)} />}
              <PlayerSeatPanel
                key={selected.displayName}
                participant={selected}
                participantsBySeatName={participantsBySeatName}
                matches={matches}
                replays={replays}
                setCode={setCode}
                eventSlug={eventSlug}
                hasDraftLog={hasDraftLog}
                canViewSeat={canViewSeat}
                podFinalized={podFinalized}
                onShowDeck={onShowDeck}
                isMock={isMock}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TileGrid({
  participants,
  selectedSeat,
  onSelect,
  eventLabel,
  setCode,
  formatLabel,
}: {
  participants: PodSeat[];
  selectedSeat: number | null;
  onSelect: (seat: number | null) => void;
  eventLabel: string;
  setCode: string;
  formatLabel?: string | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      if (w > 0) setScale(w / GRID_REF_WIDTH);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const n = participants.length;
  const cols = Math.ceil(n / 2);
  const topRow = participants.slice(0, cols);
  const bottomRow = participants.slice(cols).reverse();
  const tileW = REF_TILE.w * scale;

  return (
    <div
      ref={ref}
      className="w-full mx-auto"
      style={{ maxWidth: GRID_MAX_WIDTH }}
    >
      <TileRow
        tiles={topRow}
        arrowDir="right"
        selectedSeat={selectedSeat}
        onSelect={onSelect}
        scale={scale}
      />
      <div
        className="flex items-center justify-between gap-2"
        style={{ paddingTop: 10 * scale, paddingBottom: 10 * scale }}
      >
        <div style={{ width: tileW, display: "flex", justifyContent: "center" }}>
          <PassChevron direction="up" scale={scale} />
        </div>
        <div
          className="flex items-center text-text font-display min-w-0 px-1"
          style={{
            gap: 6 * scale,
            fontSize: Math.round(mobileLabelFontSize(eventLabel) * scale),
          }}
        >
          <i
            className={`ss ss-${keyruneClass(formatLabel ? "CUBE" : setCode)} text-text shrink-0`}
            style={{ fontSize: Math.round(20 * scale), lineHeight: 1 }}
            aria-hidden="true"
          />
          <span className="truncate">{highlightEventLabel(eventLabel)}</span>
        </div>
        <div style={{ width: tileW, display: "flex", justifyContent: "center" }}>
          <PassChevron direction="down" scale={scale} />
        </div>
      </div>
      <TileRow
        tiles={bottomRow}
        arrowDir="left"
        selectedSeat={selectedSeat}
        onSelect={onSelect}
        scale={scale}
      />
    </div>
  );
}

function TileRow({
  tiles,
  arrowDir,
  selectedSeat,
  onSelect,
  scale,
}: {
  tiles: PodSeat[];
  arrowDir: "right" | "left";
  selectedSeat: number | null;
  onSelect: (seat: number | null) => void;
  scale: number;
}) {
  return (
    <div className="flex items-center justify-between">
      {tiles.map((p, i) => (
        <Fragment key={p.displayName}>
          <PlayerTile
            participant={p}
            selected={selectedSeat === p.seatIndex}
            onClick={() => onSelect(p.seatIndex)}
            scale={scale}
          />
          {i < tiles.length - 1 && <PassChevron direction={arrowDir} scale={scale} />}
        </Fragment>
      ))}
    </div>
  );
}

function PassChevron({
  direction,
  scale,
}: {
  direction: "right" | "left" | "up" | "down";
  scale: number;
}) {
  const rotation =
    direction === "right" ? 0 : direction === "down" ? 90 : direction === "left" ? 180 : 270;
  const size = REF_ARROW * scale;
  return (
    <div
      className="pointer-events-none"
      style={{
        width: size,
        height: size,
        transform: `rotate(${rotation}deg)`,
      }}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" className="w-full h-full">
        <path
          d="M 4 7 L 11 12 L 4 17 M 13 7 L 20 12 L 13 17"
          fill="none"
          stroke="#c4ccdb"
          strokeOpacity="0.75"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}

function PlayerTile({
  participant,
  selected,
  onClick,
  scale,
}: {
  participant: PodSeat;
  selected: boolean;
  onClick: () => void;
  scale: number;
}) {
  const { wins, losses, played: hasRecord } = recordParts(participant.record);
  const isWinner = isPodTrophyRecord(participant.record) || participant.placement === 1;
  const w = REF_TILE.w * scale;
  const h = REF_TILE.h * scale;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      aria-label={`Seat ${participant.seatIndex + 1}: ${participant.discordName}${hasRecord ? `, ${participant.record}` : ""}`}
      className={cn(
        "block p-0 m-0 bg-surface border transition-colors text-left",
        selected
          ? "border-green bg-surface2"
          : isWinner
            ? "border-border2"
            : "border-border hover:border-border2",
      )}
      style={{
        width: w,
        height: h,
        boxShadow: selected ? "0 0 12px -2px rgba(46, 232, 92, 0.35)" : undefined,
      }}
    >
      <div className="h-full flex flex-col items-center justify-between" style={{ paddingTop: 5 * scale, paddingBottom: 5 * scale }}>
        {participant.deckColors ? (
          <Pips colors={participant.deckColors} size={Math.round(10 * scale)} />
        ) : (
          <div style={{ height: Math.round(10 * scale) }} />
        )}
        <div
          className="flex items-center justify-center gap-1 w-full px-1 min-w-0"
        >
          {isWinner && (
            <Trophy
              size={Math.round(10 * scale)}
              color="#ffc63a"
              className="shrink-0"
            />
          )}
          <span
            className="font-display leading-none uppercase truncate text-text"
            style={{
              fontSize: Math.round(12 * scale),
              letterSpacing: "0.02em",
              fontFamily: "'Bebas Neue', sans-serif",
            }}
          >
            {participant.discordName}
          </span>
        </div>
        {hasRecord ? (
          <div
            className="tabular-nums leading-none text-text"
            style={{
              fontSize: Math.round(12 * scale),
              letterSpacing: "0.06em",
              fontFamily: "'Bebas Neue', sans-serif",
            }}
          >
            <Record wins={wins} losses={losses} mono separatorMargin={2} />
          </div>
        ) : (
          <div style={{ height: Math.round(12 * scale) }} />
        )}
      </div>
    </button>
  );
}

function mobileLabelFontSize(label: string): number {
  const len = label.length;
  if (len <= 8) return 18;
  if (len <= 14) return 16;
  if (len <= 20) return 14;
  return 12;
}

