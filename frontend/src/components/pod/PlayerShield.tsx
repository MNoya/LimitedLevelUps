import { type CSSProperties, useId, useLayoutEffect, useRef } from "react";
import { Pips } from "../ManaPips";
import { useIsLandscapePhone } from "../../lib/use-is-mobile";
import { Record } from "../Record";
import { cn } from "../../lib/utils";
import { isPodTrophyRecord } from "../../data/utils";
import { recordParts } from "./PodStandingRow";
import type { PodSeat } from "../../types/leaderboard";
import type { RoundOutcome } from "./PlayerSeatPanel";

export const SHIELD_VIEWBOX = "0 0 100 122";
export const SHIELD_RATIO = 100 / 122;
const FRAME_PATH = "M 0 0 H 100 V 60 C 100 80, 85 100, 50 122 C 15 100, 0 80, 0 60 Z";
const GROOVE_PATH = "M 3.2 3.2 H 96.8 V 60 C 96.8 77.4, 83.4 96.8, 50 117.2 C 16.6 96.8, 3.2 77.4, 3.2 60 Z";
const FACE_PATH = "M 5.2 5.2 H 94.8 V 60 C 94.8 76.4, 82.4 94.8, 50 114.2 C 17.6 94.8, 5.2 76.4, 5.2 60 Z";

interface Metal {
  hi: string;
  mid: string;
  low: string;
  deep: string;
  edge: string;
}
const SILVER: Metal = { hi: "#f4f7fc", mid: "#c6cedb", low: "#8a93a6", deep: "#535c6e", edge: "#3a4150" };
const GOLD: Metal = { hi: "#fff3cc", mid: "#ffd96e", low: "#cf9a2c", deep: "#855a12", edge: "#5a3d0c" };
const READABLE_TEXT: CSSProperties = {
  WebkitTextStroke: "1px rgba(0,0,0,0.92)",
  paintOrder: "stroke",
  textShadow: "0 0 3px rgba(0,0,0,0.85), 0 1px 1px rgba(0,0,0,0.9)",
};

export function ShieldFrame({
  metal = SILVER,
  ring = null,
  elevated = false,
  layer = "full",
}: {
  metal?: Metal;
  ring?: string | null;
  elevated?: boolean;
  layer?: "full" | "base" | "border";
}) {
  const uid = useId().replace(/:/g, "");
  const showBase = layer !== "border";
  const showBorder = layer !== "base";
  return (
    <svg
      viewBox={SHIELD_VIEWBOX}
      preserveAspectRatio="none"
      className="absolute inset-0 w-full h-full overflow-visible pointer-events-none"
      aria-hidden="true"
      style={{
        filter: !showBase
          ? "none"
          : elevated
            ? "drop-shadow(0 8px 14px rgba(0, 0, 0, 0.55))"
            : "drop-shadow(0 4px 8px rgba(0, 0, 0, 0.5))",
      }}
    >
      <defs>
        <linearGradient id={`fr-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={metal.hi} />
          <stop offset="22%" stopColor={metal.mid} />
          <stop offset="55%" stopColor={metal.low} />
          <stop offset="100%" stopColor={metal.deep} />
        </linearGradient>
        <linearGradient id={`lip-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={metal.hi} />
          <stop offset="100%" stopColor={metal.low} />
        </linearGradient>
        <linearGradient id={`face-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#181d27" />
          <stop offset="55%" stopColor="#10141c" />
          <stop offset="100%" stopColor="#06080d" />
        </linearGradient>
      </defs>
      {showBase && (
        <>
          <path d={FRAME_PATH} fill={`url(#fr-${uid})`} />
          <path d={FRAME_PATH} fill="none" stroke={metal.edge} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
          <path d={GROOVE_PATH} fill="#06080d" />
          <path d={FACE_PATH} fill={`url(#face-${uid})`} />
        </>
      )}
      {showBorder && (
        <>
          <path d={FACE_PATH} fill="none" stroke={`url(#lip-${uid})`} strokeWidth={2} strokeOpacity={0.85} vectorEffect="non-scaling-stroke" />
          {ring && <path d={FACE_PATH} fill="none" stroke={ring} strokeWidth={2.4} vectorEffect="non-scaling-stroke" />}
        </>
      )}
    </svg>
  );
}

interface Props {
  participant: PodSeat;
  selected: boolean;
  highlighted?: boolean;
  highlightedOutcome?: RoundOutcome | null;
  onClick: () => void;
  scale?: number;
}

const REF = { w: 118, h: 144, nameMax: 17, nameMin: 10, pip: 13, rec: 20 };

export function PlayerShield({ participant, selected, highlighted = false, highlightedOutcome = null, onClick, scale = 1 }: Props) {
  const { wins, losses, played: hasRecord } = recordParts(participant.record);
  const isWinner = isPodTrophyRecord(participant.record) || participant.placement === 1;
  const raiseForName = useIsLandscapePhone();
  const dims = {
    w: REF.w * scale,
    h: REF.h * scale,
    nameMax: raiseForName ? Math.max(REF.nameMax * scale, 13) : REF.nameMax * scale,
    nameMin: raiseForName ? Math.max(REF.nameMin * scale, 10) : REF.nameMin * scale,
    pip: REF.pip * scale,
    rec: REF.rec * scale,
  };

  const metal = isWinner ? GOLD : SILVER;
  const isHighlight = highlighted && !selected;
  const ring =
    (selected || isHighlight) && highlightedOutcome != null
      ? outcomeRingColor(selected, highlightedOutcome)
      : null;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      aria-label={`Seat ${participant.seatIndex + 1}: ${participant.discordName}${hasRecord ? `, ${participant.record}` : ""}`}
      className={cn(
        "group relative block p-0 m-0 border-0 bg-transparent cursor-pointer outline-none",
        "transition-transform duration-300 ease-out will-change-transform",
        selected
          ? "-translate-y-2.5 scale-[1.04]"
          : "hover:-translate-y-1.5 hover:scale-[1.025]",
      )}
      style={{ width: dims.w, height: dims.h }}
    >
      <ShieldFrame metal={metal} elevated={selected} layer="base" />
      <div
        className="absolute inset-0 flex flex-col items-center"
        style={{
          paddingTop: dims.h * 0.05,
          paddingBottom: dims.h * 0.14,
          paddingLeft: dims.w * 0.06,
          paddingRight: dims.w * 0.06,
        }}
      >
        <AvatarWindow
          displayName={participant.discordName}
          avatarUrl={participant.avatarUrl}
          radius={Math.max(3, 6 * scale)}
        />
        {participant.deckColors && (
          <div className="shrink-0 z-10" style={{ marginTop: -dims.pip * (raiseForName ? 1.15 : 0.5) }}>
            <Pips colors={participant.deckColors} size={dims.pip} />
          </div>
        )}
        <div className="flex-1 flex items-center justify-center w-full min-h-0 overflow-hidden px-0.5">
          <FitName
            text={participant.discordName}
            maxSize={dims.nameMax}
            minSize={dims.nameMin}
            maxLines={2}
            className="leading-none uppercase text-text text-center"
          />
        </div>
        {hasRecord && (
          <div
            className="shrink-0 tabular-nums leading-none text-text"
            style={{ fontSize: dims.rec, letterSpacing: "0.04em", fontFamily: "'Bebas Neue', sans-serif", ...READABLE_TEXT }}
          >
            <Record wins={wins} losses={losses} mono separatorMargin={3} />
          </div>
        )}
      </div>
      <ShieldFrame metal={metal} ring={ring} layer="border" />
    </button>
  );
}

function AvatarWindow({
  displayName,
  avatarUrl,
  radius,
}: {
  displayName: string;
  avatarUrl: string | null;
  radius: number;
}) {
  const initials = displayName
    .split(/[\s\-_().]+/)
    .filter(Boolean)
    .map((s) => s[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div
      className="relative w-full overflow-hidden shrink-0"
      style={{
        aspectRatio: "5 / 3",
        containerType: "inline-size",
        background: "radial-gradient(circle at 50% 32%, #2a3142 0%, #161b25 55%, #090c12 100%)",
      }}
    >
      {avatarUrl ? (
        <img src={avatarUrl} alt={displayName} className="absolute inset-0 w-full h-full object-cover" />
      ) : (
        <span className="absolute inset-0 flex items-center justify-center font-display text-muted" style={{ fontSize: "44cqw", letterSpacing: "0.04em" }}>
          {initials}
        </span>
      )}
    </div>
  );
}

function outcomeRingColor(selected: boolean, outcome: RoundOutcome): string {
  const GREEN = "#2ee85c";
  const RED = "#ff5e5e";
  const MUTED = "#7a849a";
  if (outcome === "skip" || outcome === "pending") return MUTED;
  const won = outcome === "win";
  if (selected) return won ? GREEN : RED;
  return won ? RED : GREEN;
}

function FitName({
  text,
  maxSize,
  minSize,
  maxLines = 2,
  className,
}: {
  text: string;
  maxSize: number;
  minSize: number;
  maxLines?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const parent = el.parentElement;
    if (!parent) return;
    const canWrap = /\s/.test(text);
    const fit = () => {
      const avail = parent.clientWidth;
      if (avail <= 0) return;

      el.style.setProperty("-webkit-line-clamp", "");
      el.style.display = "block";
      el.style.whiteSpace = "nowrap";
      el.style.fontSize = `${maxSize}px`;
      if (el.scrollWidth <= avail) return;

      if (canWrap) {
        el.style.whiteSpace = "normal";
        el.style.display = "-webkit-box";
        el.style.setProperty("-webkit-box-orient", "vertical");
        el.style.setProperty("-webkit-line-clamp", String(maxLines));
        const availHeight = parent.clientHeight;
        let size = maxSize;
        el.style.fontSize = `${size}px`;
        while (
          (el.scrollHeight > el.clientHeight + 0.5 || el.scrollHeight > availHeight + 0.5) &&
          size > minSize
        ) {
          size -= 0.5;
          el.style.fontSize = `${size}px`;
        }
      } else {
        let size = maxSize;
        while (el.scrollWidth > avail && size > minSize) {
          size -= 0.5;
          el.style.fontSize = `${size}px`;
        }
      }
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(parent);
    return () => ro.disconnect();
  }, [text, maxSize, minSize, maxLines]);
  return (
    <span
      ref={ref}
      className={className}
      style={{
        letterSpacing: "0.02em",
        display: "block",
        overflow: "hidden",
        textOverflow: "ellipsis",
        fontFamily: "'Bebas Neue', sans-serif",
        ...READABLE_TEXT,
      }}
    >
      {text}
    </span>
  );
}
