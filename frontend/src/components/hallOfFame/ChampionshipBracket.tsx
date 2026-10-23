import type { ReactNode } from "react";
import { Crown } from "lucide-react";
import { AAvatar } from "../Brand";
import { Pips } from "../ManaPips";
import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";
import { orderedDeckColors } from "../../data/utils";
import { gamesWon, playerLabel, type ChampionshipBracket as Bracket } from "../../data/setChampionship";
import type { PodEventMatchRow, PodEventParticipantRow } from "../../types/leaderboard";

const HEADING_SPACE = 32;
const PIP_SLOTS = 6.4;

const BRACKET_SIZES = {
  regular: {
    row: 38,
    pairGap: 12,
    halfGap: 28,
    matchColumn: 280,
    championColumn: 150,
    avatar: 24,
    name: 15,
    score: 17,
    pips: 12,
    portrait: 104,
    championName: 17,
  },
  mini: {
    row: 30,
    pairGap: 8,
    halfGap: 16,
    matchColumn: 0,
    championColumn: 0,
    avatar: 20,
    name: 14,
    score: 15,
    pips: 11,
    portrait: 80,
    championName: 16,
  },
  large: {
    row: 52,
    pairGap: 16,
    halfGap: 40,
    matchColumn: 360,
    championColumn: 200,
    avatar: 32,
    name: 18,
    score: 21,
    pips: 15,
    portrait: 140,
    championName: 20,
  },
};

type BracketSize = (typeof BRACKET_SIZES)["regular"];

type RowProps = {
  byName: Map<string, PodEventParticipantRow>;
  showDecks: boolean;
  selected?: string | null;
  onSelect: (name: string) => void;
  dims: BracketSize;
};

export function ChampionshipBracket({
  bracket,
  champion,
  stacked = false,
  large = false,
  ...rowProps
}: Omit<RowProps, "dims"> & { bracket: Bracket; champion: string | null; stacked?: boolean; large?: boolean }) {
  const isMobile = useIsMobile(1024);
  const props = { ...rowProps, dims: large && !isMobile ? BRACKET_SIZES.large : BRACKET_SIZES.regular };
  if (isMobile || stacked) {
    const championPanel = <ChampionPanel name={champion} {...props} dims={BRACKET_SIZES.mini} />;
    return <TreeList bracket={bracket} champion={championPanel} {...props} />;
  }
  const championPanel = <ChampionPanel name={champion} {...props} centerOnPortrait />;
  return <Tree bracket={bracket} champion={championPanel} {...props} />;
}

export function GrandFinal({
  match,
  champion,
  ...rowProps
}: Omit<RowProps, "dims" | "showDecks"> & { match: PodEventMatchRow | undefined; champion: string | null }) {
  const isMobile = useIsMobile(1024);
  const dims = isMobile ? BRACKET_SIZES.regular : BRACKET_SIZES.large;
  const props = { ...rowProps, dims, showDecks: false };
  return (
    <div className={cn("flex items-center", isMobile ? "flex-col gap-14 w-full pt-7" : "gap-16")}>
      <div className="relative" style={{ width: isMobile ? "100%" : dims.matchColumn }}>
        <div className="absolute left-0 -top-7">{FINAL_HEADING}</div>
        <MatchBlock match={match} final {...props} />
      </div>
      <div style={{ width: dims.championColumn }}>
        <ChampionPanel name={champion} {...props} centerOnPortrait />
      </div>
    </div>
  );
}

function Tree({ bracket, champion, ...rowProps }: RowProps & { bracket: Bracket; champion: ReactNode }) {
  const { dims } = rowProps;
  const matchHeight = dims.row * 2 + 1;
  const quarterTops = [
    0,
    matchHeight + dims.pairGap,
    2 * matchHeight + dims.pairGap + dims.halfGap,
    3 * matchHeight + 2 * dims.pairGap + dims.halfGap,
  ];
  const quarterCenters = quarterTops.map((top) => top + matchHeight / 2);
  const semiCenters = [(quarterCenters[0] + quarterCenters[1]) / 2, (quarterCenters[2] + quarterCenters[3]) / 2];
  const finalCenter = (semiCenters[0] + semiCenters[1]) / 2;
  const height = quarterTops[3] + matchHeight + HEADING_SPACE;
  const matchColumn = `minmax(0, ${dims.matchColumn}px)`;
  const column = (children: ReactNode) => (
    <div className="relative" style={{ height }}>
      {children}
    </div>
  );
  const positioned = (
    match: PodEventMatchRow | undefined,
    top: number,
    heading?: ReactNode,
    firstRound = false,
  ) => (
    <div key={top} className="absolute inset-x-0" style={{ top: top + HEADING_SPACE }}>
      {heading ? <div className="absolute left-0 -top-7">{heading}</div> : null}
      <MatchBlock
        match={match}
        final={heading === FINAL_HEADING}
        {...rowProps}
        showDecks={firstRound && rowProps.showDecks}
      />
    </div>
  );
  return (
    <div
      className="grid"
      style={{
        gridTemplateColumns: `${matchColumn} 24px ${matchColumn} 24px ${matchColumn} 20px ${dims.championColumn}px`,
      }}
    >
      {column(
        bracket.quarterfinals.map((match, index) =>
          positioned(match, quarterTops[index], index === 0 ? <StageHeading label="ROUND 1" /> : undefined, true),
        ),
      )}
      {column(
        <>
          <Elbow from={[quarterCenters[0], quarterCenters[1]]} to={semiCenters[0]} />
          <Elbow from={[quarterCenters[2], quarterCenters[3]]} to={semiCenters[1]} />
        </>,
      )}
      {column(
        <>
          {positioned(bracket.semifinals[0], semiCenters[0] - matchHeight / 2, <StageHeading label="ROUND 2" />)}
          {positioned(bracket.semifinals[1], semiCenters[1] - matchHeight / 2)}
        </>,
      )}
      {column(<Elbow from={[semiCenters[0], semiCenters[1]]} to={finalCenter} />)}
      {column(positioned(bracket.final, finalCenter - matchHeight / 2, FINAL_HEADING))}
      <span />
      {column(
        <div className="absolute inset-x-0 -translate-y-1/2" style={{ top: HEADING_SPACE + finalCenter }}>
          {champion}
        </div>,
      )}
    </div>
  );
}

function TreeList({ bracket, champion, ...rowProps }: RowProps & { bracket: Bracket; champion: ReactNode }) {
  const firstRound = { ...rowProps, dims: BRACKET_SIZES.mini };
  const secondRound = { ...firstRound, showDecks: false };
  const stages: [ReactNode, (PodEventMatchRow | undefined)[], RowProps][] = [
    [<StageHeading key="r1" label="ROUND 1" />, bracket.quarterfinals, firstRound],
    [<StageHeading key="r2" label="ROUND 2" />, bracket.semifinals, secondRound],
    [FINAL_HEADING, [bracket.final], { ...rowProps, showDecks: false }],
  ];
  return (
    <div className="flex flex-col gap-4">
      {stages.map(([heading, matches, stageProps], index) => (
        <div key={index} className="flex flex-col gap-1.5">
          {heading}
          {matches.map((match, matchIndex) => (
            <MatchBlock key={matchIndex} match={match} final={heading === FINAL_HEADING} {...stageProps} />
          ))}
        </div>
      ))}
      {champion}
    </div>
  );
}

const FINAL_HEADING = (
  <span className="flex items-center gap-1.5 font-display text-[15px] tracking-[0.14em] text-gold">
    <Crown size={14} />
    FINAL
  </span>
);

function StageHeading({ label }: { label: string }) {
  return <span className="font-display text-[15px] tracking-[0.14em] text-text">{label}</span>;
}

function MatchBlock({ match, final = false, ...rowProps }: RowProps & {
  match: PodEventMatchRow | undefined;
  final?: boolean;
}) {
  const emptyRow = <div style={{ height: rowProps.dims.row }} />;
  return (
    <div className={cn("border bg-surface", final ? "border-gold/50" : "border-border2")}>
      {match ? (
        <>
          <EntrantRow name={match.playerAName} match={match} {...rowProps} />
          <div className="h-px bg-border" />
          <EntrantRow name={match.playerBName} match={match} {...rowProps} />
        </>
      ) : (
        <>
          {emptyRow}
          <div className="h-px bg-border" />
          {emptyRow}
        </>
      )}
    </div>
  );
}

function EntrantRow({ name, match, byName, showDecks, selected, onSelect, dims }: RowProps & {
  name: string;
  match: PodEventMatchRow;
}) {
  const participant = byName.get(name);
  const reported = Boolean(match.winnerName);
  const won = match.winnerName === name;
  const games = gamesWon(match, name);
  const deckColors = showDecks ? participant?.deckColors : null;
  return (
    <button
      type="button"
      onClick={() => onSelect(name)}
      className={cn(
        "w-full flex items-center gap-2.5 pl-2.5 pr-3 border-0 text-left cursor-pointer transition-colors",
        "hover:bg-surface2",
        selected === name ? "bg-surface2" : "bg-transparent",
      )}
      style={{ height: dims.row }}
    >
      <AAvatar displayName={name} avatarUrl={participant?.avatarUrl ?? null} size={dims.avatar} />
      <span className={cn("flex-1 min-w-0 flex items-center gap-2", reported && !won && "opacity-55")}>
        <span
          className="flex-1 min-w-0 truncate font-display tracking-[0.04em] leading-tight text-text"
          style={{ fontSize: dims.name }}
        >
          {playerLabel(participant, name).toUpperCase()}
        </span>
        {showDecks ? (
          <span className="shrink-0 flex" style={{ width: dims.pips * PIP_SLOTS }}>
            {deckColors ? <Pips colors={orderedDeckColors(deckColors)} size={dims.pips} /> : null}
          </span>
        ) : null}
      </span>
      <span
        className={cn("shrink-0 font-num font-semibold", won ? "text-green" : "text-muted")}
        style={{ fontSize: dims.score }}
      >
        {games ?? ""}
      </span>
    </button>
  );
}

function ChampionPanel({
  name,
  byName,
  onSelect,
  dims,
  centerOnPortrait = false,
}: RowProps & { name: string | null; centerOnPortrait?: boolean }) {
  const participant = name ? byName.get(name) : undefined;
  const portrait = (
    <span
      className="overflow-hidden rounded-full bg-surface2 flex items-center justify-center"
      style={{
        width: dims.portrait,
        height: dims.portrait,
        boxShadow: "0 0 0 2px #0a0c10, 0 0 0 3px #ffc63a, 0 0 26px #ffc63a44",
      }}
    >
      {name ? (
        <AAvatar displayName={name} avatarUrl={participant?.avatarUrl ?? null} size={dims.portrait} />
      ) : (
        <Crown size={36} className="text-dim" />
      )}
    </span>
  );
  return (
    <button
      type="button"
      disabled={!name}
      onClick={() => (name ? onSelect(name) : undefined)}
      className={cn(
        "relative w-full flex flex-col items-center gap-2 border-0 bg-transparent cursor-pointer",
        "disabled:cursor-default",
      )}
    >
      <span
        className={cn(
          "flex items-center gap-1.5 font-display text-[15px] tracking-[0.14em] text-gold",
          centerOnPortrait && "absolute bottom-full mb-2",
        )}
      >
        <Crown size={15} />
        CHAMPION
      </span>
      {portrait}
      <span
        className={cn(
          "font-display tracking-[0.04em] text-text text-center",
          centerOnPortrait && "absolute top-full mt-2 w-full",
        )}
        style={{ fontSize: dims.championName }}
      >
        {name ? playerLabel(participant, name).toUpperCase() : "TBD"}
      </span>
    </button>
  );
}

function Elbow({ from, to }: { from: [number, number]; to: number }) {
  const line = "absolute bg-border2";
  return (
    <>
      <span className={cn(line, "left-0 w-1/2 h-px")} style={{ top: HEADING_SPACE + from[0] }} />
      <span className={cn(line, "left-0 w-1/2 h-px")} style={{ top: HEADING_SPACE + from[1] }} />
      <span className={cn(line, "left-1/2 w-px")} style={{ top: HEADING_SPACE + from[0], height: from[1] - from[0] }} />
      <span className={cn(line, "right-0 w-1/2 h-px")} style={{ top: HEADING_SPACE + to }} />
    </>
  );
}
