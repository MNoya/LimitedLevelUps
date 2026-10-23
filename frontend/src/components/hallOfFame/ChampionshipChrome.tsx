import { SetGlyph } from "../Brand";
import { TabButton } from "../TabButton";
import { cn } from "../../lib/utils";
import { formatChampionshipDay, type ChampionshipView } from "../../data/setChampionship";

export interface ChampionshipTab {
  view: ChampionshipView;
  label: string;
}

export const FINISHED_TABS: ChampionshipTab[] = [
  { view: "table", label: "TABLE" },
  { view: "bracket", label: "BRACKET" },
  { view: "top8", label: "TOP 8" },
];

export const UPCOMING_TABS: ChampionshipTab[] = [
  { view: "table", label: "QUALIFICATION" },
  { view: "top8", label: "TOP 8" },
];

export function ChampionshipTabs({
  tabs,
  view,
  onChange,
  className = "w-[360px]",
}: {
  tabs: ChampionshipTab[];
  view: ChampionshipView;
  onChange: (view: ChampionshipView) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex border-b border-border", className)}>
      {tabs.map((tab) => (
        <TabButton key={tab.view} active={view === tab.view} onClick={() => onChange(tab.view)}>
          {tab.label}
        </TabButton>
      ))}
    </div>
  );
}

export function ChampionshipTitle({ setCode, label, day }: { setCode: string; label: string; day: string | null }) {
  return (
    <span className="flex items-center gap-2.5 min-w-0">
      <SetGlyph code={setCode} size={20} />
      <span className="truncate font-display text-[17px] tracking-[0.04em] text-text">
        {setCode} {label}
      </span>
      {day ? <span className="shrink-0 text-[13px] text-subtle">{formatChampionshipDay(day)}</span> : null}
    </span>
  );
}
