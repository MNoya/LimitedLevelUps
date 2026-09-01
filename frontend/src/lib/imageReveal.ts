import { useEffect, useLayoutEffect, useState } from "react";

const loadedImages = new Set<string>();

export function isImageLoaded(url: string): boolean {
  return loadedImages.has(url);
}

export function markImageLoaded(url: string): void {
  loadedImages.add(url);
}

export function preloadImage(url: string, onReady?: () => void) {
  if (loadedImages.has(url)) {
    onReady?.();
    return;
  }
  const warm = new Image();
  const done = () => {
    loadedImages.add(url);
    onReady?.();
  };
  warm.onload = done;
  warm.onerror = done;
  warm.src = url;
  if (warm.complete && warm.naturalWidth > 0) {
    done();
  }
}

export function usePreloaded(src: string): boolean {
  const [ready, setReady] = useState(() => loadedImages.has(src));

  useEffect(() => {
    if (loadedImages.has(src)) {
      setReady(true);
      return;
    }
    setReady(false);
    let active = true;
    preloadImage(src, () => {
      if (active) setReady(true);
    });
    return () => {
      active = false;
    };
  }, [src]);

  return ready;
}

export function useImageReveal(src: string) {
  const [loaded, setLoaded] = useState(false);
  const [instant, setInstant] = useState(false);

  useLayoutEffect(() => {
    const cached = loadedImages.has(src);
    setLoaded(cached);
    setInstant(cached);
  }, [src]);

  const onLoad = () => {
    loadedImages.add(src);
    setLoaded(true);
  };

  return { loaded, instant, onLoad };
}
