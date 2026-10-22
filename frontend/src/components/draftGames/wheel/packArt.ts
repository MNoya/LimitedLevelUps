import { useEffect, useMemo, useState } from "react";

import { cardImageSources, hasCardImage, useCardImageMap, type CardImages } from "../../../data/cardImages";
import type { WheelPack } from "../../../data/draftGames";

export function packArtResolved(pack: WheelPack | undefined, cardImages: CardImages): boolean {
  if (!pack) {
    return false;
  }
  return (
    cardImages.ready || pack.pack.every((card) => hasCardImage(cardImages, pack.cards[card].n, pack.cards[card].s))
  );
}

export function usePreloadPackArt(pack: WheelPack | undefined, cardImages: CardImages) {
  const resolved = packArtResolved(pack, cardImages);
  useEffect(() => {
    if (!pack || !resolved) {
      return;
    }
    for (const card of pack.pack) {
      preloadImage(cardImageSources(pack.cards[card].n, pack.cards[card].s, cardImages)[0]);
    }
  }, [pack, resolved, cardImages]);
}

export function useCurrentPackFirstImages(packs: WheelPack[], current: number, allAtOnce = false): CardImages {
  const [lookAhead, setLookAhead] = useState(allAtOnce);
  const cardImages = useCardImageMap(
    useMemo(() => {
      const lookupPacks = lookAhead ? packs : packs.slice(current, current + 1);
      return lookupPacks.flatMap((pack) => pack.pack.map((i) => ({ name: pack.cards[i].n, set: pack.cards[i].s })));
    }, [packs, current, lookAhead]),
  );
  if (!lookAhead && packArtResolved(packs[current], cardImages)) {
    setLookAhead(true);
  }
  return cardImages;
}

export function usePackDealtAt(pack: WheelPack | undefined, cards: number[], cardImages: CardImages): number | null {
  const [dealtAt, setDealtAt] = useState<number | null>(null);
  const dealt = dealtAt != null;
  const deal = () => setDealtAt(performance.now());
  const eventId = pack?.eventId;
  const artResolved = packArtResolved(pack, cardImages);
  const sources: string[] = [];
  if (pack && artResolved) {
    for (const card of cards) {
      const src = cardImageSources(pack.cards[card].n, pack.cards[card].s, cardImages)[0];
      if (src) {
        sources.push(src);
      }
    }
  }
  const sourceList = sources.join("\n");

  useEffect(() => {
    if (dealt || !eventId) {
      return;
    }
    const giveUp = window.setTimeout(deal, 8000);
    return () => window.clearTimeout(giveUp);
  }, [dealt, eventId]);

  useEffect(() => {
    if (dealt || !artResolved) {
      return;
    }
    const urls = sourceList ? sourceList.split("\n") : [];
    let pending = urls.length;
    if (pending === 0) {
      deal();
      return;
    }
    const settle = () => {
      pending -= 1;
      if (pending === 0) {
        deal();
      }
    };
    const loaders = urls.map((src) => {
      const image = new Image();
      image.onload = settle;
      image.onerror = settle;
      image.src = src;
      return image;
    });
    return () => {
      for (const image of loaders) {
        image.onload = null;
        image.onerror = null;
      }
    };
  }, [dealt, artResolved, sourceList]);

  return dealtAt;
}

function preloadImage(src: string | undefined) {
  if (src) {
    new Image().src = src;
  }
}
