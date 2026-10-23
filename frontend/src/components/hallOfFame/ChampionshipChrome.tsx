import { SiTwitch, SiYoutube } from "react-icons/si";
import { SetGlyph } from "../Brand";
import { SITE_LINKS } from "../../data/site";
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

export function ChampionshipTitle({
  setCode,
  label,
  day,
  media = null,
}: {
  setCode: string;
  label: string;
  day: string | null;
  media?: ChampionshipMedia | null;
}) {
  return (
    <span className="flex items-center gap-2.5 min-w-0">
      <SetGlyph code={setCode} size={20} />
      <span className="truncate font-display text-[17px] tracking-[0.04em] text-text">
        {setCode} {label}
      </span>
      {day ? <span className="shrink-0 text-[13px] text-subtle">{formatChampionshipDay(day)}</span> : null}
      {media ? <ChampionshipMediaLink media={media} /> : null}
    </span>
  );
}

export function ChampionshipMobileTitle(props: Parameters<typeof ChampionshipTitle>[0]) {
  return (
    <div className="flex justify-center px-3 py-2.5 border-b border-border">
      <ChampionshipTitle {...props} />
    </div>
  );
}

export interface ChampionshipMedia {
  kind: "twitch" | "vod";
  url: string;
}

export function championshipMedia(live: boolean, vodUrl: string | null | undefined): ChampionshipMedia | null {
  if (live) {
    return { kind: "twitch", url: SITE_LINKS.championshipTwitch };
  }
  return vodUrl ? { kind: "vod", url: vodUrl } : null;
}

function ChampionshipMediaLink({ media }: { media: ChampionshipMedia }) {
  const live = media.kind === "twitch";
  const Icon = live ? SiTwitch : SiYoutube;
  return (
    <a
      href={media.url}
      target="_blank"
      rel="noreferrer"
      className={cn(
        "shrink-0 ml-4 flex items-center gap-2 no-underline font-display text-[17px] tracking-[0.04em]",
        "transition-colors hover:text-green",
        live ? "text-green" : "text-text",
      )}
    >
      {live ? (
        <span className="rounded-full bg-green text-bg px-1.5 py-0.5 text-[11px] leading-none font-sans font-bold tracking-wide">
          LIVE
        </span>
      ) : null}
      <Icon size={17} className="-translate-y-[1.5px]" />
      {live ? "TWITCH" : "VOD"}
    </a>
  );
}
