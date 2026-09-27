import { useEffect } from "react";

export function useStickyScrollPadding(stickyHeight: number): void {
  useEffect(() => {
    const root = document.documentElement;
    root.style.scrollPaddingTop = stickyHeight ? `${stickyHeight + 12}px` : "";
    return () => {
      root.style.scrollPaddingTop = "";
    };
  }, [stickyHeight]);
}
