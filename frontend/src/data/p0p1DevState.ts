import { useSyncExternalStore } from "react";

export type P0P1DevPreset =
  | "live"
  | "closedLoggedOut"
  | "closedComplete"
  | "closedDidNotVote"
  | "midwayScoring"
  | "midwayDidNotVote"
  | "finalScoring"
  | "finalLoggedOut";

export const P0P1_DEV_PRESETS: { value: P0P1DevPreset; group: string; label: string }[] = [
  { value: "live", group: "Live", label: "Live" },
  { value: "closedLoggedOut", group: "Voting", label: "Logged out" },
  { value: "closedComplete", group: "Voting", label: "Complete entry" },
  { value: "closedDidNotVote", group: "Voting", label: "Didn't vote" },
  { value: "midwayScoring", group: "Midway", label: "Complete entry" },
  { value: "midwayDidNotVote", group: "Midway", label: "Didn't vote" },
  { value: "finalScoring", group: "Final", label: "Complete entry" },
  { value: "finalLoggedOut", group: "Final", label: "Logged out" },
];

export const p0p1DevEnabled = import.meta.env.DEV && typeof window !== "undefined";

const STORAGE_KEY = "p0p1DevPreset";
const listeners = new Set<() => void>();

function readStored(): P0P1DevPreset {
  if (!p0p1DevEnabled) return "live";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  const valid = P0P1_DEV_PRESETS.some((p) => p.value === stored);
  return valid ? (stored as P0P1DevPreset) : "live";
}

let current = readStored();

export function setP0P1DevPreset(preset: P0P1DevPreset) {
  current = preset;
  window.localStorage.setItem(STORAGE_KEY, preset);
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void) {
  listeners.add(notify);
  return () => listeners.delete(notify);
}

export function useP0P1DevPreset(): P0P1DevPreset {
  return useSyncExternalStore(subscribe, () => current, () => "live");
}

// Forces the viewer's synthetic ballot (finalScoring preset) into a chosen
// standings position so the best-possible badge and 1st/2nd/3rd medal
// treatments can be previewed without waiting for real submissions to land there.
export type P0P1DevSelfPlacement = "auto" | "best" | "first" | "second" | "third";

export const P0P1_DEV_SELF_PLACEMENTS: { value: P0P1DevSelfPlacement; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "best", label: "Best possible" },
  { value: "first", label: "1st" },
  { value: "second", label: "2nd" },
  { value: "third", label: "3rd" },
];

const SELF_PLACEMENT_STORAGE_KEY = "p0p1DevSelfPlacement";
const selfPlacementListeners = new Set<() => void>();

function readStoredSelfPlacement(): P0P1DevSelfPlacement {
  if (!p0p1DevEnabled) return "auto";
  const stored = window.localStorage.getItem(SELF_PLACEMENT_STORAGE_KEY);
  const valid = P0P1_DEV_SELF_PLACEMENTS.some((p) => p.value === stored);
  return valid ? (stored as P0P1DevSelfPlacement) : "auto";
}

let currentSelfPlacement = readStoredSelfPlacement();

export function setP0P1DevSelfPlacement(placement: P0P1DevSelfPlacement) {
  currentSelfPlacement = placement;
  window.localStorage.setItem(SELF_PLACEMENT_STORAGE_KEY, placement);
  selfPlacementListeners.forEach((notify) => notify());
}

function subscribeSelfPlacement(notify: () => void) {
  selfPlacementListeners.add(notify);
  return () => selfPlacementListeners.delete(notify);
}

export function useP0P1DevSelfPlacement(): P0P1DevSelfPlacement {
  return useSyncExternalStore(subscribeSelfPlacement, () => currentSelfPlacement, () => "auto");
}

const DEV_RESULTS_REMAINING_MS = (20 * 24 + 1) * 60 * 60 * 1000;
const DEV_PAST_SCORING_MS = 60 * 60 * 1000;

export function p0p1Now(scoringDate?: Date): number {
  if (!p0p1DevEnabled || current === "live") return Date.now();
  const anchor = scoringDate?.getTime() ?? Date.now();
  if (current === "finalScoring" || current === "finalLoggedOut") {
    return anchor + DEV_PAST_SCORING_MS;
  }
  return anchor - DEV_RESULTS_REMAINING_MS;
}
