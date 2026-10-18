export const cachedImageUrl = (url: string): string =>
  import.meta.env.DEV && url.startsWith("https://") ? `/__image?u=${encodeURIComponent(url)}` : url;
