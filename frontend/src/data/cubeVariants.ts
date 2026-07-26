import variantsConfig from "../../../cube_variants.json";
import type { CubeSeason } from "../types/leaderboard";
import { CUBE_BASE } from "./utils";

// Arena's cubes, in dropdown order. Same file bot/sets.py reads, so the two never drift.
export interface CubeVariant {
  slug: string;
  name: string;
  expansion: string;
  glyph: string;
  seasoned: boolean;
  soup?: boolean;
}

export const CUBE_VARIANTS: CubeVariant[] = variantsConfig.variants;

export const CUBE_BOARD_PREFIX = `${CUBE_BASE}-`;

export const cubeBoardCode = (slug: string) => `${CUBE_BOARD_PREFIX}${slug.toUpperCase()}`;

export function cubeVariant(slug: string): CubeVariant | undefined {
  const upper = slug.toUpperCase();
  return CUBE_VARIANTS.find((v) => v.slug === upper);
}

// The cube whose drafts split into per-set season boards, and the board CUBE-ALL now resolves to.
export const SEASONED_CUBE_VARIANT = CUBE_VARIANTS.find((v) => v.seasoned) ?? CUBE_VARIANTS[0];

export function cubeVariantForBoard(code: string): CubeVariant | undefined {
  if (!code.startsWith(CUBE_BOARD_PREFIX)) {
    return undefined;
  }
  return cubeVariant(code.slice(CUBE_BOARD_PREFIX.length));
}

// Every board of one cube shares its glyph, so a season reads as the cube that ran it.
export function cubeBoardGlyphCode(code: string): string {
  const variant = cubeVariantForBoard(code);
  return variant ? cubeBoardCode(variant.slug) : cubeBoardCode(SEASONED_CUBE_VARIANT.slug);
}

// The board bare /leaderboard/CUBE lands on: the cube running now, or the last one that ran. Arena
// runs one cube at a time, so that is the variant holding the newest draft — resolved to its newest
// season when it is the seasoned cube. Mirrors latest_cube_board in bot/services/player_stats.py.
export function ongoingCubeBoard(seasons: CubeSeason[] | undefined): string | undefined {
  if (!seasons?.length) {
    return undefined;
  }
  const newestVariant = newestBoard(seasons.filter((s) => s.kind === "variant"));
  if (!newestVariant) {
    return undefined;
  }
  if (!cubeVariant(newestVariant.label)?.seasoned) {
    return newestVariant.setCode;
  }
  return newestBoard(seasons.filter((s) => s.kind === "season"))?.setCode ?? newestVariant.setCode;
}

// Soup counts 4+ colours with 3+ of them main on cube, which on a multicolour cube swallows most of
// the board and says nothing. A cube can opt out; its seasons follow it.
export function boardOffersSoup(code: string): boolean {
  return cubeVariantForBoard(code)?.soup !== false;
}

// A run is over once the cube goes a week without a draft, the same gap that anchors a season burst.
const BURST_GAP_MS = 7 * 24 * 60 * 60 * 1000;

export function isCubeBoardLive(board: CubeSeason | undefined): boolean {
  if (!board?.lastEvent) {
    return false;
  }
  const last = new Date(`${board.lastEvent}T00:00:00Z`).getTime();
  return Date.now() - last <= BURST_GAP_MS;
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
