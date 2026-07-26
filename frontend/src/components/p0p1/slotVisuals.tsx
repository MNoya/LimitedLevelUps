import { Pip } from "../ManaPips";
import { keyruneClass } from "../Brand";
import type { SlotKey } from "../../types/p0p1";

type Color = "W" | "U" | "B" | "R" | "G";

const UNCOMMON_SILVER_GRADIENT = "linear-gradient(90deg, #8a94a3 0%, #e6e9ef 50%, #8a94a3 100%)";
const UNCOMMON_SILVER_BAR = "linear-gradient(90deg, #5c6675 0%, #b9c1cc 40%, #ffffff 50%, #b9c1cc 60%, #5c6675 100%)";
const UNCOMMON_GLYPH_GRADIENT = "linear-gradient(to bottom, #d6dbe3 0%, #ffffff 48%, #ffffff 56%, #cdd3dc 100%)";

export const SLOT_ACCENT: Record<SlotKey, string> = {
  white_common: "#e8e4cf",
  blue_common: "#5aa9e6",
  black_common: "#9b86c4",
  red_common: "#e0625c",
  green_common: "#54b87a",
  multicolor_uncommon: "#ffc63a",
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
  return (
    <i
      className={`${setSymbol} ss-uncommon ss-grad`}
      style={{
        fontSize: size,
        lineHeight: 1,
        background: UNCOMMON_GLYPH_GRADIENT,
        WebkitBackgroundClip: "text",
        backgroundClip: "text",
        WebkitTextFillColor: "transparent",
      }}
    />
  );
}
