// Client-side derivations over the pod draft artifact (public_pod_draft_log). The deck view reads
// resolveDeck; the draft-review view reads reconstructDraft over the same artifact's packs/picks.

import type { Mainboard, MainboardCard, PodDraftArtifact } from "../types/leaderboard";

type ArtifactCard = PodDraftArtifact["cards"][number];

// One turn from a single seat's vantage: the booster exactly as that seat saw it, the positions taken,
// and the card indices taken. A Pick 2 draft takes two of each. Indices address the artifact card table.
export interface DraftPickView {
  booster: number[];
  takenPositions: number[];
  takenCards: number[];
}

const PASS_DIRS = [1, -1, 1];

// Replays the whole draft and captures every seat's view at every turn. Returns views[seat][pack][turn].
// The pass rotation mirrors bot/scripts/draftmancer_log.py::simulate so positions stay faithful.
export function reconstructDraft(artifact: PodDraftArtifact): DraftPickView[][][] {
  const n = artifact.seats.length;
  const perTurn = picksPerTurn(artifact);
  const views: DraftPickView[][][] = artifact.seats.map(() => [[], [], []]);
  for (let pack = 0; pack < 3; pack++) {
    let boosters = artifact.seats.map((_, seat) => [...artifact.packs[seat + pack * n]]);
    const dir = PASS_DIRS[pack];
    const turns = Math.floor((artifact.picks[0]?.[pack]?.length ?? 0) / perTurn);
    for (let turn = 0; turn < turns; turn++) {
      const positionsAt = artifact.seats.map((_, seat) =>
        artifact.picks[seat][pack].slice(turn * perTurn, turn * perTurn + perTurn),
      );
      for (let seat = 0; seat < n; seat++) {
        const booster = [...boosters[seat]];
        const positions = positionsAt[seat];
        views[seat][pack].push({ booster, takenPositions: positions, takenCards: positions.map((p) => booster[p]) });
      }
      for (let seat = 0; seat < n; seat++) {
        for (const pos of [...positionsAt[seat]].sort((a, b) => b - a)) {
          boosters[seat].splice(pos, 1);
        }
      }
      boosters = boosters.map((_, seat) => boosters[((seat - dir) % n + n) % n]);
    }
  }
  return views;
}

// Cards a seat takes per turn. Draftmancer records a Pick 2 turn as two positions in the same booster
// and the artifact stores them flat, so a 14-card pack reads exactly like 14 single picks — `pp` is
// what tells them apart. Artifacts written before Pick 2 existed carry no `pp` and are all single-pick.
export function picksPerTurn(artifact: PodDraftArtifact): number {
  return artifact.pp ?? 1;
}

// Card indices a seat has taken strictly before the given turn — the pool built up to this point.
export function poolBefore(views: DraftPickView[][][], seat: number, pack: number, pick: number): number[] {
  const out: number[] = [];
  for (let p = 0; p <= pack; p++) {
    const picks = views[seat][p];
    const upto = p < pack ? picks.length : pick;
    for (let k = 0; k < upto; k++) {
      out.push(...picks[k].takenCards);
    }
  }
  return out;
}

// The same pool grouped into one array per pack up to the current one — drives the order view's
// one-row-per-pack layout. The current pack only includes picks made before `pick`.
export function poolByPack(views: DraftPickView[][][], seat: number, pack: number, pick: number): number[][] {
  const rows: number[][] = [];
  for (let p = 0; p <= pack; p++) {
    const picks = views[seat][p];
    const upto = p < pack ? picks.length : pick;
    rows.push(picks.slice(0, upto).flatMap((v) => v.takenCards));
  }
  return rows;
}

// Draftmancer names carry a discriminator (`Noya#08011`); the board shows the bare handle.
export function seatHandle(name: string): string {
  const hash = name.indexOf("#");
  return hash === -1 ? name : name.slice(0, hash);
}

// A seat's built deck (maindeck + sideboard), grouped by name with counts and sorted by mana value.
// Returns null when the event predates deck capture (decks is null) or the seat built nothing. Basics
// are absent — they are never in the drafted pool.
export function resolveDeck(artifact: PodDraftArtifact, seatIndex: number): Mainboard | null {
  const deck = artifact.decks?.[seatIndex];
  if (!deck || deck.main.length === 0) {
    return null;
  }
  const deckSet = dominantSet(artifact, deck.main);
  return {
    set: deckSet,
    cards: resolveCards(artifact, deck.main, deckSet),
    sideboard: resolveCards(artifact, deck.side, deckSet),
  };
}

function dominantSet(artifact: PodDraftArtifact, indices: number[]): string | null {
  const tally = new Map<string, number>();
  for (const idx of indices) {
    const card = artifact.cards[idx];
    if (card?.s) {
      tally.set(card.s, (tally.get(card.s) ?? 0) + 1);
    }
  }
  let dominant: string | null = null;
  let best = 0;
  for (const [code, n] of tally) {
    if (n > best) {
      best = n;
      dominant = code;
    }
  }
  return dominant;
}

function resolveCards(artifact: PodDraftArtifact, indices: number[], deckSet: string | null): MainboardCard[] {
  const grouped = new Map<string, { card: ArtifactCard; count: number }>();
  for (const idx of indices) {
    const card = artifact.cards[idx];
    if (!card || card.n == null) {
      continue;
    }
    const existing = grouped.get(card.n);
    if (existing) {
      existing.count += 1;
    } else {
      grouped.set(card.n, { card, count: 1 });
    }
  }
  return [...grouped.values()]
    .sort((a, b) => (a.card.cmc ?? 99) - (b.card.cmc ?? 99) || a.card.n!.localeCompare(b.card.n!))
    .map(({ card, count }) => {
      const resolved: MainboardCard = { name: card.n!, cn: card.cn, cmc: card.cmc, type: card.type };
      if (card.s && card.s !== deckSet) {
        resolved.set = card.s;
      }
      if (card.c && card.c.length) {
        resolved.colors = card.c;
      }
      if (count > 1) {
        resolved.count = count;
      }
      return resolved;
    });
}
