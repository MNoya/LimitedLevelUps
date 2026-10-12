export type FantasySavedPick = { slot: string; playerId: number; fromRound: number };

export type FantasyEventState = {
  revealedThroughRound: number;
  completedThroughRound: number;
  picksLockAt: string;
  dayTwoStartedAt: string | null;
  bracketLockAt: string;
  top8StartedAt: string | null;
};

export type FantasyFieldRow = {
  id: number;
  slug: string;
  firstName: string;
  lastName: string;
  shortName: string | null;
  country: string | null;
  countryCode: string | null;
  sources: string[];
  photoUrl: string | null;
  deckName: string | null;
  decklistId: string | null;
};

export type FantasyResultRow = {
  round: number;
  playerId: number;
  opponentId: number | null;
  stage: "swiss" | "quarterfinal" | "semifinal" | "final";
  result: "W" | "L" | "D";
  gameWins: number;
  gameLosses: number;
  gameDraws: number;
  isBye: boolean;
  bracketPosition: string | null;
};

export type FantasyMemberRow = { memberKey: string; isMe: boolean; name: string; avatarUrl: string | null; rank: number };

export type FantasyLineupRow = { memberKey: string; isMe: boolean; slot: string; fromRound: number; playerId: number };

export type FantasyBracketPickRow = { memberKey: string; isMe: boolean; position: string; winnerId: number; games: string | null };

export type FantasyOwnBracketPick = { position: string; winnerId: number; games: string | null };
