export const loadFantasyPage = () => import("../../pages/FantasyPage");

export const loadFantasyReplayPage = () => import("../../pages/FantasyReplayPage");

export function prefetchProPlay(): void {
  void loadFantasyPage();
  void loadFantasyReplayPage();
}

export function prefetchProPlayWhenIdle(): () => void {
  if (typeof window.requestIdleCallback === "function") {
    const handle = window.requestIdleCallback(prefetchProPlay, { timeout: 5000 });
    return () => window.cancelIdleCallback(handle);
  }
  const timer = window.setTimeout(prefetchProPlay, 2000);
  return () => window.clearTimeout(timer);
}
