import { forwardRef, useImperativeHandle, useRef, useState, type MouseEvent, type Ref } from "react";
import { createPortal } from "react-dom";

import { cn } from "../lib/utils";

interface CursorTooltipHandle {
  show: (label: string, e: MouseEvent) => void;
  hide: () => void;
}

export interface CursorTooltipBinding {
  onMouseEnter: (e: MouseEvent) => void;
  onMouseMove: (e: MouseEvent) => void;
  onMouseLeave: () => void;
  onMouseDown: () => void;
}

export function useCursorTooltip() {
  const handle = useRef<CursorTooltipHandle>(null);
  const bind = (label: string): CursorTooltipBinding => ({
    onMouseEnter: (e) => handle.current?.show(label, e),
    onMouseMove: (e) => handle.current?.show(label, e),
    onMouseLeave: () => handle.current?.hide(),
    onMouseDown: () => handle.current?.hide(),
  });
  return { bind, layer: <CursorTooltipLayer ref={handle} /> };
}

const CursorTooltipLayer = forwardRef((_props: object, ref: Ref<CursorTooltipHandle>) => {
  const [label, setLabel] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useImperativeHandle(ref, () => ({
    show: (next, e) => {
      setLabel(next);
      if (box.current) {
        box.current.style.transform = `translate(${e.clientX + 14}px, ${e.clientY + 18}px)`;
      }
    },
    hide: () => setLabel(null),
  }));
  return createPortal(
    <div
      ref={box}
      className={cn(
        "fixed left-0 top-0 z-50 pointer-events-none select-none rounded-md px-2.5 py-1.5 whitespace-nowrap",
        "border border-border2 bg-black text-text text-[12px] leading-tight shadow-lg shadow-black/60",
        label ? "opacity-100" : "opacity-0",
      )}
    >
      {label}
    </div>,
    document.body,
  );
});
