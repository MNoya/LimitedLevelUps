import type { ReactNode } from "react";

import { PanelBar, useResizableHeight } from "../pod/review/resizablePanel";
import { usePersistentBool } from "../../lib/use-persistent-bool";
import { cn } from "../../lib/utils";
import type { PileZone, SortKey } from "../../data/dailySealedLayout";
import { DROP_ZONE_ATTR } from "./pileHitTest";

const DECK_DEFAULT_FRACTION = 0.38;

export const SORT_LABELS: Record<SortKey, string> = { mana: "Mana Value", color: "Color", rarity: "Rarity" };

export const Panel = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="border-b border-border px-3 pb-3 pt-2">
    <h2 className="mb-4 text-center font-display text-[15px] tracking-[0.18em] text-text">{title}</h2>
    {children}
  </section>
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
          <span className={cn("font-num text-[14px]", total !== undefined && total !== count ? "text-text" : "text-subtle")}>
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
      <div className="min-h-0 flex-1 overflow-auto px-2 py-1.5">{children}</div>
    )}
  </section>
);

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
      <PanelBar open={open} canCollapse onToggle={() => setOpen((value) => !value)} onResizeStart={beginResize} className="flex">
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
