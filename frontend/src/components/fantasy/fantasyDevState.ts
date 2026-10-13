import { createDevPresetStore } from "../../lib/dev-preset-store";
import type { DevStateOption } from "../DevStatePanel";
import type { FantasyEventState } from "../../types/fantasy";
import type { FantasyEventEntry } from "./fantasyEvents";

export type FantasyDevPreset =
  | "live"
  | "pickingSignedIn"
  | "pickingLoggedOut"
  | "dayOne"
  | "cut"
  | "dayTwo"
  | "bracketOpen"
  | "quarterfinalsDone"
  | "final";

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
];

const presetStore = createDevPresetStore<FantasyDevPreset>(
  "fantasyDevPreset",
  FANTASY_DEV_PRESETS.map((preset) => preset.value),
  "live",
);

export const setFantasyDevPreset = presetStore.set;
export const useFantasyDevPreset = presetStore.useValue;

export function devPresetState(
  preset: FantasyDevPreset,
  state: FantasyEventState,
  event: FantasyEventEntry,
  now: number,
): FantasyEventState {
  if (preset === "live") {
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

function presetRound(preset: Exclude<FantasyDevPreset, "live">, event: FantasyEventEntry): number {
  const rounds: Record<Exclude<FantasyDevPreset, "live">, number> = {
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
