import { useEffect, useState } from "react";

import { cn } from "../../../lib/utils";
import { ChevronIcon } from "./reviewControls";

export const DECK_PANEL_MAX_FRACTION = 0.72;
const PANEL_DRAG_THRESHOLD = 4;
const PANEL_MIN_HEIGHT = 64;
const PANEL_COLLAPSE_AT = 40;

export function useResizableHeight(baseHeight: number, storageKey: string, onCollapse?: () => void) {
  const [dragHeight, setDragHeight] = useState<number | null>(() => storedPanelHeight(storageKey));
  const [dragging, setDragging] = useState(false);
  const height = dragHeight ?? baseHeight;
  useEffect(() => {
    if (dragging) {
      return;
    }
    if (dragHeight == null) {
      window.localStorage.removeItem(storageKey);
    } else {
      window.localStorage.setItem(storageKey, `${Math.round(dragHeight)}`);
    }
  }, [dragHeight, dragging, storageKey]);
  const beginResize = (startY: number, fromHeight?: number) => {
    const startHeight = fromHeight ?? dragHeight ?? baseHeight;
    let collapsible = fromHeight == null;
    if (fromHeight != null) {
      setDragHeight(fromHeight);
    }
    setDragging(true);
    const onMove = (ev: PointerEvent) => {
      const next = startHeight - (ev.clientY - startY);
      if (next >= PANEL_MIN_HEIGHT) {
        collapsible = true;
      }
      if (onCollapse && collapsible && next < PANEL_COLLAPSE_AT) {
        onCollapse();
        setDragHeight(null);
        cleanup();
        return;
      }
      const floor = collapsible ? PANEL_MIN_HEIGHT : 0;
      setDragHeight(Math.min(window.innerHeight * DECK_PANEL_MAX_FRACTION, Math.max(floor, next)));
    };
    const onUp = () => cleanup();
    function cleanup() {
      setDragging(false);
      setDragHeight((h) => (h != null && h < PANEL_MIN_HEIGHT ? PANEL_MIN_HEIGHT : h));
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };
  return { height, beginResize, dragging };
}

function storedPanelHeight(storageKey: string): number | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = Number(window.localStorage.getItem(storageKey));
  if (!stored) {
    return null;
  }
  return Math.min(stored, window.innerHeight * DECK_PANEL_MAX_FRACTION);
}

// Thick bar shared by the deck pool and the neighbor band: a tap toggles the panel collapsed, a press
// and drag past a small threshold resizes it instead. The chevron tab on the top edge shows which way
// a tap moves it. With nothing to show (no neighbor picks yet) it renders static, no toggle or resize.
export function PanelBar({
  open,
  canCollapse,
  onToggle,
  onResizeStart,
  className,
  children,
}: {
  open: boolean;
  canCollapse: boolean;
  onToggle: () => void;
  onResizeStart: (startY: number, fromHeight?: number) => void;
  className?: string;
  children: React.ReactNode;
}) {
  const handlePointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) {
      return;
    }
    e.preventDefault();
    const startY = e.clientY;
    let dragging = false;
    const onMove = (ev: PointerEvent) => {
      if (!dragging && Math.abs(ev.clientY - startY) > PANEL_DRAG_THRESHOLD) {
        dragging = true;
        if (open) {
          onResizeStart(startY);
        } else {
          onToggle();
          onResizeStart(startY, 0);
        }
      }
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (!dragging) {
        onToggle();
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };
  if (!canCollapse) {
    return (
      <div className={cn("relative hidden h-10 w-full shrink-0 items-center border-t border-border bg-bg lg:flex", className)}>
        {children}
      </div>
    );
  }
  return (
    <div
      onPointerDown={handlePointerDown}
      className={cn(
        "group relative hidden h-10 w-full shrink-0 cursor-row-resize select-none items-center border-t border-border bg-bg transition-colors hover:bg-surface2 lg:flex",
        className,
      )}
    >
      <span className="absolute bottom-full left-1/2 flex -translate-x-1/2 translate-y-px items-center justify-center rounded-t-md border border-b-0 border-border bg-bg px-3 text-subtle transition-colors group-hover:bg-surface2 group-hover:text-text">
        <ChevronIcon dir={open ? "down" : "up"} />
      </span>
      {children}
    </div>
  );
}
