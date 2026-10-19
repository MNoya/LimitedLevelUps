import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { frontFace } from "../lib/cardSlug";
import { cachedImageUrl } from "../lib/dev-image-cache";
import { scryfallWebp } from "./scryfallImage";

// Card art resolves through /api/card-images (Scryfall batch → CDN URLs); the browser never hits Scryfall directly

export interface CardImageItem {
  name: string | null;
  set: string | null;
}

export interface CardImages {
  images: Map<string, string>;
  layouts?: Map<string, string>;
  ready: boolean;
  settled?: ReadonlySet<string>;
}

function mapKey(set: string | null | undefined, name: string): string {
  return `${(set ?? "").toLowerCase()}|${frontFace(name).toLowerCase()}`;
}

function namedImageUrl(name: string, set?: string): string {
  const setParam = set ? `&set=${set.toLowerCase()}` : "";
  const exact = encodeURIComponent(frontFace(name));
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

interface ResolvedCards {
  images: Record<string, string>;
  layouts: Record<string, string>;
}

async function fetchCardImages(identifiers: { name: string; set: string }[]): Promise<ResolvedCards> {
  if (identifiers.length === 0) {
    return { images: {}, layouts: {} };
  }
  const res = await fetch("/api/card-images", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ identifiers }),
  });
  if (!res.ok) {
    return { images: {}, layouts: {} };
  }
  const body = (await res.json()) as Partial<ResolvedCards> | Record<string, string>;
  if (typeof body.images === "object" && body.images) {
    return { images: body.images as Record<string, string>, layouts: (body.layouts ?? {}) as Record<string, string> };
  }
  return { images: body as Record<string, string>, layouts: {} };
}

// One app-wide card->URL map shared by every caller, persisted to localStorage; a hook resolves only its missing cards
const CACHE_KEY = "cardimg:v3";
const LAYOUT_CACHE_KEY = "cardlayout:v1";
const memoryMap = new Map<string, string>();
const layoutMap = new Map<string, string>();
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
    const rawLayouts = localStorage.getItem(LAYOUT_CACHE_KEY);
    if (rawLayouts) {
      for (const [key, layout] of Object.entries(JSON.parse(rawLayouts) as Record<string, string>)) {
        layoutMap.set(key, layout);
      }
    }
  } catch {
    return;
  }
}

function persist(): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(Object.fromEntries(memoryMap)));
    localStorage.setItem(LAYOUT_CACHE_KEY, JSON.stringify(Object.fromEntries(layoutMap)));
  } catch {
    return;
  }
}

// Resolves art for items against the shared map: fetches only missing cards, merges + persists, returns a ready flag
export function useCardImageMap(items: CardImageItem[]): CardImages {
  hydrate();
  const identifiers = useMemo(() => dedupeIdentifiers(items), [items]);
  const missing = useMemo(
    () => identifiers.filter((id) => !memoryMap.has(mapKey(id.set, id.name)) || needsLayout(id)),
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
    () => ({ images: new Map(memoryMap), layouts: new Map(layoutMap), ready: missing.length === 0 || !isFetching }),
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
  for (const [key, url] of Object.entries(fetched.images)) {
    memoryMap.set(key, url);
  }
  for (const [key, layout] of Object.entries(fetched.layouts)) {
    layoutMap.set(key, layout);
  }
  persist();
  return fetched.images;
}

function needsLayout(id: { name: string; set: string }): boolean {
  return id.name.includes("//") && !layoutMap.has(mapKey(id.set, id.name));
}

export function cardLayout(cardImages: CardImages, name: string | null | undefined, set: string | null | undefined) {
  return name ? cardImages.layouts?.get(mapKey(set, name)) : undefined;
}

// A fixed card->URL map from images already known, such as a set pool, so nothing is resolved over the network
export function cardImagesFromUrls(set: string, cards: { name: string; image: string | null }[]): CardImages {
  const images = new Map<string, string>();
  for (const card of cards) {
    if (card.image) {
      images.set(mapKey(set, card.name), card.image);
    }
  }
  return { images, ready: true };
}

// Layers known URLs over a resolved map, so a card the pool already names never waits on or loses to a lookup
export function withKnownImages(resolved: CardImages, known: CardImages): CardImages {
  return { ...resolved, images: new Map([...resolved.images, ...known.images]) };
}

// <img> src candidates for a card, best first: the mapped CDN URL, then Scryfall's named endpoint
export function cardImageSources(
  name: string | null | undefined,
  set: string | null | undefined,
  cardImages?: CardImages,
): string[] {
  return scryfallImageSources(name, set, cardImages).map(cachedImageUrl);
}

export function hasCardImage(cardImages: CardImages, name: string | null | undefined, set: string | null | undefined) {
  return name != null && cardImages.images.has(mapKey(set, name));
}

// Like cardImageSources but rewritten to Scryfall's art crop for a frameless thumbnail
export function cardArtSources(
  name: string | null | undefined,
  set: string | null | undefined,
  cardImages?: CardImages,
): string[] {
  const artUrls = scryfallImageSources(name, set, cardImages).map((url) =>
    url.includes("cards.scryfall.io/") ? scryfallWebp(url, "art") : url.replace("version=normal", "version=art_crop"),
  );
  return artUrls.map(cachedImageUrl);
}

function scryfallImageSources(
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
