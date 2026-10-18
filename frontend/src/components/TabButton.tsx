import type React from "react";
import { Link, type To } from "react-router-dom";
import { cn } from "../lib/utils";

type TabSize = "default" | "section";

export function TabButton({
  active,
  onClick,
  children,
  size = "default",
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  size?: TabSize;
}) {
  return (
    <button type="button" onClick={onClick} className={tabClassName(active, size)} style={tabStyle(active)}>
      {children}
    </button>
  );
}

export function TabLink({ active, to, children }: { active: boolean; to: To; children: React.ReactNode }) {
  return (
    <Link to={to} className={cn(tabClassName(active), "no-underline", !active && "hover:text-subtle")} style={tabStyle(active)}>
      {children}
    </Link>
  );
}

function tabClassName(active: boolean, size: TabSize = "default"): string {
  return cn(
    "flex-1 px-1.5 bg-transparent cursor-pointer font-display leading-none transition-colors border-b-2 border-solid inline-flex items-center justify-center gap-1.5",
    size === "section" ? "h-[50px] text-[17px] tracking-[0.18em]" : "py-2 text-[14px] tracking-[0.16em]",
    active ? "text-text border-green" : "text-muted border-transparent",
  );
}

function tabStyle(active: boolean): React.CSSProperties | undefined {
  return active ? { marginBottom: -1 } : undefined;
}
