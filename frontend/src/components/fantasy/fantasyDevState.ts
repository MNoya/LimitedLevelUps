import { createDevPresetStore, devToolsEnabled } from "../../lib/dev-preset-store";
import type { DevStateOption } from "../DevStatePanel";
import type { FantasyEventState } from "../../types/fantasy";
import type { FantasyEventEntry } from "./fantasyEvents";
import type { EventPhase } from "./fantasyScoring";

export type FantasyDevPreset =
  | "live"
  | "pickingSignedIn"
  | "pickingLoggedOut"
  | "dayOne"
  | "cut"
  | "dayTwo"
  | "bracketOpen"
  | "quarterfinalsDone"
  | "final"
  | "skeleton";

export const FANTASY_DEV_PRESETS: DevStateOption<FantasyDevPreset>[] = [
  { value: "live", group: "Live", label: "Live" },
  { value: "pickingSignedIn", group: "Picking", label: "Signed in" },
  { value: "pickingLoggedOut", group: "Picking", label: "Logged out" },
  { value: "dayOne", group: "Day 1", label: "Round 4 live" },
  { value: "cut", group: "Cut", label: "Day 1 complete" },
  { value: "dayTwo", group: "Day 2", label: "Round 12 live" },
  { value: "bracketOpen", group: "Top 8", label: "Bracket open" },
  { value: "quarterfinalsDone", group: "Top 8", label: "Quarterfinals done" },
  { value: "final", group: "Final", label: "Event complete" },
  { value: "skeleton", group: "Loading", label: "Skeleton" },
];

export const DEMO_PRESETS = FANTASY_DEV_PRESETS.filter((preset) => preset.value !== "skeleton");

export const LOADING_PRESETS = FANTASY_DEV_PRESETS.filter((preset) => ["live", "skeleton"].includes(preset.value));

const presetStore = createDevPresetStore<FantasyDevPreset>(
  "fantasyDevPreset",
  FANTASY_DEV_PRESETS.map((preset) => preset.value),
  "live",
  typeof window !== "undefined",
);

export const setFantasyDevPreset = presetStore.set;

export function demoPresetsAllowed(event: FantasyEventEntry): boolean {
  return devToolsEnabled || !event.live;
}

export function useFantasyDevPreset(event: FantasyEventEntry | undefined): FantasyDevPreset {
  const preset = presetStore.useValue();
  return event && demoPresetsAllowed(event) ? preset : "live";
}

export function readsDemoData(preset: FantasyDevPreset, state: FantasyEventState): boolean {
  return preset !== "live" && preset !== "skeleton" && !state.completedThroughRound;
}

export function devPresetState(
  preset: FantasyDevPreset,
  state: FantasyEventState,
  event: FantasyEventEntry,
  now: number,
): FantasyEventState {
  if (preset === "live" || preset === "skeleton") {
    return state;
  }
  const hour = 60 * 60 * 1000;
  const past = new Date(now - hour).toISOString();
  const round = presetRound(preset, event);
  const picking = preset === "pickingSignedIn" || preset === "pickingLoggedOut";
  return {
    revealedThroughRound: round,
    completedThroughRound: round,
    picksLockAt: picking ? new Date(now + 48 * hour).toISOString() : past,
    dayTwoStartedAt: round > event.cutRound ? past : null,
    top8StartedAt: round > event.swissRounds ? past : null,
    bracketLockAt: round > event.swissRounds ? past : new Date(now + 24 * hour).toISOString(),
  };
}

function presetRound(preset: Exclude<FantasyDevPreset, "live" | "skeleton">, event: FantasyEventEntry): number {
  const rounds: Record<Exclude<FantasyDevPreset, "live" | "skeleton">, number> = {
    pickingSignedIn: 0,
    pickingLoggedOut: 0,
    dayOne: 3,
    cut: event.cutRound,
    dayTwo: event.cutRound + 4,
    bracketOpen: event.swissRounds,
    quarterfinalsDone: event.swissRounds + 1,
    final: event.swissRounds + 3,
  };
  return rounds[preset];
}

export function picksAtPreviewPhase<T extends { fromRound: number }>(picks: T[], phase: EventPhase): T[] {
  if (phase === "picking") {
    return [];
  }
  if (phase === "day1" || phase === "cut") {
    return picks.filter((pick) => pick.fromRound === 1);
  }
  return picks;
}
