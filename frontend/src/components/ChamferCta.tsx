import type { ReactNode } from "react";
import { ArrowRight } from "./Icons";
import { cn } from "../lib/utils";

// Green cut-corner CTA with a trailing arrow and optional left icon. Renders an
// <a> when href is given, otherwise a <span> so it can sit inside a parent link
export const CUT_CORNER_CHAMFER = "polygon(9px 0, 100% 0, 100% calc(100% - 9px), calc(100% - 9px) 100%, 0 100%, 0 9px)";

type ChamferSize = "sm" | "lg";

const SIZE_CLASSES: Record<ChamferSize, string> = {
  sm: "gap-2.5 text-[12.5px] tracking-[0.1em] px-4 py-2",
  lg: "gap-3 text-[15px] md:text-[17px] tracking-[0.12em] px-6 py-3.5",
};

const ARROW_SIZE: Record<ChamferSize, number> = { sm: 13, lg: 16 };

const BASE = "inline-flex items-center bg-green text-bg font-mono font-bold no-underline hover:bg-green-2 transition-colors";

const GROW = "transition-[transform,background-color] duration-200 hover:scale-105";

export function ChamferCta({
  label,
  icon,
  href,
  target,
  size = "sm",
  grow = false,
  className,
}: {
  label: string;
  icon?: ReactNode;
  href?: string;
  target?: string;
  size?: ChamferSize;
  grow?: boolean;
  className?: string;
}) {
  const inner = (
    <>
      {icon}
      {label}
      <ArrowRight size={ARROW_SIZE[size]} />
    </>
  );
  const props = {
    className: cn(BASE, SIZE_CLASSES[size], grow && GROW, className),
    style: { clipPath: CUT_CORNER_CHAMFER },
  };

  if (href) {
    return (
      <a href={href} target={target} rel={target === "_blank" ? "noreferrer" : undefined} {...props}>
        {inner}
      </a>
    );
  }
  return <span {...props}>{inner}</span>;
}
