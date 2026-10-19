import { useMemo, useState } from "react";

import { useCardImageMap } from "../../../data/cardImages";
import { useFreePlayPacks } from "../../../data/draftGames";
import { usePreloadPackArt } from "./packArt";

export function quickSeed(): number {
  const saved = Number(sessionStorage.getItem(QUICK_SEED_KEY));
  if (saved > 0) {
    return saved;
  }
  return rotateQuickSeed();
}

export function rotateQuickSeed(): number {
  const seed = Math.floor(Math.random() * 1_000_000) + 1;
  sessionStorage.setItem(QUICK_SEED_KEY, String(seed));
  return seed;
}

export function useQuickPreload(setCode: string | undefined) {
  const [seed] = useState(quickSeed);
  const { packs } = useFreePlayPacks(setCode ?? "", 1, seed);
  const firstPack = packs[0];
  const images = useCardImageMap(
    useMemo(
      () => (firstPack ? firstPack.pack.map((i) => ({ name: firstPack.cards[i].n, set: firstPack.cards[i].s })) : []),
      [firstPack],
    ),
  );
  usePreloadPackArt(firstPack, images);
}

const QUICK_SEED_KEY = "wheel-of-fortune-quick-seed";
