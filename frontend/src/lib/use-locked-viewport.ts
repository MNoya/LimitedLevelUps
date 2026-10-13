import { useLayoutEffect } from "react";

export function useLockedViewport(enabled = true) {
  useLayoutEffect(() => {
    if (!enabled) {
      return;
    }
    const html = document.documentElement;
    const previous = html.style.scrollbarGutter;
    const gutterWidth = window.innerWidth - html.getBoundingClientRect().width;
    html.style.setProperty("--app-scrollbar", `${gutterWidth}px`);
    html.style.scrollbarGutter = "auto";
    return () => {
      html.style.scrollbarGutter = previous;
      html.style.removeProperty("--app-scrollbar");
    };
  }, [enabled]);
}
