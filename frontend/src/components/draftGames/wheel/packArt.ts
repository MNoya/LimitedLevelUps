import { useEffect } from "react";

import { cardImageSources, hasCardImage, type CardImages } from "../../../data/cardImages";
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

function preloadImage(src: string | undefined) {
  if (src) {
    new Image().src = src;
  }
}
