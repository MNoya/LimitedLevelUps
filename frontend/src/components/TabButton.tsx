import type React from "react";
import { Link, type To } from "react-router-dom";
import { cn } from "../lib/utils";

export function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button type="button" onClick={onClick} className={tabClassName(active)} style={tabStyle(active)}>
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

function tabClassName(active: boolean): string {
  return cn(
    "flex-1 py-2 px-1.5 bg-transparent cursor-pointer font-display text-[14px] tracking-[0.16em] leading-none transition-colors border-b-2 border-solid inline-flex items-center justify-center gap-1.5",
    active ? "text-text border-green" : "text-muted border-transparent",
  );
}

function tabStyle(active: boolean): React.CSSProperties | undefined {
  return active ? { marginBottom: -1 } : undefined;
}
