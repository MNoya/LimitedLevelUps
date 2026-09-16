import { Pip } from "../ManaPips";
import { keyruneClass } from "../Brand";
import type { SlotKey } from "../../types/p0p1";

type Color = "W" | "U" | "B" | "R" | "G";

const UNCOMMON_SILVER_GRADIENT = "linear-gradient(90deg, #8a94a3 0%, #e6e9ef 50%, #8a94a3 100%)";
const UNCOMMON_SILVER_BAR = "linear-gradient(90deg, #5c6675 0%, #b9c1cc 40%, #ffffff 50%, #b9c1cc 60%, #5c6675 100%)";
const UNCOMMON_GLYPH_GRADIENT = "linear-gradient(to bottom, #d6dbe3 0%, #ffffff 48%, #ffffff 56%, #cdd3dc 100%)";
const RARE_GOLD_GRADIENT = "linear-gradient(90deg, #c88a2c 0%, #ffd579 50%, #c88a2c 100%)";
const RARE_GLYPH_GRADIENT = "linear-gradient(to bottom, #ffe6a3 0%, #ffcf5e 50%, #d99a2e 100%)";

const COLOR_ACCENT: Record<Color, string> = {
  W: "#e8e4cf",
  U: "#5aa9e6",
  B: "#9b86c4",
  R: "#e0625c",
  G: "#54b87a",
};

export const SLOT_ACCENT: Record<SlotKey, string> = {
  white_common: COLOR_ACCENT.W,
  blue_common: COLOR_ACCENT.U,
  black_common: COLOR_ACCENT.B,
  red_common: COLOR_ACCENT.R,
  green_common: COLOR_ACCENT.G,
  white_uncommon: COLOR_ACCENT.W,
  blue_uncommon: COLOR_ACCENT.U,
  black_uncommon: COLOR_ACCENT.B,
  red_uncommon: COLOR_ACCENT.R,
  green_uncommon: COLOR_ACCENT.G,
  multicolor_uncommon: "#ffc63a",
  best_card: RARE_GOLD_GRADIENT,
  wildcard_common: "#ffffff",
  wildcard_uncommon: UNCOMMON_SILVER_GRADIENT,
};

export function breakdownStripAccent(slotKey: SlotKey): string {
  return slotKey === "wildcard_uncommon" ? UNCOMMON_SILVER_BAR : SLOT_ACCENT[slotKey];
}

const MONO: Partial<Record<SlotKey, Color>> = {
  white_common: "W",
  blue_common: "U",
  black_common: "B",
  red_common: "R",
  green_common: "G",
  white_uncommon: "W",
  blue_uncommon: "U",
  black_uncommon: "B",
  red_uncommon: "R",
  green_uncommon: "G",
};

export function SlotPip({ slotKey, size = 15, setCode = "" }: { slotKey: SlotKey; size?: number; setCode?: string }) {
  const mono = MONO[slotKey];
  if (mono) {
    return <Pip c={mono} size={Math.round(size * 0.64)} />;
  }
  if (slotKey === "multicolor_uncommon") {
    return <i className="ms ms-multicolor ms-duo ms-duo-color ms-grad" style={{ fontSize: size, lineHeight: 1 }} />;
  }
  const setSymbol = `ss ss-${keyruneClass(setCode)}`;
  if (slotKey === "wildcard_common") {
    return <i className={setSymbol} style={{ fontSize: size, color: "#fff", lineHeight: 1 }} />;
  }
  const isRare = slotKey === "best_card";
  return (
    <i
      className={`${setSymbol} ${isRare ? "ss-mythic" : "ss-uncommon"} ss-grad`}
      style={{
        fontSize: size,
        lineHeight: 1,
        background: isRare ? RARE_GLYPH_GRADIENT : UNCOMMON_GLYPH_GRADIENT,
        WebkitBackgroundClip: "text",
        backgroundClip: "text",
        WebkitTextFillColor: "transparent",
      }}
    />
  );
}
