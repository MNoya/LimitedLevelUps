import { isCubeSeasonCode } from "../data/utils";
import {
  cubeBoardCode, cubeForBoard, cubeSeasonBoardLabel, cubeSeasonRows, SEASONED_CUBE_VARIANT,
} from "../data/cubeVariants";
import { CalendarRange } from "./Icons";
import type { CubeSeason } from "../types/leaderboard";
import { BoardWindowSelector, type BoardWindowOption } from "./BoardWindowSelector";

// A cube runs in declared windows; this picks which one the board scores over. Which cube you are
// on is chosen in the set list beside the sets, so this list holds only that cube's runs.
const seasonOption = (season: CubeSeason): BoardWindowOption => ({
  value: season.setCode,
  label: cubeSeasonBoardLabel(season.setCode),
  glyph: season.setCode,
});

export function CubeSeasonSelector({
  activeSet,
  seasons,
  onSelect,
  variant = "hero",
}: {
  activeSet: string;
  seasons: CubeSeason[] | undefined;
  onSelect: (setCode: string) => void;
  variant?: "hero" | "mobile";
}) {
  const cube = cubeForBoard(activeSet) ?? SEASONED_CUBE_VARIANT;
  const wholeBoard = cubeBoardCode(cube.slug);
  const value = isCubeSeasonCode(activeSet) ? activeSet : wholeBoard;
  const rowByCode = new Map((seasons ?? []).map((s) => [s.setCode, s]));
  const windows = cubeSeasonRows(cube, seasons).map(seasonOption);
  windows.sort((a, b) =>
    (rowByCode.get(b.value)?.lastEvent ?? "").localeCompare(rowByCode.get(a.value)?.lastEvent ?? ""),
  );
  if (windows.length === 0) {
    return null;
  }
  const options: BoardWindowOption[] = [
    { value: wholeBoard, label: "ALL SEASONS", icon: <CalendarRange size={20} className="text-white shrink-0" /> },
    ...windows,
  ];
  return <BoardWindowSelector value={value} options={options} onSelect={onSelect} variant={variant} />;
}

// True for a cube that splits into declared runs, and for those runs themselves, which carry a run
// code rather than a cube slug and so match no variant.
export function cubeBoardHasSeasons(code: string): boolean {
  return cubeForBoard(code)?.seasoned ?? false;
}
