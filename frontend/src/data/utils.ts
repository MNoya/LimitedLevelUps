// Pure helpers shared by pages and components.
// Anything stateless that previously got inlined or duplicated lives here.

import type { LeaderboardRow, SetSummary } from "../types/leaderboard";
import { POD_TROPHY_WINS } from "./scoring";

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"] as const;

const MONTHS_SHORT = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."] as const;

// "May 8" / "Apr. 8" / "Dec. 23" — parses the YYYY-MM-DD prefix directly to
// avoid timezone shifts on UTC-stored draft timestamps. Appends the year
// ("May 8, 2023") when the date is not in the current calendar year.
export function fmtShortDate(iso: string, today: Date = new Date()): string {
  const year = parseInt(iso.slice(0, 4), 10);
  const month = parseInt(iso.slice(5, 7), 10);
  const day = parseInt(iso.slice(8, 10), 10);
  if (!month || !day) return "";
  const base = `${MONTHS_SHORT[month - 1]} ${day}`;
  return year && year !== today.getFullYear() ? `${base}, ${year}` : base;
}

export function eventDate(e: { finishedAt: string | null; startedAt: string | null }): string {
  return e.finishedAt ?? e.startedAt ?? "";
}

// The new set goes live the evening of its start date, so the changeover day still carries the old
// set's drafts. Treat events as flashback only once a full day past the end date has elapsed.
export function isFlashbackEvent(
  finishedAt: string | null | undefined,
  setEndDate: string | null | undefined,
): boolean {
  if (!finishedAt || !setEndDate) return false;
  return finishedAt.slice(0, 10) > dayAfter(setEndDate);
}

function dayAfter(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

// Win percentage as a fixed-precision string, safe against zero-game players.
export function winPct(wins: number, losses: number, digits = 1): string {
  return ((wins / Math.max(1, wins + losses)) * 100).toFixed(digits);
}

// Strip splash colors (lowercase) from a 17lands color string, leaving uppercase main colors.
export function mainColors(colors: string | null | undefined): string {
  if (!colors) return "";
  return colors.replace(/[a-z]/g, "");
}

// Sort main colors into WUBRG order. Used for archetype normalization.
export function wubrgSort(colors: string): string {
  const order = "WUBRG";
  return [...colors].sort((a, b) => order.indexOf(a) - order.indexOf(b)).join("");
}

// WUBRG-sorted main colors only — splashes dropped
export function colorsOf(colors: string | null | undefined): string {
  return wubrgSort(mainColors(colors));
}

// Mains then splashes, each WUBRG-sorted. 17lands writes them in pick order (`WubrG` is WG splashing UBR)
export function orderedDeckColors(colors: string | null | undefined): string {
  if (!colors) return "";
  const mains = new Set<string>();
  const splashes = new Set<string>();
  for (const c of colors) {
    const upper = c.toUpperCase();
    if (!"WUBRG".includes(upper)) continue;
    if (c === upper) {
      mains.add(upper);
    } else {
      splashes.add(upper);
    }
  }
  for (const main of mains) {
    splashes.delete(main);
  }
  return wubrgSort([...mains].join("")) + wubrgSort([...splashes].join("")).toLowerCase();
}

// Distinct colors played (main + splash deduped)
export function effectiveColorCount(colors: string | null | undefined): number {
  if (!colors) return 0;
  const seen = new Set<string>();
  for (const c of colors) {
    const u = c.toUpperCase();
    if ("WUBRG".includes(u)) seen.add(u);
  }
  return seen.size;
}

// A deck is "Soup" (MULTI) when it plays enough colors to escape a normal archetype.
// Standard limited: 4+ effective colors (2 base + 2 splash counts). Cube affords freer
// splashing, so the bar rises to 3+ base colors plus a splash (or 4+ base outright).
export function isSoup(colors: string | null | undefined, isCube: boolean): boolean {
  if (effectiveColorCount(colors) < 4) return false;
  return isCube ? colorsOf(colors).length >= 3 : true;
}

function parseLocalDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function fmtRange(start: string, end: string | null | undefined, today: Date = new Date()): string {
  if (!start) return "";
  const s = parseLocalDate(start);
  const startStr = `${MONTHS[s.getMonth()]} ${s.getDate()}`;
  if (!end) {
    const startWithYear = s.getFullYear() !== today.getFullYear() ? `${startStr}, ${s.getFullYear()}` : startStr;
    return `${startWithYear} — NOW`;
  }
  const e = parseLocalDate(end);
  // A range crossing years carries both, so a multi-year board doesn't read as one season
  const from = e.getFullYear() !== s.getFullYear() ? `${startStr}, ${s.getFullYear()}` : startStr;
  const base = `${from} — ${MONTHS[e.getMonth()]} ${e.getDate()}`;
  return e.getFullYear() !== today.getFullYear() ? `${base}, ${e.getFullYear()}` : base;
}

export function weekOfSet(set: SetSummary | undefined, today: Date = new Date()): string | null {
  if (!set?.startDate || !set.endDate) return null;
  const start = parseLocalDate(set.startDate).getTime();
  const end = parseLocalDate(set.endDate).getTime();
  const now = today.getTime();
  if (now > end) return null;
  const totalWeeks = Math.max(1, Math.ceil((end - start) / (7 * 24 * 60 * 60 * 1000)));
  const elapsedWeeks = Math.max(1, Math.min(totalWeeks, Math.ceil((now - start) / (7 * 24 * 60 * 60 * 1000))));
  return `WEEK ${elapsedWeeks} OF ${totalWeeks}`;
}

// Renders an ISO timestamp as a relative-time string ("5M AGO", "2H AGO", "NOW")
// for the "UPDATED" badge. Driven by the set's full-refresh tick, not a per-player
// max — a single join no longer makes the board read as freshly updated.
export function lastUpdated(iso: string | null | undefined): string {
  if (!iso) return "—";
  const rel = relativeTime(iso);
  return rel === "now" ? "NOW" : `${rel.toUpperCase()} AGO`;
}

// Total events across rows, locale-formatted with commas.
export function sumEvents(rows: ReadonlyArray<{ events: number }> | undefined): string {
  if (!rows) return "0";
  return rows.reduce((s, r) => s + r.events, 0).toLocaleString();
}

// Compact relative time ("2h", "3d", "1w", "5mo", "3y") suitable for sidebar timestamps.
// Only goes one unit deep; "now" for events under a minute old.
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  const diffMs = now.getTime() - then;
  if (diffMs < 60_000) return "now";
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  const weeks = Math.floor(days / 7);
  if (weeks < 8) return `${weeks}w`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo`;
  const years = Math.floor(days / 365);
  return `${years}y`;
}

const AGE_UNITS: Array<{ unit: string; short: string; seconds: number }> = [
  { unit: "year", short: "y", seconds: 31_536_000 },
  { unit: "month", short: "mo", seconds: 2_592_000 },
  { unit: "week", short: "w", seconds: 604_800 },
  { unit: "day", short: "d", seconds: 86_400 },
  { unit: "hour", short: "h", seconds: 3_600 },
  { unit: "minute", short: "m", seconds: 60 },
];

export function relativeAge(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) {
    return "";
  }
  const seconds = Math.floor((now.getTime() - then) / 1000);
  for (const { unit, seconds: unitSeconds } of AGE_UNITS) {
    const value = Math.floor(seconds / unitSeconds);
    if (value >= 1) {
      return `${value} ${unit}${value === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}

export function relativeAgeShort(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) {
    return "";
  }
  const seconds = Math.floor((now.getTime() - then) / 1000);
  for (const { short, seconds: unitSeconds } of AGE_UNITS) {
    const value = Math.floor(seconds / unitSeconds);
    if (value >= 1) {
      return `${value}${short} ago`;
    }
  }
  return "just now";
}

// Maps any raw 17lands format string OR a backend `format_label` group
// (Premier / Trad / Quick / Sealed / LCQ Draft 1 / LCQ Draft 2) to a
// presentation-ready name. Unknowns fall through unchanged.
const FORMAT_DISPLAY: Record<string, string> = {
  Premier: "Premier Draft",
  Trad: "Traditional Draft",
  Quick: "Quick Draft",
  Sealed: "Sealed",
  "LCQ Draft 1": "LCQ Draft 1",
  "LCQ Draft 2": "LCQ Draft 2",
  PremierDraft: "Premier Draft",
  ContenderDraft: "Contender Draft",
  TradDraft: "Traditional Draft",
  QuickDraft: "Quick Draft",
  TradSealed: "Traditional Sealed",
  ArenaDirect_Sealed: "Arena Direct",
  QualifierPlayInSealed: "Qualifier Play-In",
  QualifierPlayInTradSealed: "Qualifier Play-In Bo3",
  Qualifier_D1_Sealed: "Qualifier Weekend Day 1",
  Qualifier_D2_Sealed: "Qualifier Weekend Day 2",
  PickTwoDraft: "Pick Two Draft",
  Emblem_QuickDraft: "Quick Draft",
  LimitedChampionshipQualifier_Draft1: "LCQ Draft 1",
  LimitedChampionshipQualifier_Draft2: "LCQ Draft 2",
  PodDraft: "Pod Draft",
  MidWeekQuickDraft: "Quick Draft",
  MidWeekSealed: "Sealed",
  DraftChallenge: "Draft Challenge",
  OpenSealed_D1_Bo1: "Day 1 Sealed Bo1",
  OpenSealed_D1_Bo3: "Day 1 Sealed Bo3",
  OpenSealed_D2_Bo3: "Day 2 Sealed Bo3",
  OpenSealed_D2_Sealed1_Bo3: "Day 2 Sealed 1 Bo3",
  OpenDraft_D1_Bo1: "Day 1 Draft Bo1",
  OpenDraft_D1_Bo3: "Day 1 Draft Bo3",
  OpenDraft_D2_Bo3: "Day 2 Draft Bo3",
  OpenDraft_D2_Draft1_Bo3: "Day 2 Draft 1 Bo3",
  OpenDraft_D2_Draft2_Bo3: "Day 2 Draft 2 Bo3",
  OpenDraft_D2_Draft2B_Bo3: "Day 2 Draft 2B Bo3",
};

export function prettyFormat(format: string): string {
  return FORMAT_DISPLAY[format] ?? format;
}

export function eventDisplayLabel(event: { format: string; eventName?: string | null; setCode: string }): string {
  if (event.format === "PodDraft" && event.eventName) {
    return cleanPodEventName(event.eventName, event.setCode);
  }
  return prettyFormat(event.format);
}

export type FormatTag = { label: string; tone: "midweek" | "open" | "alchemy" };

export function formatTag(format: string, expansion?: string | null): FormatTag | null {
  if (format.startsWith("MidWeek")) return { label: "MidWeek Magic", tone: "midweek" };
  if (format.startsWith("Open")) return { label: "Arena Open", tone: "open" };
  if (expansion && expansion.startsWith("Y")) return { label: "Alchemy", tone: "alchemy" };
  return null;
}

export function lcqCashPrize(event: { format: string; wins: number; losses: number }): string | null {
  if (event.format !== "LimitedChampionshipQualifier_Draft2") return null;
  if (event.wins >= 6) return "$2K";
  if (event.wins === 5 && event.losses === 2) return "$1K";
  return null;
}

export function stripDiscriminator(name: string): string {
  return name.replace(/#\d+/, "").trim();
}

export function podDiscordName(p: {
  playerDisplayName: string | null;
  displayName: string;
}): string {
  return stripDiscriminator(p.playerDisplayName ?? p.displayName);
}

// A pod trophy is three match wins. A small pod's 2-1 winner takes 1st place without one, and a big
// pod can crown two 3-0s where only one of them carries placement 1.
export function isPodTrophyRecord(record: string | null | undefined): boolean {
  return Number((record ?? "").split("-")[0] || 0) >= POD_TROPHY_WINS;
}

export function podSeatName(p: { draftmancerName: string | null; displayName: string }): string {
  return p.draftmancerName ?? p.displayName;
}

export function cleanPodEventName(name: string, setCode: string): string {
  const tableMatch = name.match(/\s+(?:[-–]\s+)?Table\s+(\d+)\s*$/i);
  const tableSuffix = tableMatch ? ` - Table ${tableMatch[1]}` : "";
  const withoutTable = tableMatch ? name.slice(0, tableMatch.index).trim() : name;
  const escaped = setCode.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  let cleaned = withoutTable.replace(/\s+[-–]\s+.+$/, "").trim();
  // Cube events lead with an organizer name and the format label; keep only what follows "Cube"
  const afterCube = cleaned.replace(/^.*\bcube\b\s*/i, "").trim();
  if (afterCube && afterCube !== cleaned) {
    cleaned = afterCube;
  }
  // A custom format label with no "Cube" word still leads the date, so drop anything before it
  const dateStart = cleaned.search(POD_DATE_START_RE);
  if (dateStart > 0) {
    cleaned = cleaned.slice(dateStart).trim();
  }
  const withoutCode = cleaned
    .replace(new RegExp(`\\b${escaped}\\b`, "gi"), "")
    .replace(/\s{2,}/g, " ")
    .trim();
  return (withoutCode || cleaned) + tableSuffix;
}

// The slot phrase alone (`Early Pod`, `Late Pod`), stripped of set code, date, baked number, and any
// Table suffix. The date lives in the row's date box and the Table suffix renders separately, so
// neither belongs here.
export function podSlotName(name: string, setCode: string): string {
  const escaped = setCode.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return name
    .replace(/\s*[-–]?\s*Table\s+\d+\s*$/i, "")
    .replace(/#\d+/g, "")
    .replace(new RegExp(`\\b${escaped}\\b`, "gi"), "")
    .replace(POD_NAME_DATE_RE, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

// Unanchored: a format word can lead the date (`Peasant Cube Aug 14 Early Pod`)
const POD_DATE_START_RE =
  /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b/i;

const POD_NAME_DATE_RE = new RegExp(`\\s*[-–]?\\s*${POD_DATE_START_RE.source}`, "gi");

// Plain-string title (medallions, aria): `#15 Early Pod - Table 2` once run, the slot alone upcoming.
// PodEventTitle renders the styled version. Number is the execution-ordered ordinal, not any baked #N.
export function podEventTitle(event: {
  ordinal?: number | null;
  tableIndex?: number;
  name: string;
  setCode: string;
}): string {
  const slot = podSlotName(event.name, event.setCode);
  const qualifier = podEventQualifier(event);
  if (event.ordinal != null) {
    return `#${event.ordinal} ${slot}${qualifier}`;
  }
  return slot;
}

export function podEventQualifier(event: { tableIndex?: number }): string {
  if ((event.tableIndex ?? 1) > 1) return ` - Table ${event.tableIndex}`;
  return "";
}

// Set codes are uppercase in the data; URLs are case-insensitive.
export function canonicalSetCode(raw: string, sets: SetSummary[] | undefined): string {
  const known = sets?.find((s) => s.code.toLowerCase() === raw.toLowerCase());
  return known?.code ?? raw.toUpperCase();
}

// Arena swaps its cube every few sets, so the CUBE set splits into boards addressed as virtual set
// codes: one per cube (`CUBE-PLANAR`), plus a per-set season (`CUBE-SOS`) for the cube that recurs.
// Bare `CUBE` is not a board — it resolves to whichever cube is running. The base code drives the
// title and switcher chip, so they read "CUBE" whichever board is open.
export const CUBE_BASE = "CUBE";

// Retired: the lifetime board is now the seasoned cube's own board. Kept so old links still land.
export const CUBE_LIFETIME = `${CUBE_BASE}-ALL`;

export function isCubeSeasonCode(code: string): boolean {
  return code.startsWith(`${CUBE_BASE}-`);
}

// True for bare `CUBE` and every cube board (`CUBE-SOS`, `CUBE-PLANAR`).
export function isCubeCode(code: string): boolean {
  return baseSetCode(code) === CUBE_BASE;
}

export function baseSetCode(code: string): string {
  return isCubeSeasonCode(code) ? CUBE_BASE : code;
}

export function cubeSeasonLabel(code: string): string | null {
  return isCubeSeasonCode(code) ? code.slice(CUBE_BASE.length + 1) : null;
}

// The leaderboard is a lowercase section; set codes stay uppercase under it (/leaderboard/SOS).
export const LEADERBOARD_BASE = "/leaderboard";

// Player profiles live at their own top-level section, set-scoped as /player/<slug>/<SET>.
export const PLAYER_BASE = "/player";

export function leaderboardPath(setCode?: string): string {
  return setCode ? `${LEADERBOARD_BASE}/${setCode}` : LEADERBOARD_BASE;
}

export function playerPath(slug: string, setCode: string): string {
  return `${PLAYER_BASE}/${slug}/${setCode}`;
}

// Query string for a profile link: keeps the format/colors filter, drops the leaderboard-only sort
export function profileSearch(params: URLSearchParams | undefined): string {
  const search = new URLSearchParams(params);
  search.delete("sort");
  search.delete("dir");
  return search.toString();
}
