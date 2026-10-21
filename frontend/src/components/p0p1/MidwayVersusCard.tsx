import { type MouseEvent } from "react";
import {
  VsCardShell,
  VsCategoryHeader,
  VsTwoColumnLayout,
  VsThreeColumnLayout,
  VsMetricSide,
  PagerNav,
  useVersusPager,
  VersusModal,
} from "./PickVersusCard";
import type { MidwaySlotVersus, MidwayVersusSide, GihwrBounds } from "../../data/p0p1Results";
import type { SlotKey } from "../../types/p0p1";

const GREEN = "#2ee85c";
const GOLD = "#ffc63a";
const TEXT = "#e6ecf5";

function barFill(gihwr: number | null, bounds: GihwrBounds): number {
  if (gihwr === null) return 0;
  const span = bounds.max - bounds.min;
  if (span <= 0) return 100;
  return Math.max(4, Math.min(100, ((gihwr - bounds.min) / span) * 100));
}

function gihwrDisplay(gihwr: number | null): string {
  return gihwr !== null ? `${(gihwr * 100).toFixed(1)}%` : "—";
}

// ── Column collapse ────────────────────────────────────────────────────────────

type Role = "yours" | "crowd" | "best";

interface Column {
  side: MidwayVersusSide;
  roles: Role[];
  label: string;
  accent: string;
}

const ROLE_LABEL: Record<Role, string> = {
  yours: "YOUR PICK",
  crowd: "CROWD FAVORITE",
  best: "BEST POSSIBLE",
};

const MERGED_ROLE_LABEL: Record<Role, string> = {
  best: "BEST POSSIBLE",
  crowd: "CROWD",
  yours: "YOURS",
};

const MERGED_ROLE_ORDER: Role[] = ["best", "crowd", "yours"];

function columnLabel(roles: Role[], pickLabel: string | undefined): string {
  if (roles.length === 1) {
    const [role] = roles;
    if (role === "yours" && pickLabel) {
      return pickLabel;
    }
    return ROLE_LABEL[role];
  }
  const parts: string[] = [];
  for (const role of MERGED_ROLE_ORDER) {
    if (!roles.includes(role)) {
      continue;
    }
    parts.push(role === "yours" && pickLabel ? pickLabel : MERGED_ROLE_LABEL[role]);
  }
  return parts.join("・");
}

function accentFor(roles: Role[]): string {
  if (roles.includes("best") && roles.includes("yours")) return GREEN;
  return TEXT;
}

function buildColumns(versus: MidwaySlotVersus, pickLabel: string | undefined): Column[] {
  const present: Array<{ role: Role; side: MidwayVersusSide }> = [];
  present.push({ role: "crowd", side: versus.crowd });
  present.push({ role: "best", side: versus.best });
  if (versus.yours) present.push({ role: "yours", side: versus.yours });

  const order: string[] = [];
  const grouped = new Map<string, { roles: Role[]; side: MidwayVersusSide }>();
  for (const { role, side } of present) {
    if (!grouped.has(side.name)) {
      order.push(side.name);
      grouped.set(side.name, { roles: [], side });
    }
    grouped.get(side.name)!.roles.push(role);
  }

  // Ensure the column containing "yours" is always rightmost
  if (versus.yours) {
    const idx = order.indexOf(versus.yours.name);
    if (idx !== -1) {
      order.splice(idx, 1);
      order.push(versus.yours.name);
    }
  }

  return order.map((name) => {
    const { roles, side } = grouped.get(name)!;
    const label = columnLabel(roles, pickLabel);
    const accent = accentFor(roles);
    return { side, roles, label, accent };
  });
}

// ── Pager hook ─────────────────────────────────────────────────────────────────

export function useMidwayVersusPager(list: MidwaySlotVersus[]) {
  return useVersusPager(list);
}

// ── Modal ──────────────────────────────────────────────────────────────────────

export function MidwayVersusModal({
  pager,
  bounds,
  pickLabel,
}: {
  pager: ReturnType<typeof useMidwayVersusPager>;
  bounds: GihwrBounds;
  pickLabel?: string;
}) {
  return (
    <VersusModal
      pager={pager}
      padding="p-4"
      renderCard={(versus, nav) => <MidwayVersusCard versus={versus} bounds={bounds} pickLabel={pickLabel} {...nav} />}
    />
  );
}

// ── Card ───────────────────────────────────────────────────────────────────────

export function MidwayVersusCard({
  versus,
  onPrev,
  onNext,
  paged = false,
  bounds,
  pickLabel,
}: {
  versus: MidwaySlotVersus;
  onPrev?: () => void;
  onNext?: () => void;
  paged?: boolean;
  bounds: GihwrBounds;
  pickLabel?: string;
}) {
  const stop = (e: MouseEvent) => e.stopPropagation();
  const columns = buildColumns(versus, pickLabel);
  const maxWidth = columns.length === 1 ? 420 : columns.length === 2 ? 820 : 1160;

  return (
    <VsCardShell maxWidth={maxWidth} onClick={stop}>
      <div className="overflow-y-auto flex-1 min-h-0 px-2 pt-2 lg:px-4">
        <VsCategoryHeader slotKey={versus.slotKey as SlotKey} slotLabel={versus.slotLabel} />
        {columns.length === 1 ? (
          <SoloLayout column={columns[0]} bounds={bounds} />
        ) : columns.length === 2 ? (
          <TwoColumnLayout columns={columns as [Column, Column]} bounds={bounds} />
        ) : (
          <ThreeColumnLayout columns={columns as [Column, Column, Column]} bounds={bounds} />
        )}
      </div>
      <PagerNav onPrev={onPrev} onNext={onNext} paged={paged} prevLabel="Prev Slot" nextLabel="Next Slot" />
    </VsCardShell>
  );
}

// ── Layout variants ────────────────────────────────────────────────────────────

function columnCaption(column: Column): string {
  return `GIH`;
}

function SoloLayout({ column, bounds }: { column: Column; bounds: GihwrBounds }) {
  return (
    <VsMetricSide
      label={column.label}
      labelColor={column.accent}
      value={gihwrDisplay(column.side.gihwr)}
      valueColor={column.accent}
      caption={columnCaption(column)}
      fillPct={barFill(column.side.gihwr, bounds)}
      barColor={column.accent}
      dim={column.side.gihwr === null}
      density="comfortable"
      solo
      imageUrl={column.side.imageUrl}
      name={column.side.name}
    />
  );
}

function TwoColumnLayout({ columns, bounds }: { columns: [Column, Column]; bounds: GihwrBounds }) {
  return (
    <VsTwoColumnLayout
      left={<GihwrSide column={columns[0]} bounds={bounds} />}
      right={<GihwrSide column={columns[1]} bounds={bounds} />}
    />
  );
}

function ThreeColumnLayout({
  columns,
  bounds,
}: {
  columns: [Column, Column, Column];
  bounds: GihwrBounds;
}) {
  return (
    <VsThreeColumnLayout
      left={<GihwrSide column={columns[0]} bounds={bounds} tight />}
      middle={<GihwrSide column={columns[1]} bounds={bounds} tight />}
      right={<GihwrSide column={columns[2]} bounds={bounds} tight />}
    />
  );
}

function GihwrSide({ column, bounds, tight = false }: { column: Column; bounds: GihwrBounds; tight?: boolean }) {
  return (
    <VsMetricSide
      label={column.label}
      labelColor={column.accent}
      value={gihwrDisplay(column.side.gihwr)}
      valueColor={column.accent}
      caption={columnCaption(column)}
      fillPct={barFill(column.side.gihwr, bounds)}
      barColor={column.accent}
      dim={column.side.gihwr === null}
      density="comfortable"
      tight={tight}
      imageUrl={column.side.imageUrl}
      name={column.side.name}
    />
  );
}
