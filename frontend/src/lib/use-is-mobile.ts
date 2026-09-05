import React from "react";

// Single source of truth for the responsive cutover. Pages and the header all
// consult this so layouts stay in sync. Lives in /lib so React Fast Refresh
// doesn't complain about mixed component+hook exports.

export function useIsMobile(breakpoint = 720): boolean {
  const [isMobile, setIsMobile] = React.useState<boolean>(
    typeof window !== "undefined" ? window.innerWidth < breakpoint : false
  );
  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${breakpoint - 1}px)`);
    const handler = (e: MediaQueryListEvent | MediaQueryList) => setIsMobile(e.matches);
    handler(mql);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [breakpoint]);
  return isMobile;
}

export function useIsLandscapePhone(): boolean {
  const query = "(orientation: landscape) and (max-height: 520px)";
  const [matches, setMatches] = React.useState<boolean>(
    typeof window !== "undefined" ? window.matchMedia(query).matches : false
  );
  React.useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent | MediaQueryList) => setMatches(e.matches);
    handler(mql);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);
  return matches;
}

export function useIsCompact(): boolean {
  const isMobile = useIsMobile();
  const isLandscapePhone = useIsLandscapePhone();
  return isMobile || isLandscapePhone;
}

const SET_VISIBLE_BREAKPOINTS: Array<[number, number]> = [
  [1400, 6],
  [1100, 5],
];

const VISIBLE_FLOOR = 2;
const NARROW_VISIBLE = 4;

function computeVisibleCap(): number {
  if (typeof window === "undefined") return NARROW_VISIBLE;
  for (const [w, cap] of SET_VISIBLE_BREAKPOINTS) {
    if (window.matchMedia(`(min-width: ${w}px)`).matches) return cap;
  }
  return NARROW_VISIBLE;
}

export function useSetVisibleCap(total: number, extraHide = 0): number {
  const [cap, setCap] = React.useState<number>(computeVisibleCap);
  React.useEffect(() => {
    const mqls = SET_VISIBLE_BREAKPOINTS.map(([w]) =>
      window.matchMedia(`(min-width: ${w}px)`),
    );
    const update = () => setCap(computeVisibleCap());
    mqls.forEach((m) => m.addEventListener("change", update));
    update();
    return () => mqls.forEach((m) => m.removeEventListener("change", update));
  }, []);
  return Math.max(VISIBLE_FLOOR, Math.min(total, cap - extraHide));
}

const ORGANIZER_COLUMN_BREAKPOINTS: Array<[number, number]> = [
  [1024, 3],
  [768, 2],
];

function computeOrganizerColumns(): number {
  if (typeof window === "undefined") return 1;
  for (const [w, cols] of ORGANIZER_COLUMN_BREAKPOINTS) {
    if (window.matchMedia(`(min-width: ${w}px)`).matches) return cols;
  }
  return 1;
}

export function useOrganizerColumns(): number {
  const [columns, setColumns] = React.useState<number>(computeOrganizerColumns);
  React.useEffect(() => {
    const mqls = ORGANIZER_COLUMN_BREAKPOINTS.map(([w]) => window.matchMedia(`(min-width: ${w}px)`));
    const update = () => setColumns(computeOrganizerColumns());
    mqls.forEach((m) => m.addEventListener("change", update));
    update();
    return () => mqls.forEach((m) => m.removeEventListener("change", update));
  }, []);
  return columns;
}

const EPISODE_GRID_BREAKPOINTS: Array<[number, number]> = [
  [1536, 4],
  [1280, 3],
  [640, 2],
];

function computeEpisodeColumns(): number {
  if (typeof window === "undefined") return 4;
  for (const [w, cols] of EPISODE_GRID_BREAKPOINTS) {
    if (window.matchMedia(`(min-width: ${w}px)`).matches) return cols;
  }
  return 1;
}

export function useEpisodeGridColumns(): number {
  const [columns, setColumns] = React.useState<number>(computeEpisodeColumns);
  React.useEffect(() => {
    const mqls = EPISODE_GRID_BREAKPOINTS.map(([w]) =>
      window.matchMedia(`(min-width: ${w}px)`),
    );
    const update = () => setColumns(computeEpisodeColumns());
    mqls.forEach((m) => m.addEventListener("change", update));
    update();
    return () => mqls.forEach((m) => m.removeEventListener("change", update));
  }, []);
  return columns;
}
