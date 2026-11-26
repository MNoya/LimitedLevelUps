import { useLayoutEffect, useState, type RefObject } from "react";

import { PILE_GAP } from "./piles";

const MIN_CARD_WIDTH = 118;
const MAX_CARD_WIDTH = 220;
const COLUMNS_TO_FIT = 7;
const PANE_PADDING = 18;

export const fittedCardWidth = (paneWidth: number, piles: number) => {
  if (paneWidth === 0) {
    return MIN_CARD_WIDTH;
  }
  const columns = Math.max(COLUMNS_TO_FIT, piles);
  const fit = Math.floor((paneWidth - PANE_PADDING - PILE_GAP * columns) / columns);
  return Math.min(MAX_CARD_WIDTH, Math.max(MIN_CARD_WIDTH, fit));
};

export const useWidth = (ref: RefObject<HTMLElement | null>) => useMeasured(ref, (element) => element.clientWidth);

export const useHeight = (ref: RefObject<HTMLElement | null>) => useMeasured(ref, (element) => element.offsetHeight);

const useMeasured = (ref: RefObject<HTMLElement | null>, read: (element: HTMLElement) => number) => {
  const [size, setSize] = useState(0);
  const [element, setElement] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (ref.current !== element) {
      setElement(ref.current);
    }
  });
  useLayoutEffect(() => {
    if (!element) {
      return;
    }
    setSize(read(element));
    const observer = new ResizeObserver(() => setSize(read(element)));
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return size;
};
