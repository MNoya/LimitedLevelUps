import { useLayoutEffect, useRef } from "react";
import { cn } from "../lib/utils";

export function FitText({
  text,
  max = 15,
  min = 9,
  className,
}: {
  text: string;
  max?: number;
  min?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      el.style.fontSize = `${max}px`;
      if (el.clientWidth > 0 && el.scrollWidth > el.clientWidth) {
        const scaled = (max * el.clientWidth) / el.scrollWidth;
        el.style.fontSize = `${Math.max(min, Math.floor(scaled * 10) / 10)}px`;
      }
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    let cancelled = false;
    document.fonts?.ready.then(() => {
      if (!cancelled) fit();
    });
    return () => {
      cancelled = true;
      observer.disconnect();
    };
  }, [text, max, min]);
  return (
    <span ref={ref} className={cn("block min-w-0 flex-1 overflow-hidden whitespace-nowrap leading-none", className)}>
      {text}
    </span>
  );
}
