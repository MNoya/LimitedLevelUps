import { describe, expect, it } from "vitest";

import {
  buildChampionshipBracket,
  buildSwissRounds,
  championOf,
  championshipPodNumber,
  championshipViewFromSegment,
  pickPodWildcard,
  projectChampionshipSeats,
  type ChampionshipEntrant,
  type ChampionshipRsvp,
} from "./setChampionship";
import type { PodEventMatchRow } from "../types/leaderboard";

describe("buildSwissRounds", () => {
  it("groups each round by record and marks the unbeaten last-round match as the final", () => {
    const matches = finishedChampionship();

    const rounds = buildSwissRounds(matches, 3);

    expect(rounds.map((round) => round.groups.map(describeGroup))).toEqual([
      ["0-0: A-B C-D E-F G-H"],
      ["1-0: A-E C-H", "0-1: G-D B-F"],
      ["2-0 final: A-H", "0-2: G-B"],
    ]);
    expect(championOf(rounds)).toBe("H");
  });

  it("feeds the tree from the unbeaten path", () => {
    const rounds = buildSwissRounds(finishedChampionship(), 3);

    const bracket = buildChampionshipBracket(rounds);

    expect(bracket.quarterfinals.map(pairing)).toEqual(["A-B", "E-F", "C-D", "G-H"]);
    expect(bracket.semifinals.map(pairing)).toEqual(["A-E", "C-H"]);
    expect(pairing(bracket.final)).toBe("A-H");
  });

  it("leaves later rounds empty before they are paired", () => {
    const matches = [match(1, "A", "B", "A"), match(1, "C", "D", null)];

    const rounds = buildSwissRounds(matches, 3);

    expect(rounds.map((round) => round.groups.length)).toEqual([1, 0, 0]);
    expect(championOf(rounds)).toBeNull();
  });
});

describe("projectChampionshipSeats", () => {
  it.each([
    {
      name: "holds the last seat for the wildcard",
      entrants: [...ranked(1, 10, null), entrant(15, null, true)],
      seated: [1, 2, 3, 4, 5, 6, 7, 15],
    },
    {
      name: "seats the best-ranked Yes answers once everyone has answered",
      entrants: [...ranked(1, 3, "no"), ...ranked(4, 12, "yes")],
      seated: [4, 5, 6, 7, 8, 9, 10, 11],
    },
  ])("$name", ({ entrants, seated }) => {
    const seats = projectChampionshipSeats(entrants);

    expect(seats.map((seat) => seat.rank)).toEqual(seated);
  });
});

describe("split championships", () => {
  it.each([
    { name: "👑 TLA Set Championship Pod 2", pod: 2 },
    { name: "👑 TLA Set Championship", pod: null },
  ])("reads the pod number from $name", ({ name, pod }) => {
    const number = championshipPodNumber(name);

    expect(number).toBe(pod);
  });

  it.each([
    { segment: undefined, view: "table" },
    { segment: "pod-1", view: "pod-1" },
    { segment: "top-8", view: "top8" },
    { segment: "pods", view: null },
  ])("maps the $segment segment to a view", ({ segment, view }) => {
    const resolved = championshipViewFromSegment(segment);

    expect(resolved).toBe(view);
  });
});

describe("pickPodWildcard", () => {
  it.each([
    { name: "skips pod players already inside the seat cut", podOrder: ["p3", "p12", "p20"], wildcard: "p12" },
    { name: "takes a pod player missing from the board", podOrder: ["p1", "newcomer"], wildcard: "newcomer" },
    { name: "names nobody when every pod player is inside the cut", podOrder: ["p2", "p8"], wildcard: null },
  ])("$name", ({ podOrder, wildcard }) => {
    const board = Array.from({ length: 30 }, (_, index) => ({ slug: `p${index + 1}`, rank: index + 1 }));

    const pick = pickPodWildcard(board, podOrder.map((slug) => ({ slug })));

    expect(pick).toBe(wildcard);
  });
});

function ranked(first: number, last: number, rsvp: ChampionshipRsvp | null): ChampionshipEntrant[] {
  const entrants: ChampionshipEntrant[] = [];
  for (let rank = first; rank <= last; rank++) {
    entrants.push(entrant(rank, rsvp));
  }
  return entrants;
}

function entrant(rank: number, rsvp: ChampionshipRsvp | null, wildcard = false): ChampionshipEntrant {
  return {
    rank,
    slug: `p${rank}`,
    displayName: `Player ${rank}`,
    avatarUrl: null,
    score: 100 - rank,
    trophies: null,
    wildcard,
    rsvp,
  };
}

function finishedChampionship(): PodEventMatchRow[] {
  return [
    match(1, "A", "B", "A"),
    match(1, "C", "D", "C"),
    match(1, "E", "F", "E"),
    match(1, "G", "H", "H"),
    match(2, "A", "E", "A"),
    match(2, "C", "H", "H"),
    match(2, "G", "D", "D"),
    match(2, "B", "F", "F"),
    match(3, "A", "H", "H"),
    match(3, "C", "E", "(skipped)"),
    match(3, "G", "B", "B"),
  ];
}

function pairing(row: PodEventMatchRow | undefined): string {
  return row ? `${row.playerAName}-${row.playerBName}` : "-";
}

function match(round: number, playerAName: string, playerBName: string, winnerName: string | null): PodEventMatchRow {
  return {
    eventId: "event",
    eventName: "Set Championship",
    round,
    playerAName,
    playerBName,
    winnerName,
    score: winnerName ? "2-1" : null,
    reportedAt: winnerName ? "2026-09-19T18:00:00Z" : null,
  };
}

function describeGroup(group: { wins: number; losses: number; isFinal: boolean; matches: PodEventMatchRow[] }): string {
  const pairings = group.matches.map((row) => `${row.playerAName}-${row.playerBName}`).join(" ");
  return `${group.wins}-${group.losses}${group.isFinal ? " final" : ""}: ${pairings}`;
}
