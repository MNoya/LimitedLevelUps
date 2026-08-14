import { useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { keyruneClass } from "../Brand";
import { ChevronsRight, LuScrollText, TbCards } from "../Icons";
import { Tooltip } from "../Tooltip";
import { highlightEventLabel } from "./EventLabel";
import { PlayerShield, ShieldFrame } from "./PlayerShield";
import { cn } from "../../lib/utils";
import type { PodSeat } from "../../types/leaderboard";
import type { RoundOutcome } from "./PlayerSeatPanel";

interface Props {
  participants: PodSeat[];
  selectedSeat: number | null;
  highlightedSeat?: number | null;
  highlightedRound?: number | null;
  highlightedOutcome?: RoundOutcome | null;
  onSelect: (seat: number | null) => void;
  onShowDeck?: (p: PodSeat) => void;
  canViewDeck?: (playerSlug: string | null | undefined) => boolean;
  eventLabel: string;
  teamDraft?: boolean;
  eventSlug: string;
  hasDraftLog?: boolean;
  setCode: string;
  formatLabel?: string | null;
  date: string;
  maxWidth?: number | string;
}

const ORBIT_RADIUS_PCT = 39;
const ARROW_ORBIT_PCT = 34.5;
const ARROW_OFFSET_RAD = (2 * Math.PI) / 180;
const ARROW_OFFSET_BY_INDEX: Record<number, number> = {
  1: -ARROW_OFFSET_RAD,
  6: ARROW_OFFSET_RAD,
};
const SHIELD_REF_WIDTH = 640;
const SHIELD_REF_DIMS = { w: 118, h: 144 };

export function PodTable({
  participants,
  selectedSeat,
  highlightedSeat = null,
  highlightedRound = null,
  highlightedOutcome = null,
  onSelect,
  onShowDeck,
  canViewDeck = () => true,
  eventLabel,
  teamDraft = false,
  eventSlug,
  hasDraftLog = false,
  setCode,
  formatLabel,
  date,
  maxWidth = 720,
}: Props) {
  const sorted = [...participants].sort((a, b) => a.seatIndex - b.seatIndex);
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      if (w > 0) setScale(w / SHIELD_REF_WIDTH);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      className="relative mx-auto w-full transition-[max-width] duration-500 ease-out"
      style={{ maxWidth, aspectRatio: "1 / 1", containerType: "inline-size" }}
    >
      <div className="absolute inset-[15%] overflow-hidden rounded-full">
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(circle at 50% 38%, #232a3a 0%, #181d28 28%, #10141c 58%, #070a0f 100%)",
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none mix-blend-overlay opacity-[0.18]"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='240' height='240' filter='url(%23n)'/></svg>\")",
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none rounded-full"
          style={{
            boxShadow:
              "inset 0 0 0 1px #2a3142, inset 0 0 0 5px #0a0c10, inset 0 0 0 6px #2a3142, inset 0 60px 90px -40px rgba(0,0,0,0.85), inset 0 -60px 90px -40px rgba(0,0,0,0.85)",
          }}
        />
      </div>

      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <CenterMedallion
          eventLabel={eventLabel}
          teamDraft={teamDraft}
          setCode={setCode}
          formatLabel={formatLabel}
          date={date}
        />
      </div>

      <PassDirectionArrows seatCount={sorted.length} />

      {selectedSeat != null && highlightedSeat != null && highlightedRound != null && selectedSeat !== highlightedSeat && (
        <PairingLine
          fromSeat={selectedSeat}
          toSeat={highlightedSeat}
          seatCount={sorted.length}
          round={highlightedRound}
          outcome={highlightedOutcome}
        />
      )}

      {sorted.map((p) => {
        const angle = (p.seatIndex / sorted.length) * Math.PI * 2 - Math.PI / 2;
        const x = 50 + Math.cos(angle) * ORBIT_RADIUS_PCT;
        const y = 50 + Math.sin(angle) * ORBIT_RADIUS_PCT;
        const isSelected = selectedSeat === p.seatIndex;
        return (
          <div key={p.displayName}>
            <div
              className="absolute"
              style={{
                left: `${x}%`,
                top: `${y}%`,
                transform: "translate(-50%, -50%)",
              }}
            >
              <PlayerShield
                participant={p}
                selected={isSelected}
                highlighted={!isSelected && highlightedSeat === p.seatIndex}
                highlightedOutcome={highlightedOutcome}
                onClick={() => onSelect(isSelected ? null : p.seatIndex)}
                scale={scale}
              />
            </div>
            {isSelected && onShowDeck && (
              <ShieldActions
                angle={angle}
                participant={p}
                onShowDeck={onShowDeck}
                eventSlug={eventSlug}
                hasDraftLog={hasDraftLog}
                canViewDeck={canViewDeck(p.avatarUrl)}
                scale={scale}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function ShieldActions({
  angle,
  participant,
  onShowDeck,
  eventSlug,
  hasDraftLog,
  canViewDeck,
  scale,
}: {
  angle: number;
  participant: PodSeat;
  onShowDeck: (p: PodSeat) => void;
  eventSlug: string;
  hasDraftLog: boolean;
  canViewDeck: boolean;
  scale: number;
}) {
  const hasDeck = canViewDeck && (!!participant.deckScreenshotUrl || !!participant.hasDeckList);
  const logInternalHref = hasDraftLog && canViewDeck
    ? `/pods/${eventSlug}/${participant.playerSlug ?? participant.seatIndex}`
    : null;
  const showLog = logInternalHref !== null;
  if (!hasDeck && !showLog) return null;

  const orbitX = 50 + Math.cos(angle) * ORBIT_RADIUS_PCT;
  const orbitY = 50 + Math.sin(angle) * ORBIT_RADIUS_PCT;
  const horizontalOffsetPct = 14.5;
  const verticalNudgePct = -3;
  const x = orbitX + horizontalOffsetPct;
  const y = orbitY + verticalNudgePct;
  const btnSize = Math.max(38, 44 * scale);

  return (
    <div
      className="absolute z-30 animate-fadeIn"
      style={{
        left: `${x}%`,
        top: `${y}%`,
        transform: "translate(-50%, -50%)",
      }}
    >
      <div className="flex flex-col gap-2">
        {hasDeck && (
          <Tooltip label="View Deck" side="right">
            <button
              type="button"
              onClick={() => onShowDeck(participant)}
              aria-label="View Deck"
              className="group flex items-center justify-center rounded-full bg-bg border border-border hover:border-green/60 hover:bg-green/10 transition-colors cursor-pointer shadow-[0_4px_10px_rgba(0,0,0,0.55)]"
              style={{ width: btnSize, height: btnSize }}
            >
              <TbCards
                size={Math.round(btnSize * 0.46)}
                aria-hidden="true"
                className="text-text group-hover:text-green transition-colors"
              />
            </button>
          </Tooltip>
        )}
        {showLog && (
          <Tooltip label="View Draft Log" side="right">
            <Link
              to={logInternalHref!}
              aria-label="View Draft Log"
              className="group flex items-center justify-center rounded-full bg-bg border border-border hover:border-green/60 hover:bg-green/10 transition-colors no-underline shadow-[0_4px_10px_rgba(0,0,0,0.55)]"
              style={{ width: btnSize, height: btnSize }}
            >
              <LuScrollText
                size={Math.round(btnSize * 0.46)}
                aria-hidden="true"
                className="text-text group-hover:text-green transition-colors"
              />
            </Link>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

function PairingLine({
  fromSeat,
  toSeat,
  seatCount,
  round,
  outcome,
}: {
  fromSeat: number;
  toSeat: number;
  seatCount: number;
  round: number | null;
  outcome: RoundOutcome | null;
}) {
  const project = (s: number) => {
    const a = (s / seatCount) * Math.PI * 2 - Math.PI / 2;
    return {
      x: 50 + Math.cos(a) * ORBIT_RADIUS_PCT,
      y: 50 + Math.sin(a) * ORBIT_RADIUS_PCT,
    };
  };
  const a = project(fromSeat);
  const b = project(toSeat);
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const tone =
    outcome === "skip" || outcome === "pending" ? "text-muted" : outcome === "loss" ? "text-red" : "text-green";
  const pillBorder =
    outcome === "skip" || outcome === "pending" ? "border-border" : outcome === "loss" ? "border-red/60" : "border-green/60";
  return (
    <>
      <svg
        className={cn("absolute inset-0 w-full h-full pointer-events-none", tone)}
        viewBox="0 0 100 100"
        aria-hidden="true"
      >
        <line
          x1={a.x}
          y1={a.y}
          x2={b.x}
          y2={b.y}
          stroke="currentColor"
          strokeOpacity="0.22"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        <line
          x1={a.x}
          y1={a.y}
          x2={b.x}
          y2={b.y}
          stroke="currentColor"
          strokeOpacity="0.95"
          strokeWidth="0.55"
          strokeLinecap="round"
        />
      </svg>
      {round != null && (
        <div
          className={cn(
            "absolute pointer-events-none font-display bg-bg border leading-none",
            tone,
            pillBorder,
          )}
          style={{
            left: `${mid.x}%`,
            top: `${mid.y}%`,
            transform: "translate(-50%, -50%)",
            padding: "0.55cqw 0.9cqw",
            fontSize: "2.2cqw",
            letterSpacing: "0.18em",
            zIndex: 20,
          }}
        >
          R{round}
        </div>
      )}
    </>
  );
}

function PassDirectionArrows({ seatCount }: { seatCount: number }) {
  return (
    <>
      {Array.from({ length: seatCount }, (_, i) => {
        const midAngle = ((i + 0.5) / seatCount) * Math.PI * 2 - Math.PI / 2 + (ARROW_OFFSET_BY_INDEX[i] ?? 0);
        const x = 50 + Math.cos(midAngle) * ARROW_ORBIT_PCT;
        const y = 50 + Math.sin(midAngle) * ARROW_ORBIT_PCT;
        const tangentDeg = (midAngle * 180) / Math.PI + 90;
        return (
          <div
            key={i}
            className="absolute pointer-events-none"
            style={{
              left: `${x}%`,
              top: `${y}%`,
              width: "3.2cqw",
              height: "3.2cqw",
              transform: `translate(-50%, -50%) rotate(${tangentDeg}deg)`,
            }}
          >
            <ChevronsRight
              className="w-full h-full text-[#c4ccdb] opacity-75"
              strokeWidth={2.5}
              aria-hidden="true"
            />
          </div>
        );
      })}
    </>
  );
}

function CenterMedallion({
  eventLabel,
  teamDraft = false,
  setCode,
  formatLabel,
  date,
}: {
  eventLabel: string;
  teamDraft?: boolean;
  setCode: string;
  formatLabel?: string | null;
  date: string;
}) {
  const { weekday, date: dateLabel } = formatDateParts(date);
  const labelFontSize = medallionFontSize(eventLabel);
  const glyphCode = formatLabel ? "CUBE" : setCode;
  return (
    <div
      className="flex flex-col items-center justify-center text-center select-none"
      style={{ gap: "2.2cqw" }}
    >
      <div className="flex flex-col items-center" style={{ gap: "1cqw" }}>
        <div
          className="font-display text-text leading-none px-2"
          style={{ fontSize: labelFontSize, letterSpacing: "0.02em" }}
        >
          {highlightEventLabel(eventLabel)}
        </div>
        {teamDraft && (
          <div
            className="font-display text-muted leading-none"
            style={{ fontSize: "3cqw", letterSpacing: "0.28em" }}
          >
            TEAM DRAFT
          </div>
        )}
      </div>
      <div className="flex items-center" style={{ gap: "2.2cqw" }}>
        <i
          className={`ss ss-${keyruneClass(glyphCode)} text-white`}
          style={{ fontSize: "8cqw", lineHeight: 1 }}
          aria-hidden="true"
        />
        <span
          className="font-display text-text"
          style={{ fontSize: "5.2cqw", letterSpacing: "0.24em" }}
        >
          {formatLabel ?? setCode}
        </span>
      </div>
      <div
        className="flex items-center justify-center font-display text-muted"
        style={{ fontSize: "2.2cqw", letterSpacing: "0.32em", gap: "1.6cqw" }}
      >
        <span>{weekday}</span>
        <span>{dateLabel}</span>
      </div>
    </div>
  );
}

function medallionFontSize(label: string): string {
  const len = label.length;
  if (len <= 6) return "11cqw";
  if (len <= 10) return "9cqw";
  if (len <= 14) return "7cqw";
  if (len <= 18) return "5.5cqw";
  return "4.5cqw";
}

function formatDateParts(iso: string): { weekday: string; date: string } {
  const d = new Date(iso + "T00:00:00Z");
  const weekday = d.toLocaleString("en-US", { weekday: "short", timeZone: "UTC" }).toUpperCase();
  const month = d.toLocaleString("en-US", { month: "long", timeZone: "UTC" }).toUpperCase();
  return { weekday, date: `${month} ${d.getUTCDate()}, ${d.getUTCFullYear()}` };
}

export function PodTableSkeleton({
  seatCount = 8,
  maxWidth = 720,
}: {
  seatCount?: number;
  maxWidth?: number | string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      if (w > 0) setScale(w / SHIELD_REF_WIDTH);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const w = SHIELD_REF_DIMS.w * scale;
  const h = SHIELD_REF_DIMS.h * scale;
  return (
    <div
      ref={ref}
      className="relative mx-auto w-full"
      style={{ maxWidth, aspectRatio: "1 / 1", containerType: "inline-size" }}
    >
      <div className="absolute inset-[15%] overflow-hidden rounded-full">
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(circle at 50% 38%, #232a3a 0%, #181d28 28%, #10141c 58%, #070a0f 100%)",
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none rounded-full"
          style={{
            boxShadow:
              "inset 0 0 0 1px #2a3142, inset 0 0 0 5px #0a0c10, inset 0 0 0 6px #2a3142, inset 0 60px 90px -40px rgba(0,0,0,0.85), inset 0 -60px 90px -40px rgba(0,0,0,0.85)",
          }}
        />
      </div>
      {Array.from({ length: seatCount }, (_, i) => {
        const angle = (i / seatCount) * Math.PI * 2 - Math.PI / 2;
        const x = 50 + Math.cos(angle) * ORBIT_RADIUS_PCT;
        const y = 50 + Math.sin(angle) * ORBIT_RADIUS_PCT;
        return (
          <div
            key={i}
            className="absolute animate-pulse"
            style={{
              left: `${x}%`,
              top: `${y}%`,
              transform: "translate(-50%, -50%)",
              width: w,
              height: h,
            }}
          >
            <ShieldFrame />
          </div>
        );
      })}
    </div>
  );
}
