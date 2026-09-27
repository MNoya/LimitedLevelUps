import type { Rarity } from "./Brand";

export function WildcardIcon({ rarity, size }: { rarity: Rarity; size: number }) {
  const src = `${import.meta.env.BASE_URL}wildcards/${rarity}.webp`;
  return <img src={src} alt={`${rarity} wildcard`} style={{ height: size }} className="shrink-0 w-auto" />;
}
