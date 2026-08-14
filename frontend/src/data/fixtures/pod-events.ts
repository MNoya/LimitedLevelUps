import type {
  PodDraftArtifact,
  PodEventMatchRow,
  PodEventParticipantRow,
  PodEventReplayRow,
  PodEventSummary,
  PodLeaderboardRow,
} from "../../types/leaderboard";
import { podSos3Fixture, type PodParticipant } from "./pod-sos-3";

function participantToRow(p: PodParticipant): PodEventParticipantRow {
  return {
    eventId: p.eventId,
    displayName: p.displayName,
    draftmancerName: p.displayName,
    seatIndex: p.seatIndex,
    placement: p.placement ?? null,
    record: p.record,
    deckColors: p.deckColors,
    deckScreenshotUrl: p.deckScreenshotUrl,
    deckScreenshotCaption: p.deckScreenshotCaption,
    playerSlug: p.slug,
    playerDisplayName: p.displayName,
    avatarUrl: null,
  };
}

function summaryFromFixture(): PodEventSummary {
  const champion = podSos3Fixture.participants.find((p) => p.placement === 1);
  return {
    eventId: podSos3Fixture.id,
    slug: podSos3Fixture.slug,
    name: podSos3Fixture.name,
    setCode: podSos3Fixture.setCode,
    kind: "tournament",
    eventDate: podSos3Fixture.date,
    eventTime: `${podSos3Fixture.date}T20:00:00Z`,
    formatLabel: podSos3Fixture.formatLabel,
    totalRounds: podSos3Fixture.totalRounds,
    championPlayerSlug: champion?.slug ?? null,
    championDisplayName: champion?.displayName ?? null,
    championAvatarUrl: null,
    championDeckColors: champion?.deckColors ?? null,
    championRecord: champion?.record ?? null,
    participantCount: podSos3Fixture.participants.length,
    isFinalized: podSos3Fixture.participants.every((p) => p.placement != null),
  };
}

const extraSummaries: PodEventSummary[] = [
  {
    eventId: "mock-sos-mock-1",
    slug: "sos-mock-draft-1",
    name: "SOS Mock Draft 1",
    setCode: "SOS",
    kind: "mock",
    eventDate: "2026-05-21",
    eventTime: "2026-05-21T20:00:00Z",
    formatLabel: null,
    totalRounds: 0,
    championPlayerSlug: null,
    championDisplayName: null,
    championAvatarUrl: null,
    championDeckColors: null,
    championRecord: null,
    participantCount: 8,
    isFinalized: true,
  },
  {
    eventId: "mock-sos-4",
    slug: "sos-pod-draft-4",
    name: "SOS Pod Draft #4",
    setCode: "SOS",
    kind: "tournament",
    eventDate: "2026-05-20",
    eventTime: "2026-05-20T20:00:00Z",
    formatLabel: "Pod Draft · Swiss · 3 Rounds",
    totalRounds: 3,
    championPlayerSlug: null,
    championDisplayName: null,
    championAvatarUrl: null,
    championDeckColors: null,
    championRecord: null,
    participantCount: 0,
    isFinalized: false,
  },
  {
    eventId: "mock-sos-2",
    slug: "sos-pod-draft-2",
    name: "SOS Pod Draft #2",
    setCode: "SOS",
    kind: "tournament",
    eventDate: "2026-05-07",
    eventTime: "2026-05-07T20:00:00Z",
    formatLabel: "Pod Draft · Swiss · 3 Rounds",
    totalRounds: 3,
    championPlayerSlug: "elfandor",
    championDisplayName: "Elfandor",
    championAvatarUrl: null,
    championDeckColors: "WR",
    championRecord: "3-0",
    participantCount: 8,
    isFinalized: true,
  },
  {
    eventId: "mock-sos-1",
    slug: "sos-pod-draft-1",
    name: "SOS Pod Draft #1",
    setCode: "SOS",
    kind: "tournament",
    eventDate: "2026-04-30",
    eventTime: "2026-04-30T20:00:00Z",
    formatLabel: "Pod Draft · Swiss · 3 Rounds",
    totalRounds: 3,
    championPlayerSlug: "noya",
    championDisplayName: "Noya",
    championAvatarUrl: null,
    championDeckColors: "WU",
    championRecord: "3-0",
    participantCount: 8,
    isFinalized: true,
  },
];

// Peasant Cube preview: a finalized custom-format pod that reuses the SOS-3 roster so its event
// page renders, plus a scheduled one. set_code "PEASANT" has no row in the sets table.
const PEASANT_EVENT_ID = "mock-peasant-1";
const PEASANT_NAME = "Peasant Cube Pod Draft #1";

const peasantSummaries: PodEventSummary[] = [
  {
    ...summaryFromFixture(),
    eventId: PEASANT_EVENT_ID,
    slug: "peasant-cube-pod-draft-1",
    name: PEASANT_NAME,
    setCode: "PEASANT",
    eventDate: "2026-05-22",
    eventTime: "2026-05-22T20:00:00Z",
    formatLabel: "Peasant Cube",
  },
  {
    eventId: "mock-peasant-2",
    slug: "peasant-cube-pod-draft-2",
    name: "Peasant Cube Pod Draft #2",
    setCode: "PEASANT",
    kind: "tournament",
    eventDate: "2026-05-29",
    eventTime: "2026-05-29T20:00:00Z",
    formatLabel: "Peasant Cube",
    totalRounds: 3,
    championPlayerSlug: null,
    championDisplayName: null,
    championAvatarUrl: null,
    championDeckColors: null,
    championRecord: null,
    participantCount: 0,
    isFinalized: false,
  },
];

const peasantParticipants: PodEventParticipantRow[] = podSos3Fixture.participants.map((p) => ({
  ...participantToRow(p),
  eventId: PEASANT_EVENT_ID,
}));

const peasantMatches: PodEventMatchRow[] = podSos3Fixture.matches.map((m) => ({
  eventId: PEASANT_EVENT_ID,
  eventName: PEASANT_NAME,
  round: m.round,
  playerAName: m.playerA,
  playerBName: m.playerB,
  winnerName: m.winner,
  score: m.score,
  reportedAt: m.reportedAt,
}));

export const podEventsFixture: PodEventSummary[] = [
  summaryFromFixture(),
  ...extraSummaries,
  ...peasantSummaries,
];

const mockParticipants: PodEventParticipantRow[] = podSos3Fixture.participants.map((p, i) => ({
  ...participantToRow(p),
  eventId: "mock-sos-mock-1",
  seatIndex: i,
  placement: null,
  record: null,
}));

export const podEventParticipantsFixture: PodEventParticipantRow[] = [
  ...podSos3Fixture.participants.map(participantToRow),
  ...peasantParticipants,
  ...mockParticipants,
];

const mockArtifactCards: PodDraftArtifact["cards"] = [
  { n: "Galvanic Discharge", cn: "131", s: "sos", r: "common", c: ["R"], cmc: 1, type: "Instant" },
  { n: "Iridescent Vinelasher", cn: "98", s: "sos", r: "uncommon", c: ["G"], cmc: 2, type: "Creature" },
  { n: "Sentinel of the Nameless City", cn: "201", s: "sos", r: "rare", c: ["G"], cmc: 3, type: "Creature" },
  { n: "Heated Argument", cn: "118", s: "sos", r: "common", c: ["R"], cmc: 3, type: "Instant" },
  { n: "Wystan, Trinket Trapper", cn: "224", s: "sos", r: "rare", c: ["R", "G"], cmc: 4, type: "Creature" },
  { n: "Drakeskin Construct", cn: "247", s: "sos", r: "common", c: [], cmc: 5, type: "Artifact Creature" },
  { n: "Mountain", cn: "279", s: "sos", r: "common", c: [], cmc: 0, type: "Basic Land" },
  { n: "Forest", cn: "281", s: "sos", r: "common", c: [], cmc: 0, type: "Basic Land" },
];

export const podDraftArtifactFixture: Record<string, PodDraftArtifact> = {
  "mock-sos-mock-1": {
    v: 2,
    set: "sos",
    seats: mockParticipants.map((p) => p.draftmancerName ?? p.displayName),
    cards: mockArtifactCards,
    packs: [],
    picks: [],
    decks: mockParticipants.map((_, i) =>
      i === 0 ? { main: [0, 1, 1, 2, 3, 4, 5, 6, 7], side: [2, 3, 5] } : { main: [], side: [] },
    ),
  },
};

const inProgressMatches: PodEventMatchRow[] = [
  { round: 1, playerAName: "Noya", playerBName: "Elfandor", winnerName: "Noya", score: "2-1" },
  { round: 1, playerAName: "WaveofShadow", playerBName: "flutterdev", winnerName: "WaveofShadow", score: "2-0" },
  { round: 1, playerAName: "Oophies", playerBName: "adoodwithgood", winnerName: "Oophies", score: "2-1" },
  { round: 1, playerAName: "samp", playerBName: "Lark", winnerName: "samp", score: "2-0" },
  { round: 2, playerAName: "WaveofShadow", playerBName: "Noya", winnerName: "WaveofShadow", score: "2-1" },
  { round: 2, playerAName: "samp", playerBName: "Oophies", winnerName: null, score: null },
  { round: 2, playerAName: "Elfandor", playerBName: "flutterdev", winnerName: null, score: null },
  { round: 2, playerAName: "adoodwithgood", playerBName: "Lark", winnerName: null, score: null },
].map((m) => ({ ...m, eventId: "mock-sos-4", eventName: "SOS Pod Draft #4", reportedAt: null }));

export const podEventMatchesFixture: PodEventMatchRow[] = [
  ...podSos3Fixture.matches.map((m) => ({
    eventId: m.eventId,
    eventName: podSos3Fixture.name,
    round: m.round,
    playerAName: m.playerA,
    playerBName: m.playerB,
    winnerName: m.winner,
    score: m.score,
    reportedAt: m.reportedAt,
  })),
  ...peasantMatches,
  ...inProgressMatches,
];

export const podEventReplaysFixture: PodEventReplayRow[] = podSos3Fixture.replays.map((r) => ({
  eventId: r.eventId,
  eventName: r.eventName,
  eventDate: r.eventDate,
  setCode: r.setCode,
  playerId: r.playerId,
  playerSlug: r.playerSlug,
  playerDisplayName: r.playerDisplayName,
  gameId: r.gameId,
  link: r.link,
  gameTime: r.gameTime,
  won: r.won,
  turns: r.turns,
  onPlay: r.onPlay,
  inferredRound: r.inferredRound,
}));

function leaderboardRowsForSet(setCode: string): Omit<PodLeaderboardRow, "rank">[] {
  return podSos3Fixture.participants.map((p) => {
    const wins = Number(p.record.split("-")[0] || 0);
    const losses = Number(p.record.split("-")[1] || 0);
    return {
      setCode,
      slug: p.slug,
      displayName: p.displayName,
      avatarUrl: null,
      events: 1,
      wins,
      losses,
      trophies: p.placement === 1 ? 1 : 0,
      lastFinishedAt: `${podSos3Fixture.date}T22:00:00Z`,
    };
  });
}

export const podLeaderboardFixtureRaw: Omit<PodLeaderboardRow, "rank">[] = [
  ...leaderboardRowsForSet(podSos3Fixture.setCode),
  ...leaderboardRowsForSet("PEASANT"),
];

export const podSetCodesFixture = [
  { code: "SOS", label: null, events: 3 },
  { code: "MSH", label: null, events: 3 },
  { code: "PEASANT", label: "Peasant Cube", events: 2 },
];
