// The left pane's tab strip and the draft log's column header sit side by side and must line up
export const TRACKER_HEADER_H = "h-[40px]";

export const HEADER_CLS = "font-display text-[11px] tracking-[0.2em] text-muted";
export const SUBLABEL_CLS = "font-display text-[13px] tracking-[0.08em] text-muted";

export const COLOR_HEX: Record<string, string> = {
  W: "#f5efd6", U: "#4aa8ff", B: "#a98eff", R: "#ff5e5e", G: "#2ee85c", M: "#ffc63a", C: "#8a93a5",
};

// Keyrune's own .ss-rare and .ss-mythic, the rare bar on keyrune's .ss-grad and the mythic bar on a
// softer sweep than keyrune's orange
export const RARITY_STYLE = {
  rare: { color: "#A58E4A", gradient: "linear-gradient(90deg, #876a3b 0%, #dfbd6b 50%, #876a3b 100%)" },
  mythic: { color: "#BF4427", gradient: "linear-gradient(90deg, #9E3620 0%, #D2603C 50%, #9E3620 100%)" },
};

export type RarityStyle = (typeof RARITY_STYLE)["rare"];
