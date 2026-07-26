import { useState } from "react";
import { SlotPip, SLOT_ACCENT } from "./slotVisuals";
import { CardImagePreview } from "./CardImagePreview";
import { TiedCardsModal } from "./TiedCardsModal";
import { PickVersusModal, usePickVersusPager } from "./PickVersusCard";
import { SectionLabel } from "../SectionLabel";
import { ManaCost } from "../ManaPips";
import { groupBySlot, findExtremes, buildPickVersus, pickPctLabel } from "../../data/p0p1Stats";
import { SLOTS } from "../../data/p0p1Slots";
import type { Card, P0P1PickStat, PickVersus, SlotKey } from "../../types/p0p1";

export function CommunityGrid({
  pickStats,
  cardsByName,
  picksBySlot,
  setCode,
}: {
  pickStats: P0P1PickStat[];
  cardsByName: Map<string, Card>;
  picksBySlot?: Map<string, string>;
  setCode?: string;
}) {
  const grouped = groupBySlot(pickStats);

  return (
    <PickRow
      title="Crowd Favorites"
      entries={SLOTS.map((slot) => {
        const slotStats = grouped.get(slot.key) ?? [];
        return { slotKey: slot.key, label: slot.label, stats: findExtremes(slotStats).most, slotStats };
      })}
      cardsByName={cardsByName}
      picksBySlot={picksBySlot}
      setCode={setCode}
    />
  );
}

export type PickEntry = {
  slotKey: SlotKey;
  label: string;
  stats: P0P1PickStat[];
  slotStats?: P0P1PickStat[];
  badge?: string;
  // When set, overrides the pick% badge with this string (e.g. a GIHWR label)
  pctLabel?: string;
};

function PickRow({
  title,
  entries,
  cardsByName,
  picksBySlot,
  setCode,
}: {
  title: string;
  entries: PickEntry[];
  cardsByName: Map<string, Card>;
  picksBySlot?: Map<string, string>;
  setCode?: string;
}) {
  return (
    <div>
      <div className="flex justify-center mb-1.5 lg:mb-2">
        <SectionLabel size={22} color={'white'}>
          {title}
        </SectionLabel>
      </div>
      <PickGrid entries={entries} cardsByName={cardsByName} picksBySlot={picksBySlot} setCode={setCode} />
    </div>
  );
}

export function PickGrid({
  entries,
  cardsByName,
  picksBySlot,
  onTileOpen,
  setCode,
}: {
  entries: PickEntry[];
  cardsByName: Map<string, Card>;
  picksBySlot?: Map<string, string>;
  onTileOpen?: (slotKey: SlotKey) => void;
  setCode?: string;
}) {
  const versusList: PickVersus[] = [];
  const pagerIndexBySlot = new Map<SlotKey, number>();
  if (!onTileOpen) {
    for (const entry of entries) {
      const yourPick = picksBySlot?.get(entry.slotKey);
      const versus = entry.slotStats && yourPick
        ? buildPickVersus(entry.slotStats, yourPick, cardsByName, entry.slotKey, entry.label)
        : null;
      if (versus) {
        pagerIndexBySlot.set(entry.slotKey, versusList.length);
        versusList.push(versus);
      }
    }
  }
  const pager = usePickVersusPager(versusList);

  return (
    <div className="grid grid-cols-4 lg:grid-cols-8 gap-2">
      {entries.map(({ slotKey, label, stats, badge, pctLabel }) => {
        const pagerIndex = pagerIndexBySlot.get(slotKey);
        const onOpen = onTileOpen
          ? () => onTileOpen(slotKey)
          : pagerIndex !== undefined ? () => pager.open(pagerIndex) : undefined;
        return (
          <PickTile
            key={slotKey}
            slotKey={slotKey}
            label={label}
            stats={stats}
            badge={badge}
            pctLabel={pctLabel}
            cardsByName={cardsByName}
            onOpenVersus={onOpen}
            setCode={setCode}
          />
        );
      })}
      {!onTileOpen && <PickVersusModal pager={pager} />}
    </div>
  );
}

function PickTile({
  slotKey,
  label,
  stats,
  cardsByName,
  onOpenVersus,
  badge,
  pctLabel,
  setCode,
}: {
  slotKey: SlotKey;
  label: string;
  stats: P0P1PickStat[];
  cardsByName: Map<string, Card>;
  onOpenVersus?: () => void;
  badge?: string;
  pctLabel?: string;
  setCode?: string;
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const hasStats = stats.length > 0;
  const tied = stats.length > 1;
  const card = hasStats ? cardsByName.get(stats[0].cardName) : undefined;
  const accent = SLOT_ACCENT[slotKey];

  let art;
  if (!card) {
    art = onOpenVersus
      ? <button type="button" onClick={onOpenVersus} className="w-full h-full cursor-pointer p-0 border-0 bg-transparent flex items-center justify-center"><SlotPip slotKey={slotKey} size={48} setCode={setCode} /></button>
      : <SlotPip slotKey={slotKey} size={48} setCode={setCode} />;
  } else if (onOpenVersus) {
    art = (
      <button type="button" onClick={onOpenVersus} className="w-full h-full cursor-pointer p-0 border-0 bg-transparent">
        <img src={card.imageArtCrop} alt={card.name} className="w-full h-full object-cover" />
      </button>
    );
  } else {
    art = (
      <CardImagePreview imageUrl={card.imageNormal} alt={card.name} className="w-full h-full">
        <img src={card.imageArtCrop} alt={card.name} className="w-full h-full object-cover" />
      </CardImagePreview>
    );
  }

  return (
    <div className="group relative min-w-0 transition-transform duration-150 hover:z-10 hover:scale-[1.04]">
      <div className="flex flex-col border border-t-0 border-border2 bg-surface overflow-hidden">
        <div className="relative z-10 h-[4px] w-full shrink-0 origin-top transition-transform duration-150 group-hover:scale-y-[2]" style={{ background: accent }} />
        <div className="relative aspect-square bg-surface2 flex items-center justify-center overflow-hidden">
          {art}
          {badge && (
            <span className="absolute bottom-1 left-1 text-[11px] lg:text-[13px] font-display tracking-wide uppercase bg-black/85 text-purple rounded-sm px-1.5 py-0.5">
              {badge}
            </span>
          )}
          {tied && (
            <button
              type="button"
              onClick={() => setModalOpen(true)}
              className="absolute top-1 right-1 text-[9px] lg:text-[10px] font-display tracking-wide bg-bg/90 rounded-sm px-1 text-muted cursor-pointer"
              title={`${stats.length} cards tied at this count — view all`}
            >
              {stats.length}-WAY TIE
            </button>
          )}
          {hasStats && (
            <span className="absolute bottom-1 right-1 text-[11px] lg:text-[13px] font-mono tabular-nums font-semibold px-1 rounded-sm bg-bg/85">
              {pctLabel ?? pickPctLabel(stats[0].pickPct)}
            </span>
          )}
        </div>
        {hasStats && (
          <div className="px-1.5 py-1.5 min-w-0 flex items-center gap-1.5">
            <span className="text-subtle text-[11px] lg:text-[13px] truncate min-w-0">{stats[0].cardName}</span>
            {card && <span className="ml-auto shrink-0 hidden lg:flex"><ManaCost cost={card.manaCost} size={12} /></span>}
          </div>
        )}
      </div>

      {modalOpen && (
        <TiedCardsModal
          label={label}
          stats={stats}
          cardsByName={cardsByName}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}
