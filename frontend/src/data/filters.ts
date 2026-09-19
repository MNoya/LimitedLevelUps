// Single source of truth for filter options and color-combo metadata.
import { formatsForBucket } from "./format-buckets";

export interface FilterOption {
  value: string;
  label: string;
}

// Format groups recognized across pages. `value` matches the backend
// `format_label` and the prefix-match used in PlayerPage's draft log filter.
export const FORMAT_OPTIONS: FilterOption[] = [
  { value: "ALL", label: "ALL FORMATS" },
  { value: "Premier", label: "PREMIER DRAFT" },
  { value: "Trad", label: "TRADITIONAL DRAFT" },
  { value: "Quick", label: "QUICK DRAFT" },
  { value: "Sealed", label: "SEALED" },
  // Arena Direct buckets under Sealed for scoring; surfaced as a sibling filter only
  // for sets that actually have Direct events (see fetchAvailableFormats).
  { value: "Direct", label: "SEALED - DIRECT" },
  { value: "LCQ", label: "CHAMPIONSHIP QUALIFIER" },
  { value: "Pod", label: "POD DRAFT" },
];

export const FORMAT_LABEL_GROUPS: Record<string, string[]> = {
  LCQ: ["LCQ Draft 1", "LCQ Draft 2"],
};

export const FORMAT_RAW_GROUPS: Record<string, string[]> = {
  Premier: formatsForBucket("Premier"),
  Trad: formatsForBucket("Trad"),
  Sealed: [...formatsForBucket("Sealed"), "MidWeekSealed"],
  Quick: [...formatsForBucket("Quick"), "MidWeekQuickDraft"],
  LCQ: [...formatsForBucket("LCQ Draft 1"), ...formatsForBucket("LCQ Draft 2")],
  Pod: ["PodDraft"],
  Direct: ["ArenaDirect_Sealed"],
};

export function matchesFormatFilter(rawFormat: string, filter: string): boolean {
  if (filter === "ALL") return true;
  if (filter === "Sealed" && rawFormat.startsWith("OpenSealed")) return true;
  // Arena Open Bo3 drafts score as Trad; the _Bo1 variants (HOB Sep 2026) are Champ Qualifier
  if (filter === "Trad" && rawFormat.startsWith("OpenDraft") && !rawFormat.endsWith("_Bo1")) return true;
  const group = FORMAT_RAW_GROUPS[filter];
  if (group) return group.includes(rawFormat);
  return rawFormat.toLowerCase().includes(filter.toLowerCase());
}


// Cross-cutting bucket — decks too many-colored for a normal archetype (see isSoup).
// Display label: "SOUP"
export const MULTI = "MULTI";

// Client-side catchall for sub-threshold combos. Display label: "OTHER"
export const OTHER = "OTHER";

// Mono-color codes (rare in modern Limited; kept for completeness).
export const MONO_COLOR_CODES: string[] = ["W", "U", "B", "R", "G"];

// Two-color codes in WUBRG-pair order (10 guilds).
export const TWO_COLOR_CODES: string[] = [
  "WU", "WB", "WR", "WG",
  "UB", "UR", "UG",
  "BR", "BG",
  "RG",
];

// Three-color shard/wedge codes (informational; not all formats support them).
export const TRI_COLOR_CODES: string[] = [
  "WUB", "WUR", "WUG",
  "WBR", "WBG", "WRG",
  "UBR", "UBG", "URG",
  "BRG",
];

// Display names for mono-color codes.
const MONO_NAMES: Record<string, string> = {
  W: "MONO WHITE",
  U: "MONO BLUE",
  B: "MONO BLACK",
  R: "MONO RED",
  G: "MONO GREEN",
};

// Display names for two-color codes (the MTG guild names).
const GUILD_NAMES: Record<string, string> = {
  WU: "AZORIUS",
  WB: "ORZHOV",
  WR: "BOROS",
  WG: "SELESNYA",
  UB: "DIMIR",
  UR: "IZZET",
  UG: "SIMIC",
  BR: "RAKDOS",
  BG: "GOLGARI",
  RG: "GRUUL",
};

// Three-color shard/wedge names. Used by the deck-colors charts when a player
// drafts a 3-color deck.
const WEDGE_NAMES: Record<string, string> = {
  WUB: "ESPER",
  WUR: "JESKAI",
  WUG: "BANT",
  WBR: "MARDU",
  WBG: "ABZAN",
  WRG: "NAYA",
  UBR: "GRIXIS",
  UBG: "SULTAI",
  URG: "TEMUR",
  BRG: "JUND",
};

function fourColorMissing(code: string): string | null {
  if (code.length !== 4) return null;
  for (const c of "WUBRG") {
    if (!code.includes(c)) return c;
  }
  return null;
}

export function colorsDisplayName(code: string): string {
  if (code === MULTI) return "SOUP";
  if (code === OTHER) return "OTHER";
  if (MONO_NAMES[code]) return MONO_NAMES[code];
  if (GUILD_NAMES[code]) return GUILD_NAMES[code];
  if (WEDGE_NAMES[code]) return WEDGE_NAMES[code];
  if (code === "WUBRG") return "5-COLOR";
  const missing = fourColorMissing(code);
  if (missing) return `4C NO ${missing}`;
  return code;
}

const _wubrgSort = (s: string) =>
  [...s].sort((a, b) => "WUBRG".indexOf(a) - "WUBRG".indexOf(b)).join("");

// "URg" → "IZZET SPLASH G", "UGbr" → "SIMIC SPLASH BR", "WB" → "ORZHOV"
export function formatDeckColors(colors: string | null | undefined): string {
  const { name, splash } = deckColorParts(colors);
  return splash ? `${name} ${splash}` : name;
}

// Same data as formatDeckColors but split for column-aligned layouts.
// `splash` is "SPLASH X" / "" — already includes the prefix word for readability.
export function deckColorParts(colors: string | null | undefined): { name: string; splash: string } {
  if (!colors) return { name: "", splash: "" };
  const main = _wubrgSort(colors.replace(/[a-z]/g, ""));
  const splash = _wubrgSort(colors.replace(/[A-Z]/g, "").toUpperCase());
  const splashLabel = splash ? `SPLASH ${splash}` : "";
  // 4-color decks: "NO X" only makes sense when not splashing — splash already names the missing color
  if (main.length === 4 && splash) {
    return { name: "4 COLOR", splash: splashLabel };
  }
  const name = main ? colorsDisplayName(main) : "COLORLESS";
  return { name, splash: splashLabel };
}

const comboLabel = (code: string) => `${code} · ${colorsDisplayName(code)}`;

export const COLOR_OPTIONS: FilterOption[] = [
  { value: "ALL", label: "ALL" },
  ...TWO_COLOR_CODES.map((c) => ({ value: c, label: comboLabel(c) })),
];

export const COLOR_OPTIONS_LONG: FilterOption[] = [
  { value: "ALL", label: "ALL COLORS" },
  ...TWO_COLOR_CODES.map((c) => ({ value: c, label: comboLabel(c) })),
];
