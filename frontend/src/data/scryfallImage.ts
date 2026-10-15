export type ScryfallWebpVersion = "thumb" | "grid" | "display" | "art" | "crop";

export const scryfallWebp = (url: string, version: ScryfallWebpVersion): string => {
  const match = url.match(/^(https:\/\/cards\.scryfall\.io\/)[a-z_]+(\/[^?]+)\.(?:jpg|png|webp)(\?.*)?$/);
  if (!match) {
    return url;
  }
  const [, host, path, query = ""] = match;
  return `${host}${version}${path}.webp${query}`;
};
