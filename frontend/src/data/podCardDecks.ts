import { mainColors, stripDiscriminator, wubrgSort } from "./utils";
import { POD_TROPHY_WINS } from "./scoring";

// Reads public_pod_card_decks: one row per drafted card per seat, closed decklists hidden until finalized
export interface PodCardDeckRow {
  set_code: string;
  season: string;
  card_name: string;
  card_set: string | null;
  event_id: string;
  event_slug: string;
  event_name: string;
  event_date: string;
  event_time: string;
  seat: number;
  pack_num: number | null;
  pick_num: number;
  maindecked: boolean;
  display_name: string;
  player_slug: string | null;
  player_display_name: string | null;
  avatar_url: string | null;
  deck_colors: string | null;
  record: string | null;
  placement: number | null;
  deck_screenshot_url: string | null;
  deck_screenshot_caption: string | null;
}

export interface PodCardDeck {
  eventId: string;
  eventSlug: string;
  eventName: string;
  eventDate: string;
  eventTime: string;
  season: string;
  seat: number;
  packNum: number | null;
  pickNum: number;
  maindecked: boolean;
  displayName: string;
  participantDisplayName: string;
  playerSlug: string | null;
  avatarUrl: string | null;
  deckColors: string | null;
  record: string | null;
  wins: number;
  losses: number;
  placement: number | null;
  isTrophy: boolean;
  deckScreenshotUrl: string | null;
  deckScreenshotCaption: string | null;
}

export function adaptPodCardDeck(row: PodCardDeckRow): PodCardDeck {
  const [w, l] = (row.record ?? "").split("-");
  const wins = parseInt(w || "0", 10) || 0;
  const losses = parseInt(l || "0", 10) || 0;
  return {
    eventId: row.event_id,
    eventSlug: row.event_slug,
    eventName: row.event_name,
    eventDate: row.event_date,
    eventTime: row.event_time,
    season: row.season,
    seat: row.seat,
    packNum: row.pack_num,
    pickNum: row.pick_num,
    maindecked: row.maindecked,
    displayName: row.player_display_name ?? stripDiscriminator(row.display_name),
    participantDisplayName: row.display_name,
    playerSlug: row.player_slug,
    avatarUrl: row.avatar_url,
    deckColors: row.deck_colors,
    record: row.record,
    wins,
    losses,
    placement: row.placement,
    isTrophy: wins >= POD_TROPHY_WINS,
    deckScreenshotUrl: row.deck_screenshot_url,
    deckScreenshotCaption: row.deck_screenshot_caption,
  };
}

export function cardSlug(name: string): string {
  const front = name.split("//")[0];
  return front
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export const PICKS_PER_PACK = 15;

export interface PodCardSummary {
  taken: number;
  maindecks: number;
  trophies: number;
  matchWins: number;
  matchLosses: number;
  pickCurve: number[];
  colorPairs: PodCardColorPair[];
}

interface PodCardColorPair {
  colors: string;
  decks: number;
  wins: number;
  losses: number;
}

export function summarizeCardDecks(decks: PodCardDeck[]): PodCardSummary {
  const pickCurve: number[] = Array.from({ length: PICKS_PER_PACK }, () => 0);
  const pairs = new Map<string, PodCardColorPair>();
  let maindecks = 0;
  let trophies = 0;
  let matchWins = 0;
  let matchLosses = 0;
  for (const deck of decks) {
    const slot = Math.min(deck.pickNum, PICKS_PER_PACK) - 1;
    pickCurve[slot] += 1;
    if (!deck.maindecked) {
      continue;
    }
    maindecks += 1;
    matchWins += deck.wins;
    matchLosses += deck.losses;
    if (deck.isTrophy) {
      trophies += 1;
    }
    const colors = wubrgSort(mainColors(deck.deckColors));
    if (!colors) {
      continue;
    }
    const pair = pairs.get(colors) ?? { colors, decks: 0, wins: 0, losses: 0 };
    pair.decks += 1;
    pair.wins += deck.wins;
    pair.losses += deck.losses;
    pairs.set(colors, pair);
  }
  const colorPairs = [...pairs.values()].sort((a, b) => b.decks - a.decks || b.wins - a.wins);
  return { taken: decks.length, maindecks, trophies, matchWins, matchLosses, pickCurve, colorPairs };
}

export function sortDecksRecentFirst(decks: PodCardDeck[]): PodCardDeck[] {
  return [...decks].sort((a, b) => (a.eventTime < b.eventTime ? 1 : a.eventTime > b.eventTime ? -1 : a.seat - b.seat));
}

export type PodDeckCardRow = Pick<PodCardDeckRow, "event_id" | "seat" | "card_name" | "card_set">;

export interface CoPlayedCard {
  name: string;
  set: string | null;
  decks: number;
}

export function coPlayedCards(
  rows: PodDeckCardRow[],
  decks: PodCardDeck[],
  cardName: string,
): CoPlayedCard[] {
  const seats = new Set<string>();
  for (const deck of decks) {
    if (deck.maindecked) {
      seats.add(`${deck.eventId}|${deck.seat}`);
    }
  }
  const counts = new Map<string, CoPlayedCard>();
  for (const row of rows) {
    if (row.card_name === cardName || !seats.has(`${row.event_id}|${row.seat}`)) {
      continue;
    }
    const entry = counts.get(row.card_name) ?? { name: row.card_name, set: row.card_set, decks: 0 };
    entry.decks += 1;
    counts.set(row.card_name, entry);
  }
  return [...counts.values()].sort((a, b) => b.decks - a.decks || a.name.localeCompare(b.name));
}
