import React from "react";
import { Root, Trigger, Portal, Content } from "@radix-ui/react-tooltip";
import { cn } from "../lib/utils";

type Side = "top" | "right" | "bottom" | "left";

const ARROW_CLASS = cn(
  "absolute h-2.5 w-2.5 rotate-45 bg-black border-border2",
  "group-data-[side=top]:bottom-0 group-data-[side=top]:left-1/2 group-data-[side=top]:-translate-x-1/2",
  "group-data-[side=top]:translate-y-1/2 group-data-[side=top]:border-b group-data-[side=top]:border-r",
  "group-data-[side=bottom]:top-0 group-data-[side=bottom]:left-1/2 group-data-[side=bottom]:-translate-x-1/2",
  "group-data-[side=bottom]:-translate-y-1/2 group-data-[side=bottom]:border-t group-data-[side=bottom]:border-l",
  "group-data-[side=left]:right-0 group-data-[side=left]:top-1/2 group-data-[side=left]:-translate-y-1/2",
  "group-data-[side=left]:translate-x-1/2 group-data-[side=left]:border-r group-data-[side=left]:border-t",
  "group-data-[side=right]:left-0 group-data-[side=right]:top-1/2 group-data-[side=right]:-translate-y-1/2",
  "group-data-[side=right]:-translate-x-1/2 group-data-[side=right]:border-l group-data-[side=right]:border-b",
);

// Never pair a tooltip with the help (?) cursor: a clickable trigger keeps cursor-pointer, anything else the default cursor
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
            "group relative z-50 rounded-md px-2.5 py-1.5",
            interactive ? "pointer-events-auto select-text" : "pointer-events-none select-none",
            "border border-border2 bg-black text-text text-[12px] leading-tight",
            "shadow-lg shadow-black/60",
            className,
          )}
        >
          {label}
          {!hideArrow && (
            <span className={ARROW_CLASS} />
          )}
        </Content>
      </Portal>
    </Root>
  );
}
