import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "../lib/utils";
import { useWheelTrap } from "../lib/use-wheel-trap";
import { ChevronDown } from "./Icons";

// Custom click-to-open dropdown — same family as SetSwitcherMobile so styled
// content (color swatches, mana pips, etc) renders cleanly in both the closed
// trigger and the open option list. Replaces the previous native <select>
// which couldn't host React content in its menu.
//
// Both `renderValue` and `renderOption` are optional and default to the option's
// plain label.

export interface FilterOption {
  value: string;
  label: string;
  // Options sharing a section render under a divider + header when the section changes. Options with
  // no section render flush; give a trailing group (e.g. MTGO flashbacks) a section to set it apart.
  section?: string;
}

const SEARCH_THRESHOLD = 8;

export function FilterDropdown({
  label,
  value,
  options,
  onChange,
  variant = "desktop",
  align = "left",
  renderValue,
  renderOption,
  renderTrigger,
  searchable,
  searchPlaceholder = "Search…",
  triggerClassName,
  className,
  mobileCentered = false,
}: {
  label?: string;
  value: string;
  options: FilterOption[];
  onChange: (next: string) => void;
  variant?: "desktop" | "mobile";
  align?: "left" | "right";
  renderValue?: (option: FilterOption) => React.ReactNode;
  renderOption?: (option: FilterOption) => React.ReactNode;
  renderTrigger?: (state: { open: boolean; selected: FilterOption; toggle: () => void }) => React.ReactNode;
  searchable?: boolean;
  searchPlaceholder?: string;
  triggerClassName?: string;
  className?: string;
  mobileCentered?: boolean;
}) {
  const isMobile = variant === "mobile";
  const selected = options.find((o) => o.value === value) ?? options[0];
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [menuTop, setMenuTop] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useWheelTrap<HTMLDivElement>(open);

  const showSearch = searchable ?? options.length > SEARCH_THRESHOLD;
  const toggle = () => setOpen((o) => !o);

  useLayoutEffect(() => {
    if (!open || !mobileCentered) {
      return;
    }
    const rect = (triggerRef.current ?? ref.current)?.getBoundingClientRect();
    if (rect) {
      setMenuTop(rect.bottom + 4);
    }
  }, [open, mobileCentered]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    const onClickOutside = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const trimmed = query.trim().toLowerCase();
  const filtered = trimmed
    ? options.filter(
        (o) => o.label.toLowerCase().includes(trimmed) || o.value.toLowerCase().includes(trimmed),
      )
    : options;

  return (
    <div ref={ref} className={cn("relative", isMobile ? "flex-1 min-w-0" : "", className)}>
      {renderTrigger ? (
        renderTrigger({ open, selected, toggle })
      ) : (
        <button
          ref={triggerRef}
          type="button"
          onClick={toggle}
          className={cn(
            "flex items-center gap-2 w-full bg-transparent border border-border2 font-display text-text cursor-pointer transition-colors hover:bg-surface",
            isMobile
              ? "h-full px-2.5 py-1.5 text-[15px] tracking-[0.1em]"
              : "px-3.5 py-1.5 min-w-[220px] text-[15px] tracking-[0.12em]",
            open && "bg-surface",
            triggerClassName,
          )}
        >
          {label ? (
            <span className={cn("text-muted tracking-[0.22em]", isMobile ? "text-[11px]" : "text-[12px]")}>
              {label}
            </span>
          ) : null}
          <span className="flex flex-1 items-center gap-1.5 min-w-0 truncate">
            {renderValue ? renderValue(selected) : selected.label}
          </span>
          <ChevronDown
            size={isMobile ? 18 : 16}
            strokeWidth={2.5}
            className={cn("text-muted transition-transform", open && "rotate-180")}
          />
        </button>
      )}

      {open && (
        <div
          ref={menuRef}
          className={cn(
            "absolute top-[calc(100%+4px)] min-w-full w-max max-w-[calc(100vw-24px)] flex max-h-[min(60vh,420px)] flex-col bg-surface border border-border2 z-20 shadow-lg",
            align === "right" ? "right-0" : "left-0",
            mobileCentered &&
              "max-sm:!fixed max-sm:!left-1/2 max-sm:!right-auto max-sm:!-translate-x-1/2 max-sm:!top-[var(--menu-top)]",
          )}
          style={mobileCentered ? ({ "--menu-top": `${menuTop}px` } as React.CSSProperties) : undefined}
          role="listbox"
        >
          {showSearch && (
            <div className="shrink-0 border-b border-border p-1.5">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && filtered.length > 0) {
                    e.preventDefault();
                    onChange(filtered[0].value);
                    setOpen(false);
                  }
                }}
                placeholder={searchPlaceholder}
                className="w-full bg-bg border border-border px-2.5 py-1.5 font-body text-[14px] tracking-normal text-text placeholder:text-dim outline-none focus:border-green"
              />
            </div>
          )}
          <div className="menu-scrollbar min-h-0 flex-1 overflow-y-auto">
            {filtered.map((o, i) => {
              const isSelected = o.value === value;
              const showSectionHeader = o.section && o.section !== filtered[i - 1]?.section;
              return (
                <React.Fragment key={o.value}>
                  {showSectionHeader && (
                    <div className="border-t border-border2 px-3.5 pt-2.5 pb-1 font-display text-[11px] tracking-[0.2em] text-muted select-none">
                      {o.section}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      onChange(o.value);
                      setOpen(false);
                    }}
                    role="option"
                    aria-selected={isSelected}
                    className={cn(
                      "w-full text-left flex items-center gap-2 border-l-2 font-display cursor-pointer transition-colors whitespace-nowrap",
                      isMobile
                        ? "px-2.5 py-2.5 text-[15px] tracking-[0.08em]"
                        : "px-3.5 py-2.5 text-[15px] tracking-[0.06em]",
                      i > 0 && !showSectionHeader && "border-t border-border",
                      isSelected
                        ? "border-l-green bg-surface2 text-green"
                        : "border-l-transparent bg-transparent text-text hover:bg-surface2",
                    )}
                  >
                    {renderOption ? renderOption(o) : o.label}
                  </button>
                </React.Fragment>
              );
            })}
            {filtered.length === 0 && (
              <div className="px-3.5 py-3 font-body text-[14px] text-muted">No matches</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
