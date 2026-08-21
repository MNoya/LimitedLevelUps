import type { FilterOption } from "./filters";
import { MULTI, OTHER } from "./filters";
import { Pips } from "../components/ManaPips";
import { BsAsterisk, BsPaletteFill } from "../components/Icons";

// Single source of truth for per-format swatch colors. Keep the keys aligned
// with the backend `format_label` groups so dropdowns, donuts, and legend
// chips all read from the same palette.
export const FMT_COLORS: Record<string, string> = {
  Premier: "#2ee85c",
  Trad: "#5c8aff",
  Quick: "#ffc63a",
  Sealed: "#ff5d8c",
  Direct: "#ff5d8c",
  LCQ: "#ff7700",
  "LCQ Draft 1": "#ff7700",
  "LCQ Draft 2": "#ff7700",
  Pod: "#a86bff",
  // Self-reported platforms (values are the platform strings the trophy stores)
  MTGO: "#e8503a",
  MTGA: "#e8503a",
  Paper: "#a9744f",
};

export const FMT_DEFAULT_COLOR = "#5c8aff";

const FORMAT_SHORT: Record<string, string> = {
  PremierDraft: "PREMIER",
  ContenderDraft: "CONTENDER",
  TradDraft: "TRAD",
  QuickDraft: "QUICK",
  Sealed: "SEALED",
  TradSealed: "TRAD SEALED",
  ArenaDirect_Sealed: "DIRECT",
  QualifierPlayInSealed: "PLAY-IN",
  QualifierPlayInTradSealed: "PLAY-IN BO3",
  Qualifier_D1_Sealed: "QUAL DAY 1",
  Qualifier_D2_Sealed: "QUAL DAY 2",
  PickTwoDraft: "PICK 2",
  Emblem_QuickDraft: "QUICK",
  LimitedChampionshipQualifier_Draft1: "LCQ D1",
  LimitedChampionshipQualifier_Draft2: "LCQ D2",
  "LCQ Draft 1": "LCQ D1",
  "LCQ Draft 2": "LCQ D2",
  Premier: "PREMIER",
  Trad: "TRAD",
  Quick: "QUICK",
  LCQ: "LCQ",
  Pod: "POD",
  PodDraft: "POD",
  "Trad Sealed": "TRAD SEALED",
  "Arena Direct": "ARENA DIR",
};

export function shortFormat(format: string): string {
  return FORMAT_SHORT[format] ?? format.replace(/_/g, " ").toUpperCase();
}

// Dropdown row + selected-value renderer used by every FilterDropdown that
// drives a format filter. Reads the swatch color from FMT_COLORS so the
// option chips always match the donut palette.
export const renderFormatOption = (opt: FilterOption) => {
  if (opt.value === "ALL") return <span>{opt.label}</span>;
  const color = FMT_COLORS[opt.value] ?? FMT_DEFAULT_COLOR;
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 w-2 shrink-0" style={{ background: color }} />
      <span>{opt.label}</span>
    </span>
  );
};

export const renderColorOption = (opt: FilterOption) => {
  if (opt.value === "ALL") return <span>{opt.label}</span>;
  if (opt.value === MULTI) {
    return (
      <span className="flex items-center gap-2">
        <BsPaletteFill size={12} aria-hidden="true" />
        <span>{opt.label}</span>
      </span>
    );
  }
  if (opt.value === OTHER) {
    return (
      <span className="flex items-center gap-2">
        <BsAsterisk size={11} aria-hidden="true" />
        <span>{opt.label}</span>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-2">
      <Pips colors={opt.value} size={12} />
      <span>{opt.label}</span>
    </span>
  );
};
