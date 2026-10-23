import React from "react";
import { Root, Trigger, Portal, Content } from "@radix-ui/react-tooltip";
import { cn } from "../lib/utils";

type Side = "top" | "right" | "bottom" | "left";

const ARROW_BY_SIDE: Record<Side, string> = {
  top: "bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 border-b border-r",
  bottom: "top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 border-t border-l",
  left: "right-0 top-1/2 -translate-y-1/2 translate-x-1/2 border-r border-t",
  right: "left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 border-l border-b",
};

export function Tooltip({
  label,
  side,
  align,
  children,
  className,
  open,
  onOpenChange,
  delayDuration,
  hideArrow,
  collisionPadding,
  interactive = false,
}: {
  label: React.ReactNode;
  side?: Side;
  align?: "start" | "center" | "end";
  children: React.ReactNode;
  className?: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  delayDuration?: number;
  hideArrow?: boolean;
  collisionPadding?: number | Partial<Record<Side, number>>;
  interactive?: boolean;
}) {
  return (
    <Root
      open={open}
      onOpenChange={onOpenChange}
      delayDuration={delayDuration}
      disableHoverableContent={interactive ? false : undefined}
    >
      <Trigger asChild>{children}</Trigger>
      <Portal>
        <Content
          side={side}
          align={align}
          sideOffset={7}
          collisionPadding={collisionPadding ?? 8}
          className={cn(
            "relative z-50 rounded-md px-2.5 py-1.5",
            interactive ? "pointer-events-auto select-text" : "pointer-events-none select-none",
            "border border-border2 bg-black text-text text-[12px] leading-tight",
            "shadow-lg shadow-black/60",
            className,
          )}
        >
          {label}
          {!hideArrow && (
            <span
              className={cn("absolute h-2.5 w-2.5 rotate-45 bg-black border-border2", ARROW_BY_SIDE[side ?? "top"])}
            />
          )}
        </Content>
      </Portal>
    </Root>
  );
}
