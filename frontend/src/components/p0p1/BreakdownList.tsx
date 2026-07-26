import { type ReactNode, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ManaCost } from "../ManaPips";
import { SectionLabel } from "../SectionLabel";
import { SlotPip, breakdownStripAccent } from "./slotVisuals";
import { CardImagePreview } from "./CardImagePreview";
import { SLOTS } from "../../data/p0p1Slots";
import type { Card, SlotDefinition, SlotKey } from "../../types/p0p1";

export interface BreakdownRow {
  name: string;
  card?: Card;
  isYours: boolean;
  fillPct: number;    // 0 → no bar; > 0 → fill width %
  value: ReactNode;   // right-hand metric cell, pre-styled by caller
}

export function BreakdownList({
  title,
  headerAside,
  bySlot,
  setCode,
}: {
  title: string;
  headerAside?: ReactNode;
  bySlot: Map<SlotKey, BreakdownRow[]>;
  setCode?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5 lg:gap-3">
      <div className="relative flex items-center justify-center">
        <SectionLabel size={22} className="text-white">{title}</SectionLabel>
        {headerAside && (
          <span className="absolute right-3 text-subtle text-[14px]">{headerAside}</span>
        )}
      </div>

      <div className="hidden lg:grid grid-cols-2 xl:grid-cols-3 gap-3 items-start">
        {SLOTS.map((slot) => (
          <BreakdownPanel
            key={slot.key}
            slot={slot}
            rows={bySlot.get(slot.key) ?? []}
            setCode={setCode}
          />
        ))}
      </div>

      <div className="lg:hidden flex flex-col gap-2">
        {SLOTS.map((slot) => (
          <BreakdownPanel
            key={slot.key}
            slot={slot}
            rows={bySlot.get(slot.key) ?? []}
            setCode={setCode}
            collapsible
          />
        ))}
      </div>
    </div>
  );
}

function BreakdownPanel({
  slot,
  rows,
  setCode,
  collapsible = false,
}: {
  slot: SlotDefinition;
  rows: BreakdownRow[];
  setCode?: string;
  collapsible?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const accent = breakdownStripAccent(slot.key);
  const showRows = !collapsible || expanded;
  const wide = slot.key === "wildcard_uncommon";

  const header = (
    <div className={`flex-1 flex items-center gap-2 ${wide ? "pl-4 pr-3" : "px-3"} py-2.5 min-w-0`}>
      <SlotPip slotKey={slot.key} size={20} setCode={setCode} />
      <span className="font-display text-[15px] tracking-[0.1em] text-white truncate">
        {slot.label.toUpperCase()}
      </span>
      <span className="ml-auto shrink-0 text-muted text-[12px] tabular-nums">
        {rows.length} card{rows.length !== 1 ? "s" : ""} chosen
      </span>
      {collapsible && (
        <ChevronDown
          size={16}
          className={`shrink-0 text-muted transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
        />
      )}
    </div>
  );

  return (
    <div className="relative border-y border-r border-border2 bg-surface overflow-hidden flex flex-col">
      <div className={`absolute inset-y-0 left-0 z-10 ${wide ? "w-2" : "w-1"} pointer-events-none`} style={{ background: accent }} />
      {collapsible ? (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className={`flex items-stretch bg-surface2 text-left cursor-pointer ${showRows ? "border-b border-border2" : ""}`}
        >
          {header}
        </button>
      ) : (
        <div className="flex items-stretch bg-surface2 border-b border-border2">{header}</div>
      )}

      {showRows && (
        <div>
          {rows.map((row, i) => (
            <BreakdownRowItem key={row.name} rank={i + 1} row={row} wide={wide} />
          ))}
        </div>
      )}
    </div>
  );
}

function BreakdownRowItem({
  rank,
  row,
  wide,
}: {
  rank: number;
  row: BreakdownRow;
  wide: boolean;
}) {
  const isLeader = rank === 1;

  return (
    <div className="relative overflow-hidden border-b border-border2 last:border-b-0">
      {row.fillPct > 0 && (
        <div className="absolute inset-y-0 left-0 bg-subtle/[0.08]" style={{ width: `${row.fillPct}%` }} />
      )}

      <div className={`relative flex items-center gap-2.5 ${wide ? "pl-4" : "pl-1.5"} pr-3 py-1.5 ${row.isYours ? "bg-green/[0.07]" : ""}`}>
        <span className={`w-4 shrink-0 text-right font-mono tabular-nums text-[13px] ${isLeader ? "text-text font-bold" : "text-muted"}`}>
          {rank}
        </span>

        {row.card ? (
          <CardImagePreview imageUrl={row.card.imageNormal} alt={row.card.name} className="w-11 h-11 rounded-sm overflow-hidden shrink-0">
            <img src={row.card.imageArtCrop} alt={row.card.name} className="w-full h-full object-cover" />
          </CardImagePreview>
        ) : (
          <div className="w-11 h-11 rounded-sm bg-surface2 shrink-0" />
        )}

        <div className="flex-1 min-w-0 flex items-center gap-2">
          <span className="text-text text-[15px] leading-snug line-clamp-2 min-w-0">{row.name}</span>
          {row.isYours && (
            <span className="shrink-0 inline-block font-display tracking-[0.14em] uppercase text-[12.5px] leading-none px-2 py-1 bg-green text-bg">
              YOURS
            </span>
          )}
          <span className="ml-auto flex items-center gap-3 shrink-0">
            {row.card && <ManaCost cost={row.card.manaCost} size={12} />}
            {row.value}
          </span>
        </div>
      </div>
    </div>
  );
}
