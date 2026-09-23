import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

// Card art resolves through /api/card-images (Scryfall batch → CDN URLs); the browser never hits Scryfall directly

export interface CardImageItem {
  name: string | null;
  set: string | null;
}

export interface CardImages {
  images: Map<string, string>;
  ready: boolean;
  settled?: ReadonlySet<string>;
}

function frontFaceName(name: string): string {
  const separator = name.indexOf("//");
  return (separator === -1 ? name : name.slice(0, separator)).trim();
}

function mapKey(set: string | null | undefined, name: string): string {
  return `${(set ?? "").toLowerCase()}|${frontFaceName(name).toLowerCase()}`;
}

function namedImageUrl(name: string, set?: string): string {
  const setParam = set ? `&set=${set.toLowerCase()}` : "";
  const exact = encodeURIComponent(frontFaceName(name));
  return `https://api.scryfall.com/cards/named?exact=${exact}${setParam}&format=image&version=normal`;
}

function dedupeIdentifiers(items: CardImageItem[]): { name: string; set: string }[] {
  const byKey = new Map<string, { name: string; set: string }>();
  for (const item of items) {
    if (!item.name || !item.set) {
      continue;
    }
    const key = mapKey(item.set, item.name);
    if (!byKey.has(key)) {
      byKey.set(key, { name: item.name, set: item.set });
    }
  }
  return [...byKey.values()];
}

async function fetchCardImages(identifiers: { name: string; set: string }[]): Promise<Record<string, string>> {
  if (identifiers.length === 0) {
    return {};
  }
  const res = await fetch("/api/card-images", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ identifiers }),
  });
  return res.ok ? ((await res.json()) as Record<string, string>) : {};
}

// One app-wide card->URL map shared by every caller, persisted to localStorage; a hook resolves only its missing cards
const CACHE_KEY = "cardimg:v2";
const memoryMap = new Map<string, string>();
let hydrated = false;

function hydrate(): void {
  if (hydrated) {
    return;
  }
  hydrated = true;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (raw) {
      for (const [key, url] of Object.entries(JSON.parse(raw) as Record<string, string>)) {
        memoryMap.set(key, url);
      }
    }
  } catch {
    return;
  }
}

function persist(): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(Object.fromEntries(memoryMap)));
  } catch {
    return;
  }
}

// Resolves art for items against the shared map: fetches only missing cards, merges + persists, returns a ready flag
export function useCardImageMap(items: CardImageItem[]): CardImages {
  hydrate();
  const identifiers = useMemo(() => dedupeIdentifiers(items), [items]);
  const missing = useMemo(
    () => identifiers.filter((id) => !memoryMap.has(mapKey(id.set, id.name))),
    [identifiers],
  );
  const missingSignature = useMemo(
    () => missing.map((id) => mapKey(id.set, id.name)).sort().join(","),
    [missing],
  );
  const { isFetching } = useQuery({
    queryKey: ["card-images", missingSignature],
    queryFn: () => resolveIntoMap(missing),
    enabled: missing.length > 0,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  return useMemo(
    () => ({ images: new Map(memoryMap), ready: missing.length === 0 || !isFetching }),
    [missing.length, isFetching],
  );
}

// Resolves the on-screen cards in a small request first, then the whole board in one request the edge caches for every visitor
export function useBoardCardImages(board: CardImageItem[], visible: CardImageItem[]): CardImages {
  hydrate();
  const boardIds = useMemo(() => dedupeIdentifiers(board), [board]);
  const boardSignature = useMemo(() => boardIds.map((id) => mapKey(id.set, id.name)).sort().join(","), [boardIds]);
  const boardMissing = boardIds.some((id) => !memoryMap.has(mapKey(id.set, id.name)));
  const visibleIds = dedupeIdentifiers(visible);
  const visibleMissing = visibleIds.filter((id) => !memoryMap.has(mapKey(id.set, id.name)));
  const visibleSignature = visibleMissing.map((id) => mapKey(id.set, id.name)).sort().join(",");

  const onScreen = useQuery({
    queryKey: ["card-images", visibleSignature],
    queryFn: () => resolveIntoMap(visibleMissing),
    enabled: visibleMissing.length > 0,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const wholeBoard = useQuery({
    queryKey: ["card-images-board", boardSignature],
    queryFn: () => resolveIntoMap(boardIds),
    enabled: boardMissing,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const boardSettled = !boardMissing || wholeBoard.status !== "pending";
  const onScreenSettled = onScreen.fetchStatus !== "fetching";
  return useMemo(() => {
    const settled = new Set<string>();
    if (onScreenSettled) {
      for (const id of visibleIds) {
        settled.add(mapKey(id.set, id.name));
      }
    }
    return { images: new Map(memoryMap), ready: boardSettled, settled: boardSettled ? undefined : settled };
  }, [boardSettled, onScreenSettled, visibleSignature, onScreen.dataUpdatedAt]);
}

async function resolveIntoMap(identifiers: { name: string; set: string }[]): Promise<Record<string, string>> {
  const fetched = await fetchCardImages(identifiers);
  for (const [key, url] of Object.entries(fetched)) {
    memoryMap.set(key, url);
  }
  persist();
  return fetched;
}

// <img> src candidates for a card, best first: the mapped CDN URL, then Scryfall's named endpoint
export function cardImageSources(
  name: string | null | undefined,
  set: string | null | undefined,
  cardImages?: CardImages,
): string[] {
  if (!name) {
    return [];
  }
  const mapped = cardImages?.images.get(mapKey(set, name));
  const fallback = [set ? namedImageUrl(name, set) : null, namedImageUrl(name)].filter(
    (url): url is string => url != null,
  );
  if (mapped) {
    return [mapped, ...fallback];
  }
  const settled = cardImages?.settled;
  const ready = settled ? settled.has(mapKey(set, name)) : (cardImages?.ready ?? true);
  return ready ? fallback : [];
}

// Like cardImageSources but rewritten to Scryfall's art_crop for a frameless thumbnail
export function cardArtSources(
  name: string | null | undefined,
  set: string | null | undefined,
  cardImages?: CardImages,
): string[] {
  return cardImageSources(name, set, cardImages).map((url) =>
    url.includes("cards.scryfall.io/") ? url.replace("/normal/", "/art_crop/") : url.replace("version=normal", "version=art_crop"),
  );
}
