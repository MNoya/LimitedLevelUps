import { useEffect, useState, type MouseEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ModalNavButton } from "../ModalNavButton";
import { SlotPip } from "./slotVisuals";
import { pickPctLabel } from "../../data/p0p1Stats";
import type { PickVersus, SlotKey } from "../../types/p0p1";

export const MAT = "#161b26";
const MUTED = "#7a8395";
const ROGUE = "#a98eff";
const GREEN = "#2ee85c";
const NEUTRAL = "#e6ecf5";

// ── Shared shell / structure ────────────────────────────────────────────────────

export function VsCardShell({
  maxWidth,
  onClick,
  children,
}: {
  maxWidth: number;
  onClick: (e: MouseEvent) => void;
  children: ReactNode;
}) {
  return (
    <div
      onClick={onClick}
      className="flex max-h-[92vh] w-full flex-col overflow-hidden rounded-xl border border-white/15 p-[6px] shadow-2xl sm:border-white/60"
      style={{ backgroundColor: MAT, maxWidth }}
    >
      {children}
    </div>
  );
}

export function VsCategoryHeader({
  slotKey,
  slotLabel,
  setCode,
}: {
  slotKey: SlotKey;
  slotLabel: string;
  setCode?: string;
}) {
  return (
    <div className="flex items-center justify-center gap-2 px-2 pb-3 pt-1.5 lg:gap-2.5 lg:pb-4">
      <SlotPip slotKey={slotKey} size={20} setCode={setCode} />
      <span className="font-display text-[18px] leading-none tracking-[0.2em] text-text lg:text-[22px]">
        {slotLabel.toUpperCase()}
      </span>
    </div>
  );
}

export function VsTwoColumnLayout({ left, right }: { left: ReactNode; right: ReactNode }) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] gap-2 lg:gap-5">
      {left}
      <VsColumnDivider />
      {right}
    </div>
  );
}

export function VsThreeColumnLayout({
  left,
  middle,
  right,
}: {
  left: ReactNode;
  middle: ReactNode;
  right: ReactNode;
}) {
  return (
    <div className="grid gap-0" style={{ gridTemplateColumns: "1fr auto 1fr auto 1fr" }}>
      {left}
      <VsColumnDivider />
      {middle}
      <VsColumnDivider />
      {right}
    </div>
  );
}

export function VsColumnDivider() {
  return (
    <div className="relative flex items-center justify-center">
      <div className="absolute inset-y-0 w-0.5 bg-white/20" />
      <span
        className="relative z-10 flex h-9 w-9 items-center justify-center rounded-full border border-white/60 font-display text-[13px] tracking-[0.08em] text-muted lg:h-12 lg:w-12 lg:text-[16px]"
        style={{ backgroundColor: MAT }}
      >
        VS
      </span>
    </div>
  );
}

export function PagerNav({
  onPrev,
  onNext,
  paged,
  prevLabel = "Prev",
  nextLabel = "Next",
}: {
  onPrev?: () => void;
  onNext?: () => void;
  paged: boolean;
  prevLabel?: string;
  nextLabel?: string;
}) {
  if (!paged) return null;
  return (
    <div className="flex items-center justify-between px-3 py-3.5">
      <ModalNavButton dir="prev" label={prevLabel} onClick={onPrev} />
      <ModalNavButton dir="next" label={nextLabel} onClick={onNext} />
    </div>
  );
}

// ── Shared metric-side primitive ────────────────────────────────────────────────
//
// density "comfortable": responsive header (label + number side by side on lg),
//   max-h constrained card image — used by solo + 2-col layouts.
//   solo=true forces an always-row header (used in the agreed/single-card case)
//   and limits image width on mobile.
//
// density "compact": eyebrow label stacked over number, full-width small image,
//   name caption below — used by 3-col layouts where columns are narrow.

export function VsMetricSide({
  label,
  labelColor,
  value,
  valueColor,
  caption,
  fillPct,
  barColor,
  dim = false,
  density,
  solo = false,
  tight = false,
  imageUrl,
  name,
}: {
  label: string;
  labelColor: string;
  value: string;
  valueColor: string;
  caption?: string;
  fillPct: number;
  barColor: string;
  dim?: boolean;
  density: "comfortable" | "compact";
  /** Only meaningful for density="comfortable". Forces an always-row header
   *  and constrains image width on mobile (the agreed/solo card case). */
  solo?: boolean;
  /** Shrinks the mobile label so it fits a narrow column without truncating (3-column case). */
  tight?: boolean;
  imageUrl?: string;
  name: string;
}) {
  if (density === "compact") {
    return (
      <div className="flex min-w-0 flex-col gap-1.5 px-1 pb-1">
        <div className="flex flex-col gap-0.5">
          <span
            className="font-display leading-none tracking-[0.14em]"
            style={{ fontSize: 10, color: labelColor }}
          >
            {label}
          </span>
          <span className="flex items-baseline gap-1.5">
          <span
            className="font-mono tabular-nums font-semibold leading-none"
            style={{ fontSize: 20, color: dim ? "#4a5568" : valueColor }}
          >
            {value}
          </span>
          {caption && (
            <span className="font-body text-[9px] leading-none text-muted">
              {caption}
            </span>
          )}
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full" style={{ width: `${fillPct}%`, background: barColor }} />
        </div>
        <VsCardImage imageUrl={imageUrl} name={name} className="w-full rounded-[5px]" />
        <span className="truncate text-center font-body text-[9px] leading-snug text-muted">
          {name || "—"}
        </span>
      </div>
    );
  }

  // comfortable
  const headerClass = solo
    ? "flex items-baseline justify-between gap-3"
    : "flex flex-col gap-1.5 lg:flex-row lg:items-baseline lg:justify-between lg:gap-3";
  const numberGroupClass = solo
    ? "flex items-baseline gap-1.5"
    : "order-2 flex items-baseline gap-1.5 lg:order-none";
  const labelClass = solo
    ? "shrink-0 whitespace-nowrap font-display text-[13px] leading-none tracking-[0.14em] lg:text-[16px]"
    : tight
      ? "order-1 whitespace-nowrap font-display text-[12px] leading-none tracking-[0.08em] lg:order-none lg:shrink-0 lg:text-[16px]"
      : "order-1 truncate font-display text-[13px] leading-none tracking-[0.14em] lg:order-none lg:shrink-0 lg:whitespace-nowrap lg:text-[16px]";
  const imageClass = `mx-auto max-h-[58vh] w-auto rounded-[10px] ${solo ? "max-w-[200px] lg:max-w-full" : "max-w-full"}`;

  return (
    <div className="flex min-w-0 flex-col gap-2.5 lg:gap-3">
      <div className="flex flex-col gap-2 px-1">
        <div className={headerClass}>
          <span className={numberGroupClass}>
            <span
              className="font-mono tabular-nums text-[20px] font-semibold leading-none lg:text-[30px]"
              style={{ color: dim ? "#4a5568" : valueColor }}
            >
              {value}
            </span>
            {caption && (
              <span className="text-[11px] leading-none text-muted lg:text-[13px]">{caption}</span>
            )}
          </span>
          <span className={labelClass} style={{ color: labelColor }}>
            {label}
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full" style={{ width: `${fillPct}%`, background: barColor }} />
        </div>
      </div>
      <VsCardImage imageUrl={imageUrl} name={name} className={imageClass} />
    </div>
  );
}

export function VsCardImage({
  imageUrl,
  name,
  className,
}: {
  imageUrl?: string;
  name: string;
  className: string;
}) {
  return imageUrl ? (
    <img src={imageUrl} alt={name} className={className} />
  ) : (
    <div className={`rounded-[10px] bg-white/5 ${className}`} style={{ aspectRatio: "488/680" }} />
  );
}

// ── Pager hook (generic) ────────────────────────────────────────────────────────

export function useVersusPager<T>(list: T[]) {
  const [index, setIndex] = useState<number | null>(null);
  const current = index === null ? null : list[index] ?? null;
  return {
    list,
    index,
    current,
    open: (i: number) => setIndex(i),
    close: () => setIndex(null),
    step: (delta: number) =>
      setIndex((cur) => (cur === null ? cur : (cur + delta + list.length) % list.length)),
  };
}

export type VersusPager<T> = ReturnType<typeof useVersusPager<T>>;

// Alias for backwards compat
export function usePickVersusPager(list: PickVersus[]) {
  return useVersusPager(list);
}

// ── Modal (generic) ─────────────────────────────────────────────────────────────

export function VersusModal<T>({
  pager,
  padding = "p-4",
  renderCard,
}: {
  pager: VersusPager<T>;
  padding?: string;
  renderCard: (
    current: T,
    nav: { paged: boolean; onPrev: () => void; onNext: () => void },
  ) => ReactNode;
}) {
  const { current, index, list, close, step } = pager;

  useEffect(() => {
    if (current === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === "ArrowRight") step(1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [current, close, step]);

  if (current === null || index === null) return null;

  return createPortal(
    <div
      className={`fixed inset-0 z-[200] flex items-center justify-center bg-black/70 ${padding}`}
      onClick={close}
    >
      {renderCard(current, {
        paged: list.length > 1,
        onPrev: () => step(-1),
        onNext: () => step(1),
      })}
    </div>,
    document.body,
  );
}

// Convenience wrapper used by CommunityGrid (keeps its import surface unchanged)
export function PickVersusModal({ pager }: { pager: VersusPager<PickVersus> }) {
  return (
    <VersusModal
      pager={pager}
      padding="p-6"
      renderCard={(versus, nav) => <PickVersusCard versus={versus} {...nav} />}
    />
  );
}

// ── Card ────────────────────────────────────────────────────────────────────────

export function PickVersusCard({
  versus,
  onPrev,
  onNext,
  paged = false,
}: {
  versus: PickVersus;
  onPrev?: () => void;
  onNext?: () => void;
  paged?: boolean;
}) {
  const stop = (e: MouseEvent) => e.stopPropagation();

  if (versus.agreed) {
    const fill = Math.max(Math.min(versus.yours.pickPct, 100), 4);
    return (
      <VsCardShell maxWidth={420} onClick={stop}>
        <div className="px-4 pt-2">
          <VsCategoryHeader slotKey={versus.slotKey} slotLabel={versus.slotLabel} />
          <VsMetricSide
            label="CROWD PICK"
            labelColor={GREEN}
            value={pickPctLabel(versus.yours.pickPct)}
            valueColor={GREEN}
            caption="of votes"
            fillPct={fill}
            barColor={GREEN}
            density="comfortable"
            solo
            imageUrl={versus.yours.imageUrl}
            name={versus.yours.name}
          />
        </div>
        <PagerNav onPrev={onPrev} onNext={onNext} paged={paged} prevLabel="Prev Pick" nextLabel="Next Pick" />
      </VsCardShell>
    );
  }

  const isRogue = versus.state === "rogue";
  const yoursAccent = isRogue ? ROGUE : NEUTRAL;
  const yoursBar = isRogue ? ROGUE : MUTED;
  const yoursLabel = isRogue ? "ROGUE PICK" : "YOUR PICK";

  return (
    <VsCardShell maxWidth={820} onClick={stop}>
      <div className="px-2 pt-2 lg:px-4">
        <VsCategoryHeader slotKey={versus.slotKey} slotLabel={versus.slotLabel} />
        <VsTwoColumnLayout
          left={
            <VsMetricSide
              label="CROWD FAVORITE"
              labelColor={MUTED}
              value={pickPctLabel(versus.crowd.pickPct)}
              valueColor={NEUTRAL}
              caption="of votes"
              fillPct={Math.max(Math.min(versus.crowd.pickPct, 100), 4)}
              barColor={MUTED}
              density="comfortable"
              imageUrl={versus.crowd.imageUrl}
              name={versus.crowd.name}
            />
          }
          right={
            <VsMetricSide
              label={yoursLabel}
              labelColor={yoursAccent}
              value={pickPctLabel(versus.yours.pickPct)}
              valueColor={yoursAccent}
              caption="of votes"
              fillPct={Math.max(Math.min(versus.yours.pickPct, 100), 4)}
              barColor={yoursBar}
              density="comfortable"
              imageUrl={versus.yours.imageUrl}
              name={versus.yours.name}
            />
          }
        />
      </div>
      <PagerNav onPrev={onPrev} onNext={onNext} paged={paged} prevLabel="Prev Pick" nextLabel="Next Pick" />
    </VsCardShell>
  );
}
