import variantsConfig from "../../../cube_variants.json";
import type { CubeSeason, SetSummary } from "../types/leaderboard";
import { CUBE_BASE } from "./utils";

// Arena's cubes, in dropdown order. Same file bot/sets.py reads, so the two never drift.
export interface CubeVariant {
  slug: string;
  name: string;
  expansion: string;
  glyph: string;
  short?: string;
  seasoned: boolean;
  soup?: boolean;
  seasons?: CubeVariantSeason[];
  opens?: string;
}

// One declared run of a cube: a season of the powered cube, a plane's week of the planar cube
export interface CubeVariantSeason {
  code: string;
  label?: string;
  glyph?: string;
  start_date: string;
  end_date: string;
}

export const CUBE_VARIANTS: CubeVariant[] = variantsConfig.variants;

export const CUBE_BOARD_PREFIX = `${CUBE_BASE}-`;

export const cubeBoardCode = (slug: string) => `${CUBE_BOARD_PREFIX}${slug.toUpperCase()}`;

export function cubeVariant(slug: string): CubeVariant | undefined {
  const upper = slug.toUpperCase();
  return CUBE_VARIANTS.find((v) => v.slug === upper);
}

// The flagship cube, and the board the retired CUBE-ALL resolves to.
export const SEASONED_CUBE_VARIANT = CUBE_VARIANTS.find((v) => v.seasoned) ?? CUBE_VARIANTS[0];

// The board list keeps a WORD+CUBE convention, so a cube whose full name leads with Arena drops it
// there; "Arena Cube" keeps its own, since "Cube" alone names nothing. The hero prints the full name.
export function cubeListName(variant: CubeVariant): string {
  const withoutArena = variant.name.replace(/^Arena\s+/, "");
  return withoutArena.split(/\s+/).length >= 2 ? withoutArena : variant.name;
}

export function cubeVariantForBoard(code: string): CubeVariant | undefined {
  if (!code.startsWith(CUBE_BOARD_PREFIX)) {
    return undefined;
  }
  return cubeVariant(code.slice(CUBE_BOARD_PREFIX.length));
}

const SEASON_BY_CODE = new Map(
  CUBE_VARIANTS.flatMap((variant) =>
    (variant.seasons ?? []).map((season) => [season.code, { variant, season }] as const),
  ),
);

// The cube and run a season board names: "CUBE-PLANAR-ZEN" -> (Planar Cube, Zendikar Week)
export function cubeSeasonForBoard(code: string) {
  if (!code.startsWith(CUBE_BOARD_PREFIX)) {
    return undefined;
  }
  return SEASON_BY_CODE.get(code.slice(CUBE_BOARD_PREFIX.length).toUpperCase());
}

// The cube a board scores, in full or over one of its runs. Undefined for bare CUBE, whose board is
// whichever cube ran most recently.
export function cubeForBoard(code: string): CubeVariant | undefined {
  return cubeVariantForBoard(code) ?? cubeSeasonForBoard(code)?.variant;
}

// How a run names itself in the picker, for a board code that may no longer be declared. Mirrors
// CubeSeason.display_label in bot/sets.py.
export function cubeSeasonBoardLabel(code: string): string {
  const found = cubeSeasonForBoard(code);
  const label = found?.season.label ?? `${code.slice(CUBE_BOARD_PREFIX.length)} Season`;
  return label.toUpperCase();
}

// Every board of one cube shares its glyph, so a run reads as the cube that played it.
export function cubeBoardGlyphCode(code: string): string {
  const variant = cubeForBoard(code);
  return cubeBoardCode((variant ?? SEASONED_CUBE_VARIANT).slug);
}

// The board bare /leaderboard/CUBE lands on: the cube running now, or the last one that ran. Arena
// runs one cube at a time, so that is the variant holding the newest draft — resolved to its newest
// window when the cube keeps recurring. Mirrors latest_cube_board in bot/services/player_stats.py.
export function ongoingCubeBoard(seasons: CubeSeason[] | undefined): string | undefined {
  if (!seasons?.length) {
    return undefined;
  }
  const newestVariant = newestBoard(seasons.filter((s) => s.kind === "variant"));
  if (!newestVariant) {
    return undefined;
  }
  return latestWindowFor(newestVariant.setCode, seasons);
}

// A recurring cube opens on its most recent run, live or last played, since that is what the day is
// about; its lifetime board stays one click away under ALL SEASONS. A cube that ran once opens on
// its own board. Mirrors opens_latest_season in bot/sets.py.
export function latestWindowFor(board: string, seasons: CubeSeason[] | undefined): string {
  const variant = cubeVariantForBoard(board);
  if (variant?.opens === "board") {
    return board;
  }
  return newestBoard(cubeSeasonRows(variant, seasons))?.setCode ?? board;
}

// Board rows for one cube's declared runs. The view emits every cube's runs in one list and says
// nothing about which cube played them, so the registry is what separates them.
export function cubeSeasonRows(
  variant: CubeVariant | undefined,
  seasons: CubeSeason[] | undefined,
): CubeSeason[] {
  const declared = new Set((variant?.seasons ?? []).map((s) => s.code));
  return (seasons ?? []).filter((s) => s.kind === "season" && declared.has(s.label));
}

// Soup counts 4+ colours with 3+ of them main on cube, which on a multicolour cube swallows most of
// the board and says nothing. A cube can opt out; its seasons follow it.
export function boardOffersSoup(code: string): boolean {
  return cubeForBoard(code)?.soup !== false;
}

// A run is declared, never inferred: WotC schedules cube runs in advance, so LIVE means today falls
// inside a declared window rather than "somebody drafted recently". A cube with no declared run is
// never live, which is what a retired cube should read as.
export function isCubeBoardLive(board: string | undefined, today = todayIso()): boolean {
  if (!board) {
    return false;
  }
  const variant = cubeVariantForBoard(board);
  if (!variant) {
    const season = cubeSeasonForBoard(board)?.season;
    return !!season && today >= season.start_date && today <= season.end_date;
  }
  const windows = variant.seasons ?? [];
  return windows.some((r) => today >= r.start_date && today <= r.end_date);
}

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function newestBoard(rows: CubeSeason[]): CubeSeason | undefined {
  let newest: CubeSeason | undefined;
  for (const row of rows) {
    if (!newest || row.lastEvent > newest.lastEvent) {
      newest = row;
    }
  }
  return newest;
}

// Each cube is its own board in the set list, sorted into the timeline by when it last ran, so a cube
// sits beside the sets it ran alongside instead of hiding behind one shared CUBE entry.
export function setsWithCubeBoards(
  sets: SetSummary[] | undefined,
  seasons: CubeSeason[] | undefined,
): SetSummary[] | undefined {
  if (!sets) {
    return undefined;
  }
  const runByCode = new Map(
    (seasons ?? []).filter((s) => s.kind === "variant").map((s) => [s.setCode, s]),
  );
  const cubes: SetSummary[] = [];
  for (const variant of CUBE_VARIANTS) {
    const code = cubeBoardCode(variant.slug);
    const run = runByCode.get(code);
    if (!run?.lastEvent) {
      continue;
    }
    cubes.push({
      code,
      name: cubeListName(variant),
      shortCode: variant.short ?? variant.slug,
      glyphCode: CUBE_BASE,
      startDate: run.lastEvent,
      endDate: run.lastEvent,
      isActive: isCubeBoardLive(code),
    });
  }
  return [...sets.filter((s) => s.code !== CUBE_BASE), ...cubes];
}
