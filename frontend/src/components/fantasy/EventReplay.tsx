import { useLayoutEffect, useMemo, useRef, useState, type Ref } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Trophy } from "lucide-react";
import { SectionLabel } from "../SectionLabel";
import { TabLink } from "../TabButton";
import { SetGlyph } from "../Brand";
import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";
import { SearchBox, fullName, normalizeSearch, type FieldPlayer } from "./fantasyField";
import {
  EventCrest,
  EventSwitcher,
  EventTitle,
  FieldTile,
  HoverCard,
  ProfileHint,
  useHoverTarget,
} from "./FantasyParts";
import { PlayerProfile, PlayerProfileSheet } from "./PlayerProfilePanel";
import { Top8Bracket, Top8BracketList } from "./Top8Bracket";
import { ReplayStandings } from "./ReplayStandings";
import { eventDays, fantasyEventPath } from "./fantasyEvents";
import {
  REPLAY_STAGE_LABEL,
  replayProfileEvent,
  replayStage,
  standingsAfter,
  standingsRound,
  type EventReplay as Replay,
  type ReplayPlayer,
  type ReplayStage,
} from "./fantasyReplay";

export type ReplayView = "field" | "standings" | "top8";

export const REPLAY_VIEW_SLUG: Record<ReplayView, string | undefined> = {
  field: undefined,
  standings: "standings",
  top8: "top-8",
};

const VIEW_LABEL: Record<ReplayView, string> = {
  field: "PLAYERS",
  standings: "STANDINGS",
  top8: "TOP 8",
};

export function EventReplay({ replay, view }: { replay: Replay; view: ReplayView }) {
  const isMobile = useIsMobile(1024);
  const [search, setSearch] = useState("");
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { hoverTarget, onHover, onLeave } = useHoverTarget(isMobile);

  const basePath = fantasyEventPath(replay.event);
  const viewPath = (option: ReplayView) => {
    const slug = REPLAY_VIEW_SLUG[option];
    return slug ? `${basePath}/${slug}` : basePath;
  };
  const playerHref = (player: FieldPlayer) => {
    const entry = replay.byName.get(fullName(player));
    const params = new URLSearchParams(searchParams);
    params.set("player", entry ? (replay.slugOf.get(entry) ?? "") : "");
    return `${location.pathname}?${params}`;
  };
  const playerParam = searchParams.get("player");
  const sheetPlayer = playerParam ? (replay.bySlug.get(playerParam) ?? null) : null;
  const sheetOrder = useMemo(() => {
    if (view === "standings") {
      const round = standingsRound(replay, searchParams.get("round"));
      return standingsAfter(replay, round).map((row) => row.player);
    }
    return view === "top8" ? replay.seeded : replay.players;
  }, [replay, view, searchParams]);
  const sheetIndex = sheetPlayer ? sheetOrder.indexOf(sheetPlayer) : -1;
  const neighborHref = (offset: number) => {
    const neighbor = sheetIndex >= 0 ? sheetOrder[sheetIndex + offset] : undefined;
    return neighbor ? playerHref(neighbor) : undefined;
  };
  const closeSheet = () => {
    if ((location.state as { fromList?: boolean } | null)?.fromList) {
      navigate(-1);
      return;
    }
    const params = new URLSearchParams(searchParams);
    params.delete("player");
    navigate({ pathname: location.pathname, search: params.toString() }, { replace: true });
  };

  const deckOf = (player: FieldPlayer) => replay.byName.get(fullName(player))?.deck ?? null;
  const bracketProps = {
    seeded: replay.seeded,
    results: replay.results,
    deckOf,
    hrefFor: playerHref,
    onHover,
    onLeave,
  };
  const playerProps = { replay, compact: isMobile, playerHref, onHover, onLeave };
  const body = {
    field: <PlayerGroups {...playerProps} search={search} onSearch={setSearch} />,
    standings: <ReplayStandings source={replay} {...playerProps} />,
    top8: isMobile ? <Top8BracketList {...bracketProps} /> : <Top8Bracket {...bracketProps} />,
  }[view];
  const gutter = isMobile ? "px-3" : "px-7";
  const statusProps = { replay, href: playerHref(replay.results.final.winner), onHover, onLeave };

  return (
    <main className="flex-1 lg:min-h-0 lg:overflow-y-auto themed-scrollbar lg:[scrollbar-gutter:stable]">
      <div
        className={cn(
          "bg-surface border-b border-border flex flex-col items-center gap-2.5",
          isMobile ? "px-3 py-3" : "py-6",
        )}
      >
        <div className={cn("flex items-center", isMobile ? "gap-3" : "gap-7")}>
          {replay.event.crest ? (
            <EventCrest src={replay.event.crest} alt={replay.event.name} height={isMobile ? 44 : 80} />
          ) : null}
          {isMobile ? (
            <EventTitle
              event={replay.header}
              label={titleLabel(isMobile, Boolean(replay.event.replayOnly))}
              switcher={<EventSwitcher activeCode={replay.event.code} mobile />}
              balanced={false}
              labelSize={12}
              glyphSize={32}
              titleSize={34}
              citySize={17}
            />
          ) : (
            <ReplayHeading replay={replay} statusProps={statusProps} />
          )}
        </div>
        {isMobile ? <ReplayStatus {...statusProps} inHeading={false} /> : null}
      </div>
      <div className="sticky top-0 z-10 bg-bg/95 backdrop-blur border-b border-border">
        <div className={cn("max-w-[1400px] mx-auto", gutter)}>
          <div className="flex">
            {(Object.keys(VIEW_LABEL) as ReplayView[]).map((option) => (
              <TabLink key={option} active={view === option} to={viewPath(option)}>
                {VIEW_LABEL[option]}
              </TabLink>
            ))}
          </div>
        </div>
      </div>
      <div className={cn("max-w-[1400px] mx-auto pb-8", gutter, isMobile ? "pt-3" : "pt-6")}>{body}</div>

      {hoverTarget ? (
        <HoverCard target={hoverTarget}>
          <PlayerProfile
            player={hoverTarget.player}
            compact
            preview
            event={replayProfileEvent(replay, hoverTarget.player)}
          />
          <ProfileHint rightClick={false} />
        </HoverCard>
      ) : null}
      {sheetPlayer ? (
        <PlayerProfileSheet
          player={sheetPlayer}
          event={replayProfileEvent(replay, sheetPlayer, playerHref)}
          prevHref={neighborHref(-1)}
          nextHref={neighborHref(1)}
          onClose={closeSheet}
        />
      ) : null}
    </main>
  );
}

function titleLabel(isMobile: boolean, replayOnly: boolean): "shown" | "hidden" | "removed" {
  if (!replayOnly) {
    return "shown";
  }
  return isMobile ? "removed" : "hidden";
}

function ReplayHeading({ replay, statusProps }: { replay: Replay; statusProps: ReplayStatusProps }) {
  const titleRef = useRef<HTMLSpanElement>(null);
  const glyphRef = useRef<HTMLSpanElement>(null);
  const playersRef = useRef<HTMLSpanElement>(null);
  const [overhang, setOverhang] = useState({ left: 0, right: 0 });
  useLayoutEffect(() => {
    const measure = () => {
      const titleWidth = titleRef.current?.offsetWidth ?? 0;
      const playersWidth = playersRef.current?.offsetWidth ?? 0;
      const glyphWidth = glyphRef.current?.offsetWidth ?? 0;
      const titleOverhang = Math.max(0, (titleWidth - playersWidth) / 2);
      setOverhang({ left: titleOverhang + glyphWidth, right: titleOverhang });
    };
    measure();
    void document.fonts.ready.then(measure);
  }, [replay]);

  return (
    <div
      className="grid items-end"
      style={{ gridTemplateColumns: `minmax(${overhang.left}px, auto) auto minmax(${overhang.right}px, auto)` }}
    >
      <SectionLabel
        size={13}
        color="#b8c0d0"
        className={cn("col-start-2 justify-self-center mb-1", replay.event.replayOnly && "invisible")}
      >
        FANTASY MAGIC
      </SectionLabel>
      <span className="col-start-2 row-start-2 justify-self-center w-0 flex justify-center">
        <span ref={titleRef} className="relative shrink-0 flex">
          <span ref={glyphRef} className="absolute right-full top-1/2 -translate-y-1/2 pr-2 flex">
            <SetGlyph code={replay.header.setCode} size={40} />
          </span>
          <span
            className="font-display tracking-[0.04em] text-text whitespace-nowrap"
            style={{ fontSize: 42, lineHeight: 0.9 }}
          >
            {replay.header.title}
          </span>
          <span className="absolute left-full bottom-0 ml-3 flex items-end gap-1.5">
            <span className="font-display text-subtle tracking-[0.06em]" style={{ fontSize: 18, lineHeight: 1 }}>
              {replay.header.city}
            </span>
            <EventSwitcher activeCode={replay.event.code} />
          </span>
        </span>
      </span>
      <ReplayStatus {...statusProps} inHeading playersRef={playersRef} />
    </div>
  );
}

type ReplayStatusProps = {
  replay: Replay;
  href: string;
  onHover: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave: () => void;
};

function ReplayStatus({
  replay,
  href,
  onHover,
  onLeave,
  inHeading,
  playersRef,
}: ReplayStatusProps & { inHeading: boolean; playersRef?: Ref<HTMLSpanElement> }) {
  const champion = replay.results.final.winner;
  const cell = inHeading ? "row-start-3 mt-2.5" : "";
  return (
    <span
      className={cn(
        "font-display text-[16px] tracking-[0.08em]",
        inHeading ? "contents" : "w-full grid grid-cols-[1fr_auto_1fr] items-center gap-x-6",
      )}
    >
      <span className={cn("justify-self-end text-text whitespace-nowrap", cell, inHeading && "col-start-1 mr-6")}>
        {eventDays(replay.event, new Date()).toUpperCase()}
      </span>
      <span
        ref={playersRef}
        className={cn("justify-self-center text-text whitespace-nowrap", cell, inHeading && "col-start-2")}
      >
        {replay.players.length} <span className="text-subtle">PLAYERS</span>
      </span>
      <Link
        to={href}
        state={{ fromList: true }}
        onMouseEnter={(event) => onHover(champion, event.currentTarget)}
        onMouseLeave={onLeave}
        className={cn(
          "justify-self-start flex items-center gap-1.5 text-gold whitespace-nowrap no-underline hover:underline",
          cell,
          inHeading && "col-start-3 ml-6",
        )}
      >
        <Trophy size={15} />
        {fullName(champion).toUpperCase()}
      </Link>
    </span>
  );
}

function PlayerGroups({
  replay,
  search,
  onSearch,
  compact,
  playerHref,
  onHover,
  onLeave,
}: {
  replay: Replay;
  search: string;
  onSearch: (search: string) => void;
  compact: boolean;
  playerHref: (player: FieldPlayer) => string;
  onHover: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave: () => void;
}) {
  const groups = useMemo(() => {
    const query = normalizeSearch(search);
    const byStage = new Map<ReplayStage, ReplayPlayer[]>();
    for (const player of replay.players) {
      const haystack = normalizeSearch(`${fullName(player)} ${player.country} ${player.deck ?? ""}`);
      if (query && !haystack.includes(query)) {
        continue;
      }
      const stage = replayStage(replay, player);
      byStage.set(stage, [...(byStage.get(stage) ?? []), player]);
    }
    const stages: ReplayStage[] = ["top8", "day2", "day1"];
    return stages.filter((stage) => byStage.has(stage)).map((stage) => ({ stage, players: byStage.get(stage) ?? [] }));
  }, [replay, search]);

  const searchBox = (
    <SearchBox
      value={search}
      onChange={onSearch}
      placeholder="Search players or decks"
      className={compact ? "flex-1 min-w-0" : "w-[260px]"}
    />
  );
  return (
    <div className={cn("flex flex-col", compact ? "gap-5" : "gap-8")}>
      {groups.length === 0 ? <div className="flex justify-end">{searchBox}</div> : null}
      {groups.map((group, index) => (
        <div key={group.stage}>
          <div className={cn("flex items-center justify-between gap-4", compact ? "mb-2" : "mb-3")}>
            <SectionLabel size={compact ? 16 : 18} color="#ffffff" className="shrink-0">
              {REPLAY_STAGE_LABEL[group.stage]}
            </SectionLabel>
            {index === 0 ? searchBox : null}
          </div>
          <div className={cn("grid", compact ? "grid-cols-1 gap-1.5" : "grid-cols-4 gap-3")}>
            {group.players.map((player) => (
              <FieldTile
                key={player.rank}
                player={player}
                large={!compact}
                faded={group.stage === "day1"}
                href={playerHref(player)}
                detail={
                  <>
                    <span className="shrink-0 font-num text-text">{player.matchRecord}</span>
                    {player.deck ? <span className="truncate">{player.deck}</span> : null}
                  </>
                }
                aside={<span className="shrink-0 font-num text-[13px] text-subtle">{player.rank}</span>}
                onHover={(element) => onHover(player, element)}
                onLeave={onLeave}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
