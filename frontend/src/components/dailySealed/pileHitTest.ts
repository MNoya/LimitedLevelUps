import type { Layout, PileTarget, PileZone } from "../../data/dailySealedLayout";

export const DROP_ZONE_ATTR = "data-drop-zone";
export const PILE_ROW_ATTR = "data-pile-row";
export const PILE_ATTR = "data-pile";
export const PILE_CARDS_ATTR = "data-pile-cards";
export const CARD_INDEX_ATTR = "data-card-index";

export const sameTarget = (a: PileTarget | null, b: PileTarget | null) =>
  a === b ||
  (a !== null && b !== null && a.zone === b.zone && a.row === b.row && a.pile === b.pile && a.position === b.position);

export const pileTargetAt = (
  x: number,
  y: number,
  layout: Layout,
  dragged: number[],
  gap: number,
  width: number,
): PileTarget | null => {
  const zoneEl = zoneAt(x, y);
  if (!zoneEl) {
    return null;
  }
  const moving = new Set(dragged);
  const zone = zoneEl.getAttribute(DROP_ZONE_ATTR);
  if (zone === "hidden") {
    const others = layout.hidden.filter((index) => !moving.has(index));
    const list = zoneEl.querySelector<HTMLElement>(`[${PILE_CARDS_ATTR}]`);
    const position = list ? positionIn(list, y, others, moving) : others.length;
    return { zone: "hidden", row: 0, pile: 0, position };
  }
  const pileZone = zone as PileZone;
  const rowEls = [...zoneEl.querySelectorAll<HTMLElement>(`[${PILE_ROW_ATTR}]`)];
  if (rowEls.length === 0) {
    return null;
  }
  let rowEl = rowEls[0];
  for (const candidate of rowEls) {
    if (candidate.getBoundingClientRect().top <= y) {
      rowEl = candidate;
    }
  }
  const row = Number(rowEl.getAttribute(PILE_ROW_ATTR));
  const piles = layout[pileZone][row] ?? [];
  const pileEls = [...rowEl.querySelectorAll<HTMLElement>(`[${PILE_ATTR}]`)];
  for (const pileEl of pileEls) {
    if (x < pileEl.getBoundingClientRect().right + gap / 2) {
      const pile = Number(pileEl.getAttribute(PILE_ATTR));
      const others = (piles[pile]?.cards ?? []).filter((index) => !moving.has(index));
      const list = pileEl.querySelector<HTMLElement>(`[${PILE_CARDS_ATTR}]`);
      const position = list ? positionIn(list, y, others, moving) : others.length;
      return { zone: pileZone, row, pile, position };
    }
  }
  return { zone: pileZone, row, pile: columnPast(pileEls, rowEl, piles.length, x, gap, width), position: 0 };
};

const columnPast = (
  pileEls: HTMLElement[],
  rowEl: HTMLElement,
  piles: number,
  x: number,
  gap: number,
  width: number,
) => {
  const last = pileEls[pileEls.length - 1];
  const start = last ? last.getBoundingClientRect().right + gap : rowEl.getBoundingClientRect().left;
  return piles + Math.max(0, Math.floor((x - start) / (width + gap)));
};

const zoneAt = (x: number, y: number): HTMLElement | null => {
  let found: HTMLElement | null = null;
  for (const el of document.querySelectorAll<HTMLElement>(`[${DROP_ZONE_ATTR}]`)) {
    const rect = el.getBoundingClientRect();
    const inside = x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
    if (!inside) {
      continue;
    }
    if (el.getAttribute(DROP_ZONE_ATTR) === "hidden") {
      return el;
    }
    found = el;
  }
  return found;
};

const positionIn = (list: HTMLElement, y: number, others: number[], moving: Set<number>) => {
  const reveal = Number(list.dataset.reveal) || 1;
  const shown = [...list.querySelectorAll<HTMLElement>(`[${CARD_INDEX_ATTR}]`)]
    .map((el) => ({ index: Number(el.getAttribute(CARD_INDEX_ATTR)), strip: Number(el.dataset.strip) || reveal }))
    .filter((card) => !moving.has(card.index));
  let slotTop = list.getBoundingClientRect().top;
  for (const card of shown) {
    if (y < slotTop + card.strip) {
      return Math.max(0, others.indexOf(card.index));
    }
    slotTop += card.strip;
  }
  return others.length;
};
