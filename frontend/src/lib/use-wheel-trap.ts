import { useEffect, useRef } from "react";

const LINE_HEIGHT = 16;

/** Ref for a floating panel: while active, a wheel over its chrome scrolls the panel's own list instead of the page */
export function useWheelTrap<T extends HTMLElement>(active: boolean) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const shell = ref.current;
    if (!active || !shell) {
      return;
    }
    const onWheel = (e: WheelEvent) => {
      if (scrollsWithin(e.target, shell)) {
        return;
      }
      e.preventDefault();
      const list = findScrollable(shell);
      if (list) {
        list.scrollTop += wheelPixels(e, list);
      }
    };
    shell.addEventListener("wheel", onWheel, { passive: false });
    return () => shell.removeEventListener("wheel", onWheel);
  }, [active]);

  return ref;
}

function canScrollY(node: Element): boolean {
  const overflowY = getComputedStyle(node).overflowY;
  return (overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight;
}

function scrollsWithin(target: EventTarget | null, shell: HTMLElement): boolean {
  let node = target instanceof Element ? target : null;
  while (node && node !== shell) {
    if (canScrollY(node)) {
      return true;
    }
    node = node.parentElement;
  }
  return false;
}

function findScrollable(shell: HTMLElement): HTMLElement | null {
  for (const node of shell.querySelectorAll<HTMLElement>("*")) {
    if (canScrollY(node)) {
      return node;
    }
  }
  return null;
}

function wheelPixels(e: WheelEvent, list: HTMLElement): number {
  if (e.deltaMode === WheelEvent.DOM_DELTA_LINE) {
    return e.deltaY * LINE_HEIGHT;
  }
  if (e.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    return e.deltaY * list.clientHeight;
  }
  return e.deltaY;
}
