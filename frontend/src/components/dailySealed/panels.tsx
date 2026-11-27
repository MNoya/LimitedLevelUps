import type { ReactNode } from "react";

import { PanelBar, useResizableHeight } from "../pod/review/resizablePanel";
import { usePersistentBool } from "../../lib/use-persistent-bool";
import { SCROLL_LIST_STYLE } from "../../lib/scroll-list";
import { cn } from "../../lib/utils";
import type { PileZone, SortKey } from "../../data/dailySealedLayout";
import { DROP_ZONE_ATTR } from "./pileHitTest";
import { chipClass } from "../pod/review/reviewControls";

const DECK_DEFAULT_FRACTION = 0.38;

export const SIDEBAR_WIDTH_CLASS = "w-[255px] shrink-0";

export const SORT_LABELS: Record<SortKey, string> = { mana: "Mana Value", color: "Color", rarity: "Rarity" };

export const Panel = ({ title, grow = false, children }: { title: string; grow?: boolean; children: ReactNode }) => (
  <section className={cn("border-b border-border px-3 pb-3 pt-2 last:border-b-0", grow && "flex flex-1 flex-col")}>
    <h2 className="mb-2.5 text-center font-display text-[15px] tracking-[0.18em] text-text">{title}</h2>
    {children}
  </section>
);

export const SortControls = ({ onSort }: { onSort: (key: SortKey) => void }) => (
  <div className="ml-4 flex items-center gap-2">
    <span className="font-display text-[13px] tracking-[0.18em] text-subtle">SORT BY</span>
    <div className="flex gap-1">
      {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
        <button
          key={key}
          type="button"
          onClick={() => onSort(key)}
          className={cn(
            "h-8 px-2.5 text-[12px] uppercase tracking-[0.12em]",
            chipClass(false),
            "transition-[color,background-color,border-color,transform] duration-100",
            "hover:border-green/60 hover:bg-green/15 hover:text-green active:scale-95 active:bg-green/30",
          )}
        >
          {SORT_LABELS[key]}
        </button>
      ))}
    </div>
  </div>
);

export const Pane = ({
  zone,
  className,
  title,
  count,
  total,
  controls,
  extra,
  children,
  flush = false,
}: {
  zone: PileZone;
  className?: string;
  title: ReactNode;
  count: number | null;
  total?: number;
  controls?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  flush?: boolean;
}) => (
  <section
    {...{ [DROP_ZONE_ATTR]: zone }}
    className={cn("flex min-h-0 flex-col border-b border-border last:border-b-0", className)}
  >
    <div className="flex h-10 shrink-0 items-center gap-4 border-b border-border bg-surface px-3">
      <div className="flex items-baseline gap-2">
        {title}
        {count !== null && total !== undefined && total !== count && (
          <span className="font-num text-[14px] text-subtle line-through">{total}</span>
        )}
        {count !== null && (
          <span
            className={cn("font-num text-[14px]", total !== undefined && total !== count ? "text-text" : "text-subtle")}
          >
            {count}
          </span>
        )}
      </div>
      {controls}
      <div className="ml-auto">{extra}</div>
    </div>
    {flush ? (
      <div className="flex min-h-0 flex-1">{children}</div>
    ) : (
      <div className={cn("min-h-0 flex-1 overflow-auto px-2 py-1.5", THIN_SCROLLBAR)} style={SCROLL_LIST_STYLE}>
        {children}
      </div>
    )}
  </section>
);

const THIN_SCROLLBAR =
  "[&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent " +
  "[&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border2 [&::-webkit-scrollbar-corner]:bg-transparent";

export const DeckPanel = ({
  title,
  storageKey,
  count,
  controls,
  extra,
  children,
}: {
  title: ReactNode;
  storageKey: string;
  count: number | string | null;
  controls: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
}) => {
  const [open, setOpen] = usePersistentBool(`${storageKey}-open`, true);
  const defaultHeight = Math.round(window.innerHeight * DECK_DEFAULT_FRACTION);
  const { height, beginResize } = useResizableHeight(defaultHeight, `${storageKey}-height`, () => setOpen(false));
  const keepPress = (event: React.PointerEvent) => event.stopPropagation();
  return (
    <section {...{ [DROP_ZONE_ATTR]: "deck" }} className="flex shrink-0 flex-col">
      <PanelBar
        open={open}
        canCollapse
        onToggle={() => setOpen((value) => !value)}
        onResizeStart={beginResize}
        className="flex"
      >
        <div className="flex w-full items-center gap-4 px-3">
          <div className="flex items-baseline gap-2">
            {title}
            {count !== null && <span className="font-num text-[14px] text-subtle">{count}</span>}
          </div>
          <span onPointerDown={keepPress}>{controls}</span>
          <span className="ml-auto" onPointerDown={keepPress}>
            {extra}
          </span>
        </div>
      </PanelBar>
      {open && (
        <div className="min-h-0 overflow-auto px-2 py-1.5" style={{ height }}>
          {children}
        </div>
      )}
    </section>
  );
};
