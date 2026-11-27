import { useEffect, useRef, useState } from "react";
import {
  AutoScrollActivator,
  MouseSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
} from "@dnd-kit/core";

import { cn } from "../../lib/utils";
import type { PoolCard, PoolEntry } from "../../data/dailySealed";
import type { BasicsSlot, PileTarget } from "../../data/dailySealedLayout";
import { CardStack, NO_CARD_ACTIONS, REVEAL_RATIO } from "./cards";
import { PILE_GAP } from "./piles";
import { pileTargetAt, sameTarget } from "./pileHitTest";
import type { Builder } from "./useBuilder";

const DRAG_DISTANCE = 6;
const TOUCH_HOLD_MS = 200;
const TOUCH_TOLERANCE = 8;

export interface Ghost {
  indexes: number[];
  column: boolean;
  landsPile: BasicsSlot | null;
  belowHeader: boolean;
}

export const usePileDrag = (builder: Builder, fittedWidth: number, touch = false) => {
  const [dragging, setDragging] = useState<number[] | null>(null);
  const [ghost, setGhost] = useState<Ghost | null>(null);
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const [overZone, setOverZone] = useState<PileTarget["zone"] | null>(null);
  const grab = useRef({ x: 0, y: 0 });
  const cardWidth = dragWidth ?? fittedWidth;
  const pointerSensor = useSensor(PointerSensor, { activationConstraint: { distance: DRAG_DISTANCE } });
  const mouseSensor = useSensor(MouseSensor, { activationConstraint: { distance: DRAG_DISTANCE } });
  const touchSensor = useSensor(TouchSensor, {
    activationConstraint: { delay: TOUCH_HOLD_MS, tolerance: TOUCH_TOLERANCE },
  });
  const sensors = useSensors(...(touch ? [mouseSensor, touchSensor] : [pointerSensor]));
  const latest = useRef({ builder, dragging, ghost, width: cardWidth });
  latest.current = { builder, dragging, ghost, width: cardWidth };
  const lastTarget = useRef<PileTarget | null>(null);
  const lastPoint = useRef<{ x: number; y: number } | null>(null);

  const placeAtPointer = () => {
    const { builder: current, dragging: indexes, ghost: drag, width } = latest.current;
    const point = lastPoint.current;
    if (!indexes || !point) {
      return;
    }
    if (drag?.column) {
      const target = pileTargetAt(point.x, point.y, current.layout, [], PILE_GAP, width);
      if (
        target?.zone !== "deck" ||
        (lastTarget.current?.row === target.row && lastTarget.current?.pile === target.pile)
      ) {
        return;
      }
      lastTarget.current = target;
      const slot = { row: target.row, pile: target.pile };
      if (drag.landsPile) {
        current.dragLandsPileTo(drag.landsPile, slot);
      } else {
        current.dragBasicsTo(slot);
      }
      return;
    }
    const underPointer = pileTargetAt(point.x, point.y, current.layout, indexes, PILE_GAP, width);
    const cardX = point.x - grab.current.x + width / 2;
    const titleY = point.y - grab.current.y + (width * REVEAL_RATIO) / 2;
    const target =
      underPointer?.zone === "hidden"
        ? underPointer
        : pileTargetAt(cardX, titleY, current.layout, indexes, PILE_GAP, width);
    setOverZone(target?.zone ?? null);
    if (sameTarget(target, lastTarget.current)) {
      return;
    }
    lastTarget.current = target;
    current.dragTo(indexes, target);
  };
  usePointerFrames(dragging !== null, lastPoint, placeAtPointer);

  const onDragStart = (event: DragStartEvent) => {
    const data = event.active.data.current;
    const picked = (data?.indexes as number[] | undefined) ?? [];
    const landsPile = (data?.landsPile as BasicsSlot | null | undefined) ?? null;
    const column = !!data?.basics || landsPile !== null;
    const indexes = column ? [] : picked;
    const nextGhost = { indexes: picked, column, landsPile, belowHeader: !!data?.pileHeader };
    setGhost(nextGhost);
    builder.beginDrag(!column);
    lastTarget.current = null;
    lastPoint.current = null;
    setDragWidth(cardWidth);
    grab.current = grabPointOf(event);
    setDragging(indexes);
    latest.current = { builder, dragging: indexes, ghost: nextGhost, width: cardWidth };
  };
  const finishDrag = () => {
    setDragging(null);
    setGhost(null);
    setDragWidth(null);
    setOverZone(null);
    lastTarget.current = null;
    lastPoint.current = null;
  };

  return {
    dragging,
    ghost,
    overZone,
    cardWidth,
    contextProps: {
      sensors,
      autoScroll: {
        activator: AutoScrollActivator.Pointer,
        threshold: { x: 0.04, y: 0.08 },
        acceleration: 6,
        canScroll: (element: Element) => pointerInside(element, lastPoint.current),
      },
      onDragStart,
      onDragEnd: () => {
        placeAtPointer();
        builder.endDrag();
        finishDrag();
      },
      onDragCancel: () => {
        builder.cancelDrag();
        finishDrag();
      },
    },
  };
};

export const PileDragGhost = ({
  ghost,
  cards,
  basicCards = [],
  cardWidth,
}: {
  ghost: Ghost;
  cards: PoolCard[];
  basicCards?: PoolEntry[];
  cardWidth: number;
}) => {
  const entries: PoolEntry[] = [
    ...ghost.indexes.map((index) => ({ index, card: cards[index] })),
    ...(ghost.column ? basicCards : []),
  ];
  return (
    <div className={cn("opacity-90", ghost.belowHeader && "pt-7")}>
      <CardStack entries={entries} width={cardWidth} actions={NO_CARD_ACTIONS} />
    </div>
  );
};

const usePointerFrames = (
  active: boolean,
  point: { current: { x: number; y: number } | null },
  onFrame: () => void,
) => {
  const frameHandler = useRef(onFrame);
  frameHandler.current = onFrame;
  useEffect(() => {
    if (!active) {
      return;
    }
    let frame = 0;
    const run = () => {
      frame = 0;
      frameHandler.current();
    };
    const schedule = () => {
      if (frame === 0) {
        frame = requestAnimationFrame(run);
      }
    };
    const onMove = (event: PointerEvent) => {
      point.current = { x: event.clientX, y: event.clientY };
      schedule();
    };
    const onTouchMove = (event: TouchEvent) => {
      const finger = event.touches[0];
      if (finger) {
        point.current = { x: finger.clientX, y: finger.clientY };
        schedule();
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("touchmove", onTouchMove);
    window.addEventListener("scroll", schedule, true);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("scroll", schedule, true);
      cancelAnimationFrame(frame);
    };
  }, [active, point]);
};

const grabPointOf = (event: DragStartEvent) => {
  const start = event.activatorEvent;
  const point = startPoint(start);
  if (!point || !(start.target instanceof Element)) {
    return { x: 0, y: 0 };
  }
  const grabbed = start.target.closest('[aria-roledescription="draggable"]');
  const rect = grabbed?.getBoundingClientRect();
  return rect ? { x: point.x - rect.left, y: point.y - rect.top } : { x: 0, y: 0 };
};

const startPoint = (start: Event) => {
  if (start instanceof MouseEvent) {
    return { x: start.clientX, y: start.clientY };
  }
  const finger = typeof TouchEvent !== "undefined" && start instanceof TouchEvent ? start.touches[0] : undefined;
  return finger ? { x: finger.clientX, y: finger.clientY } : null;
};

const pointerInside = (element: Element, point: { x: number; y: number } | null) => {
  if (!point) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return point.x >= rect.left && point.x <= rect.right && point.y >= rect.top && point.y <= rect.bottom;
};
