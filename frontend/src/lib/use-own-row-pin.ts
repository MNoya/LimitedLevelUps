import { useEffect, useState } from "react";

export type PinMode = "hidden" | "inflow" | "overlay";

export function useOwnRowPin(stickyTop: number, scrollRoot: HTMLElement | null = null) {
  const [rowEl, setRowEl] = useState<HTMLElement | null>(null);
  const [pinMode, setPinMode] = useState<PinMode>("hidden");
  useEffect(() => {
    if (!rowEl) {
      setPinMode("hidden");
      return;
    }
    const evaluate = () => setPinMode(pinModeFor(rowEl, stickyTop, scrollRoot));
    const observer = new IntersectionObserver(evaluate, {
      root: scrollRoot,
      rootMargin: `${-stickyTop}px 0px 0px 0px`,
      threshold: 0,
    });
    observer.observe(rowEl);
    const raf = requestAnimationFrame(evaluate);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [rowEl, stickyTop, scrollRoot]);
  const scrollToRow = () => rowEl?.scrollIntoView({ behavior: "smooth", block: "center" });
  return { setRowEl, pinMode, scrollToRow };
}

function pinModeFor(rowEl: HTMLElement, stickyTop: number, scrollRoot: HTMLElement | null): PinMode {
  const row = rowEl.getBoundingClientRect();
  const view = scrollRoot ? scrollRoot.getBoundingClientRect() : { top: 0, bottom: window.innerHeight };
  const pinLine = view.top + stickyTop;
  if (row.bottom > pinLine && row.top < view.bottom) {
    return "hidden";
  }
  return row.top < pinLine ? "overlay" : "inflow";
}
