import type { ReactNode } from "react";

import { RaritySetGlyph, type Rarity } from "../Brand";
import { columnPipClass } from "../TierGrid";

const RARITY_KEYS: Rarity[] = ["common", "uncommon", "rare", "mythic"];

export const PileSymbol = ({ pileKey, setCode }: { pileKey: string; setCode: string }): ReactNode => {
  if (pileKey === "land") {
    return <i className="ms ms-land" style={{ fontSize: 14 }} aria-label="Lands" />;
  }
  if (RARITY_KEYS.includes(pileKey as Rarity)) {
    return <RaritySetGlyph code={setCode} rarity={pileKey as Rarity} size={16} />;
  }
  if (pileKey.length === 1) {
    return <i className={columnPipClass(pileKey)} style={{ fontSize: pileKey === "M" ? 17 : 14 }} aria-label={pileKey} />;
  }
  return null;
};
