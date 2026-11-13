import type { ReactNode } from "react";
import { cn } from "../lib/utils";
import type { PinMode } from "../lib/use-own-row-pin";

export function PinnedOwnRow({
  pinMode,
  stickyTop,
  onClick,
  className,
  children,
}: {
  pinMode: PinMode;
  stickyTop: number;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}) {
  const hidden = pinMode === "hidden";
  return (
    <div
      className={cn("sticky z-[5]", hidden && "pointer-events-none opacity-0")}
      style={{ top: stickyTop, height: pinMode === "inflow" ? undefined : 0 }}
      aria-hidden={hidden}
    >
      <div onClick={onClick} className={cn("cursor-pointer", className)}>
        {children}
      </div>
    </div>
  );
}
