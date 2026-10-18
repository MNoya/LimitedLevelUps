import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

const SETTLE_EASING = "cubic-bezier(0.22, 1, 0.36, 1)";

export function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useFlip(container: RefObject<HTMLElement>, skipKey: string | null = null, durationMs = 280) {
  const previous = useRef(new Map<string, DOMRect>());
  useLayoutEffect(() => {
    const root = container.current;
    if (!root) {
      return;
    }
    const animate = !prefersReducedMotion();
    const next = new Map<string, DOMRect>();
    root.querySelectorAll<HTMLElement>("[data-flip]").forEach((node) => {
      const key = node.dataset.flip!;
      const rect = node.getBoundingClientRect();
      next.set(key, rect);
      const before = previous.current.get(key);
      if (!animate || !before || key === skipKey) {
        return;
      }
      const dx = before.left - rect.left;
      const dy = before.top - rect.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) {
        return;
      }
      const from = { transform: `translate(${dx}px, ${dy}px)` };
      node.animate([from, { transform: "translate(0, 0)" }], { duration: durationMs, easing: SETTLE_EASING });
    });
    previous.current = next;
  });
}

export function useCountUp(target: number, animate: boolean, delayMs: number, durationMs = 650): number {
  const [value, setValue] = useState(animate ? 0 : target);
  useEffect(() => {
    if (!animate || prefersReducedMotion()) {
      setValue(target);
      return;
    }
    let frame = 0;
    const start = performance.now() + delayMs;
    const tick = (now: number) => {
      const progress = Math.min(1, Math.max(0, (now - start) / durationMs));
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, animate, delayMs, durationMs]);
  return value;
}

export const REVEAL_START_MS = 300;
export const REVEAL_STEP_MS = 120;
const WHEEL_BEAT_MS = 200;

export function pickRevealDelay(pickIndex: number, animate: boolean): number {
  return animate ? REVEAL_START_MS + pickIndex * REVEAL_STEP_MS : 0;
}

export function wheelRevealDelay(slotCount: number, animate: boolean): number {
  return animate ? REVEAL_START_MS + slotCount * REVEAL_STEP_MS + WHEEL_BEAT_MS : 0;
}
