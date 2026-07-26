import type { Card, SlotDefinition } from "../../types/p0p1";
import { ManaCost } from "../ManaPips";
import { CardImagePreview } from "./CardImagePreview";
import { SlotPip, SLOT_ACCENT } from "./slotVisuals";

interface Props {
  slot: SlotDefinition;
  selectedCard: Card | undefined;
  locked?: boolean;
  active?: boolean;
  onEdit: () => void;
  setCode?: string;
}

export function SlotCard({ slot, selectedCard, locked, active, onEdit, setCode }: Props) {
  const accent = SLOT_ACCENT[slot.key];
  const stripClass = `self-stretch shrink-0 transition-[width] duration-150 ${active ? "w-2" : "w-1 group-hover:w-2"}`;

  const thumb = selectedCard ? (
    <CardImagePreview imageUrl={selectedCard.imageNormal} alt={selectedCard.name} className="self-stretch w-[88px]">
      <img src={selectedCard.imageArtCrop} alt="" className="absolute inset-0 w-full h-full object-cover" />
    </CardImagePreview>
  ) : (
    <div className="self-stretch w-[88px] shrink-0 bg-surface2 flex items-center justify-center">
      <SlotPip slotKey={slot.key} size={28} setCode={setCode} />
    </div>
  );

  const text = (
    <div className="flex flex-col justify-center gap-2 px-3.5 flex-1 min-w-0">
      <div className="text-subtle text-[14px] tracking-[0.12em] font-display truncate">
        {slot.label.toUpperCase()}
      </div>
      {selectedCard ? (
        <div className="flex items-center gap-2 min-w-0">
          <div className="text-text text-[15px] truncate">{selectedCard.name}</div>
          <ManaCost cost={selectedCard.manaCost} />
        </div>
      ) : (
        <div className="text-dim text-[15px]">{locked ? "—" : "Select a card"}</div>
      )}
    </div>
  );

  if (locked) {
    return (
      <div className="w-full h-full min-h-[56px] flex items-stretch bg-surface border border-border2 overflow-hidden">
        <div className={stripClass} style={{ background: accent }} />
        {thumb}
        {text}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onEdit}
      className={`w-full h-full min-h-[56px] flex items-stretch border transition-colors cursor-pointer text-left group overflow-hidden ${
        active ? "border-green/60 border-l-transparent bg-green/5" : "border-border2 bg-surface"
      }`}
    >
      <div className={stripClass} style={{ background: accent }} />
      {thumb}
      {text}
    </button>
  );
}
