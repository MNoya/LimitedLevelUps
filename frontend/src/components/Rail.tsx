import type { MouseEvent as ReactMouseEvent, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { IconType } from "react-icons";
import { Tooltip } from "./Tooltip";
import { cn } from "../lib/utils";

type RailHeaderProps = { icon: LucideIcon | IconType; label: string; iconSize?: number };

export function RailHeader({ icon: Icon, label, iconSize = 22 }: RailHeaderProps) {
  return (
    <div className="flex h-[60px] items-center gap-2.5 border-b border-border px-4">
      <Icon size={iconSize} className="shrink-0 text-green" />
      <span className="font-display text-[25px] leading-none tracking-[0.12em] text-text">{label}</span>
    </div>
  );
}

type RailRowProps = {
  label: string;
  icon: LucideIcon;
  active: boolean;
  count?: number;
  collapsed?: boolean;
  href?: string;
  onClick?: (e: ReactMouseEvent) => void;
};

export function RailRow({ label, icon: Icon, active, count, collapsed = false, href, onClick }: RailRowProps) {
  const className = cn(
    "group relative flex w-full items-center text-left no-underline transition-colors",
    collapsed ? "justify-center py-3.5" : "gap-3 px-4 py-3.5",
    active ? "bg-surface2" : "hover:bg-bg/40",
  );
  const body = (
    <>
      <span
        className={cn(
          "absolute left-0 top-0 h-full w-[3px] origin-center bg-green transition-all duration-200",
          active ? "opacity-100" : "opacity-0 scale-y-50 group-hover:opacity-100 group-hover:scale-y-100",
        )}
      />
      <Icon
        size={18}
        strokeWidth={2}
        className={cn("shrink-0 transition-colors", active ? "text-green" : "text-muted group-hover:text-green")}
      />
      {collapsed ? null : (
        <>
          <span
            className={cn(
              "flex-1 font-display uppercase tracking-[0.08em] text-[16px] transition-colors",
              active ? "text-green" : "text-text group-hover:text-green",
            )}
          >
            {label}
          </span>
          {count === undefined ? null : (
            <span
              className={cn(
                "mono text-[13px] tabular-nums transition-colors",
                active ? "text-green" : "text-muted group-hover:text-green",
              )}
            >
              {count || "–"}
            </span>
          )}
        </>
      )}
    </>
  );
  const row: ReactNode = href ? (
    <a href={href} onClick={onClick} aria-label={collapsed ? label : undefined} className={className}>
      {body}
    </a>
  ) : (
    <button type="button" onClick={onClick} aria-label={collapsed ? label : undefined} className={className}>
      {body}
    </button>
  );

  if (collapsed) {
    const tip = count === undefined ? label : `${label} (${count || "–"})`;
    return (
      <Tooltip label={tip} side="right">
        {row}
      </Tooltip>
    );
  }
  return row;
}
