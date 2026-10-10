import type { PodSetCode, SetSummary } from "../types/leaderboard";

// Registered custom cube formats, mirrored from CUSTOM_FORMATS in bot/services/pod_format.py.
// The bot owns the canonical mapping; keep the cube ids and labels here in sync when it changes.

interface PodCustomFormat {
  code: string;
  label: string;
  cubeId: string;
  listed?: boolean;
}

const CUSTOM_FORMATS: PodCustomFormat[] = [
  { code: "PEASANT", label: "Peasant Cube", cubeId: "DaneeliusPeasantAllStars", listed: true },
  { code: "MEMA", label: "Middle-Earth Masters", cubeId: "MEMA" },
  { code: "SAMP", label: "samp Cube", cubeId: "samp" },
];

const BY_CODE = new Map(CUSTOM_FORMATS.map((f) => [f.code, f]));

function customFormat(code: string | undefined): PodCustomFormat | undefined {
  return code ? BY_CODE.get(code.toUpperCase()) : undefined;
}

export function cubeCobraUrl(code: string | undefined): string | null {
  const fmt = customFormat(code);
  return fmt ? `https://cubecobra.com/cube/list/${fmt.cubeId}` : null;
}

export function customFormatLabel(code: string | undefined): string | undefined {
  return customFormat(code)?.label;
}

export async function fetchCubeCardNames(code: string): Promise<Set<string> | null> {
  const fmt = customFormat(code);
  if (!fmt) {
    return null;
  }
  const response = await fetch(`https://cubecobra.com/cube/api/cubelist/${fmt.cubeId}`);
  if (!response.ok) {
    throw new Error(`CubeCobra list ${fmt.cubeId}: ${response.status}`);
  }
  const names = (await response.text()).split("\n").map((line) => line.trim());
  return new Set(names.filter(Boolean));
}

export interface PodBoardWindow {
  board: string;
  season?: string;
}

export function podBoardWindowFor(code: string): PodBoardWindow | undefined {
  const whole = customFormat(code);
  if (whole) {
    return { board: whole.code };
  }
  const split = code.lastIndexOf("-");
  if (split <= 0) {
    return undefined;
  }
  const board = customFormat(code.slice(0, split));
  return board ? { board: board.code, season: code.slice(split + 1).toUpperCase() } : undefined;
}

export function podBoardCode(board: string, season?: string): string {
  return season ? `${board}-${season}` : board;
}

export const MIN_BOARD_PODS = 2;

export function podBoardSet(p: PodSetCode): SetSummary {
  const custom = p.label != null;
  return {
    code: p.code,
    name: p.label ?? p.code,
    startDate: "",
    endDate: "",
    isActive: false,
    early: !custom && p.mocks > 0,
    custom,
  };
}

export function withCustomPodBoards(
  sets: SetSummary[] | undefined,
  podSetCodes: PodSetCode[] | undefined,
): SetSummary[] | undefined {
  if (!sets) {
    return undefined;
  }
  const known = new Set(sets.map((s) => s.code));
  const boards = (podSetCodes ?? [])
    .filter((p) => customFormat(p.code)?.listed && !known.has(p.code) && p.events >= MIN_BOARD_PODS)
    .map((p) => ({ ...podBoardSet(p), startDate: p.lastEvent, endDate: p.lastEvent }));
  return [...sets, ...boards];
}
