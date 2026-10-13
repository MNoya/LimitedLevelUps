import type { MouseEvent, ReactNode } from "react";
import { Link } from "react-router-dom";
import { Check, Trophy, X } from "lucide-react";
import { cn } from "../../lib/utils";
import {
  CountryFlag,
  PicksLockDate,
  PlayerPortrait,
  cardName,
  fullName,
  shortLastName,
  type FieldPlayer,
} from "./fantasyField";
import { useFantasyEvent } from "./fantasyEvents";
import {
  BRACKET_MATCHES,
  GAME_SCORES,
  STAGE_LABEL,
  bracketMatch,
  bySeed,
  entrants,
  matchPickPoints,
  pickedWinner,
  withPickedGames,
  withPickedWinner,
  type BracketMatch,
  type BracketMatchKey,
  type BracketPicks,
  type BracketResults,
  type BracketStage,
} from "./fantasyTop8";

export type BracketProps = {
  seeded: FieldPlayer[];
  picks?: BracketPicks;
  results: BracketResults | null;
  onChange?: (picks: BracketPicks) => void;
  deckOf?: (player: FieldPlayer) => string | null;
  hrefFor?: (player: FieldPlayer) => string;
  onInspect?: (player: FieldPlayer) => void;
  onHover?: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave?: () => void;
};

const ROW_HEIGHT = 52;
const MATCH_HEIGHT = ROW_HEIGHT * 2 + 1;
const BELOW_MATCH = 30;
const PAIR_GAP = 14;
const HALF_GAP = 44;
const HEADING_SPACE = 40;
const QUARTERFINAL_ORDER: BracketMatchKey[] = ["qf1", "qf3", "qf2", "qf4"];

export function Top8Bracket(props: BracketProps) {
  const scored = Boolean(props.picks);
  const slot = MATCH_HEIGHT + (scored ? BELOW_MATCH : 0);
  const quarterTops = [0, slot + PAIR_GAP, 2 * slot + PAIR_GAP + HALF_GAP, 3 * slot + 2 * PAIR_GAP + HALF_GAP];
  const quarterCenters = quarterTops.map((top) => top + MATCH_HEIGHT / 2);
  const semiCenters = [(quarterCenters[0] + quarterCenters[1]) / 2, (quarterCenters[2] + quarterCenters[3]) / 2];
  const finalCenter = (semiCenters[0] + semiCenters[1]) / 2;
  const height = quarterTops[3] + slot + HEADING_SPACE;
  const column = (children: ReactNode) => (
    <div className="relative" style={{ height }}>
      {children}
    </div>
  );
  return (
    <div className="flex flex-col gap-5">
      {props.picks ? <BracketHeader results={props.results} /> : null}
      <div
        className="grid justify-center"
        style={{ gridTemplateColumns: "minmax(0, 330px) 36px minmax(0, 330px) 36px minmax(0, 330px) 32px 190px" }}
      >
        {column(
          QUARTERFINAL_ORDER.map((key, index) => (
            <PositionedMatch
              key={key}
              matchKey={key}
              top={quarterTops[index]}
              heading={index === 0 ? "quarterfinal" : undefined}
              {...props}
            />
          )),
        )}
        {column(
          <>
            <Elbow from={[quarterCenters[0], quarterCenters[1]]} to={semiCenters[0]} />
            <Elbow from={[quarterCenters[2], quarterCenters[3]]} to={semiCenters[1]} />
          </>,
        )}
        {column(
          <>
            <PositionedMatch matchKey="sf1" top={semiCenters[0] - MATCH_HEIGHT / 2} heading="semifinal" {...props} />
            <PositionedMatch matchKey="sf2" top={semiCenters[1] - MATCH_HEIGHT / 2} {...props} />
          </>,
        )}
        {column(<Elbow from={[semiCenters[0], semiCenters[1]]} to={finalCenter} />)}
        {column(<PositionedMatch matchKey="final" top={finalCenter - MATCH_HEIGHT / 2} heading="final" {...props} />)}
        <span />
        {column(
          <div className="absolute inset-x-0 -translate-y-1/2" style={{ top: HEADING_SPACE + finalCenter }}>
            <ChampionPanel {...props} />
          </div>,
        )}
      </div>
    </div>
  );
}

export function Top8BracketList(props: BracketProps) {
  const stages: BracketStage[] = ["quarterfinal", "semifinal", "final"];
  return (
    <div className="flex flex-col gap-5">
      {props.picks ? <BracketHeader results={props.results} /> : null}
      {stages.map((stage) => (
        <div key={stage} className="flex flex-col gap-2">
          <StageHeading stage={stage} />
          <div className="flex flex-col gap-3">
            {BRACKET_MATCHES.filter((match) => match.stage === stage).map((match) => (
              <MatchBlock key={match.key} match={match} {...props} />
            ))}
          </div>
        </div>
      ))}
      <div className="pt-2">
        <ChampionPanel {...props} />
      </div>
    </div>
  );
}

function BracketHeader({ results }: { results: BracketResults | null }) {
  const { bracketLockAt } = useFantasyEvent();
  return (
    <div className="flex flex-col items-center gap-1 text-center text-[14px] text-text">
      <span>
        Pick the winner of each match for <b>2</b> points in Quarterfinals, <b>4</b> in Semifinals and <b>8</b> in
        Finals
      </span>
      <span className="text-subtle">
        Pick the exact game score for <b className="text-text">1</b> more point
      </span>
      {results ? null : <PicksLockDate size={13} prefix="Quarterfinals start" at={bracketLockAt} />}
    </div>
  );
}

function StageHeading({ stage }: { stage: BracketStage }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-display text-[18px] tracking-[0.1em] text-text">{STAGE_LABEL[stage].toUpperCase()}</span>
    </div>
  );
}

function PositionedMatch({
  matchKey,
  top,
  heading,
  ...props
}: BracketProps & { matchKey: BracketMatchKey; top: number; heading?: BracketStage }) {
  return (
    <div className="absolute inset-x-0" style={{ top: top + HEADING_SPACE }}>
      {heading ? (
        <div className="absolute left-0 -top-9">
          <StageHeading stage={heading} />
        </div>
      ) : null}
      <MatchBlock match={bracketMatch(matchKey)} {...props} />
    </div>
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

function MatchBlock({
  match,
  seeded,
  picks,
  results,
  onChange,
  deckOf,
  hrefFor,
  onInspect,
  onHover,
  onLeave,
}: BracketProps & { match: BracketMatch }) {
  const memberPicks = picks ?? {};
  const result = results?.[match.key];
  const winnerOf = results
    ? (key: BracketMatchKey) => results[key]?.winner
    : (key: BracketMatchKey) => pickedWinner(memberPicks, key, seeded);
  const [first, second] = result ? bySeed([result.winner, result.loser], seeded) : entrants(match, seeded, winnerOf);
  const pick = picks?.[match.key];
  const earned = result && picks ? matchPickPoints(match, pick, result) : null;
  const editable = Boolean(onChange) && !results;

  const choose = (player: FieldPlayer | undefined) => {
    if (player && editable && onChange) {
      onChange(withPickedWinner(memberPicks, match.key, player));
    }
  };
  const rowProps = {
    match,
    picks: memberPicks,
    results,
    editable,
    earned,
    deckOf,
    hrefFor,
    onInspect,
    onHover,
    onLeave,
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="relative border border-border2 bg-surface">
        <EntrantRow
          player={first}
          placeholder={placeholderFor(match, 0)}
          onChoose={() => choose(first)}
          {...rowProps}
        />
        <div className="h-px bg-border" />
        <EntrantRow
          player={second}
          placeholder={placeholderFor(match, 1)}
          onChoose={() => choose(second)}
          {...rowProps}
        />
      </div>
      {editable ? (
        <GamesChips
          disabled={!pick}
          selected={pick?.games}
          onSelect={(games) => onChange?.(withPickedGames(memberPicks, match.key, games))}
        />
      ) : null}
      {results && picks ? (
        <YourCall pickName={pick?.winner} pickGames={pick?.games} seeded={seeded} result={result} />
      ) : null}
    </div>
  );
}

function EntrantRow({
  player,
  placeholder,
  match,
  picks,
  results,
  editable,
  earned,
  deckOf,
  hrefFor,
  onInspect,
  onChoose,
  onHover,
  onLeave,
}: {
  player: FieldPlayer | undefined;
  placeholder: string;
  match: BracketMatch;
  picks: BracketPicks;
  results: BracketResults | null;
  editable: boolean;
  earned: number | null;
  deckOf?: (player: FieldPlayer) => string | null;
  hrefFor?: (player: FieldPlayer) => string;
  onInspect?: (player: FieldPlayer) => void;
  onChoose: () => void;
  onHover?: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave?: () => void;
}) {
  if (!player) {
    return (
      <div className="flex items-center px-3 text-[13px] text-subtle italic" style={{ height: ROW_HEIGHT }}>
        {placeholder}
      </div>
    );
  }
  const name = fullName(player);
  const pick = picks[match.key];
  const result = results?.[match.key];
  const picked = pick?.winner === name;
  const awaitingResult = Boolean(results) && !result;
  const won = result ? fullName(result.winner) === name : picked && !awaitingResult;
  const lost = result ? !won : Boolean(pick) && !picked && !awaitingResult;
  const resultGames = result ? { winner: fullName(result.winner), games: result.games } : undefined;
  const games = gamesFor(name, awaitingResult ? undefined : (resultGames ?? pick));
  const deck = deckOf?.(player);
  const href = editable ? undefined : hrefFor?.(player);
  const className = cn(
    "w-full flex items-center gap-3 pl-3 border-0 bg-transparent text-left no-underline transition-colors",
    editable || href ? "cursor-pointer hover:bg-surface2" : "cursor-default",
    !result && picked && "bg-green/10",
  );
  const content = (
    <>
      <span className="w-7 shrink-0 flex justify-center">
        <CountryFlag code={player.countryCode} width={26} />
      </span>
      <span className={cn("flex-1 min-w-0 flex flex-col", lost && "opacity-55")}>
        <span className="truncate font-display text-[17px] tracking-[0.04em] leading-tight text-text">
          {name.toUpperCase()}
        </span>
        {deck ? <span className="truncate text-[12px] text-subtle">{deck}</span> : null}
      </span>
      {result && picked && won && earned ? (
        <span className="shrink-0 font-num text-[13px] font-semibold text-green [text-box:trim-both_cap_alphabetic]">
          +{earned}
        </span>
      ) : null}
      {result && picked ? <PickMarker correct={won} /> : null}
      <span
        className={cn(
          "w-11 self-stretch shrink-0 flex items-center justify-center font-num text-[18px] font-semibold",
          won && games ? "bg-green text-black" : "bg-surface2 text-subtle",
        )}
      >
        {games ?? ""}
      </span>
    </>
  );
  const hoverProps = {
    onMouseEnter: (event: MouseEvent<HTMLElement>) => onHover?.(player, event.currentTarget),
    onMouseLeave: onLeave,
    onContextMenu: onInspect
      ? (event: MouseEvent<HTMLElement>) => {
          event.preventDefault();
          onInspect(player);
        }
      : undefined,
    style: { height: ROW_HEIGHT },
    className,
  };
  if (href) {
    return (
      <Link to={href} state={{ fromList: true }} {...hoverProps}>
        {content}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onChoose} {...hoverProps}>
      {content}
    </button>
  );
}

function GamesChips({
  disabled,
  selected,
  onSelect,
}: {
  disabled: boolean;
  selected: string | undefined;
  onSelect: (games: (typeof GAME_SCORES)[number]) => void;
}) {
  return (
    <div className={cn("flex items-center justify-center gap-1", disabled && "opacity-40")}>
      {GAME_SCORES.map((games) => (
        <button
          key={games}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(games)}
          className={cn(
            "px-2 py-0.5 border font-num text-[12px] transition-colors",
            disabled ? "cursor-default" : "cursor-pointer",
            selected === games ? "border-green/60 bg-green/10 text-text" : "border-border2 bg-surface text-subtle",
          )}
        >
          {games}
        </button>
      ))}
    </div>
  );
}

function YourCall({
  pickName,
  pickGames,
  seeded,
  result,
}: {
  pickName: string | undefined;
  pickGames: string | undefined;
  seeded: FieldPlayer[];
  result: BracketResults[BracketMatchKey];
}) {
  if (!pickName) {
    return <span className="text-center text-[12px] text-subtle">No pick</span>;
  }
  const picked = seeded.find((player) => fullName(player) === pickName);
  const correct = result !== undefined && pickName === fullName(result.winner);
  const exact = correct && pickGames === result.games;
  return (
    <span className="text-center text-[12px] text-subtle">
      Your pick:{" "}
      <span className={correct ? "text-green" : "text-text"}>{picked ? shortLastName(picked) : pickName}</span>
      {pickGames ? <span className={exact ? "text-green" : "text-text"}> {pickGames}</span> : null}
    </span>
  );
}

function PickMarker({ correct }: { correct: boolean }) {
  return correct ? (
    <Check size={15} strokeWidth={2.5} className="shrink-0 text-green" />
  ) : (
    <X size={15} strokeWidth={2.5} className="shrink-0 text-red" />
  );
}

function ChampionPanel({ seeded, picks, results, hrefFor, onHover, onLeave }: BracketProps) {
  const finalResult = results?.final;
  const champion = finalResult ? finalResult.winner : pickedWinner(picks ?? {}, "final", seeded);
  const calledName = picks?.final?.winner;
  const called = calledName ? seeded.find((player) => fullName(player) === calledName) : undefined;
  return (
    <div className="flex flex-col items-center gap-2">
      <span className="flex items-center gap-1.5 font-display text-[15px] tracking-[0.14em] text-gold">
        <Trophy size={15} />
        {finalResult ? "CHAMPION" : "YOUR CHAMPION"}
      </span>
      <ChampionLink
        champion={champion}
        href={champion && finalResult ? hrefFor?.(champion) : undefined}
        onHover={onHover}
        onLeave={onLeave}
      >
        <span
          className="w-[112px] h-[112px] overflow-hidden rounded-full bg-surface2 flex items-center justify-center"
          style={{ boxShadow: "0 0 0 2px #0a0c10, 0 0 0 3px #f5c542, 0 0 26px #f5c54244" }}
        >
          {champion ? <PlayerPortrait player={champion} initialsSize={34} /> : <Trophy size={40} className="text-dim" />}
        </span>
        <span className="text-[14px] font-semibold text-text text-center">
          {champion ? cardName(champion) : "Pick the Final winner"}
        </span>
      </ChampionLink>
      {finalResult && picks ? (
        <span className="text-[12px] text-subtle text-center">
          {called ? (
            <>
              Your pick:{" "}
              <span className={fullName(called) === fullName(finalResult.winner) ? "text-green" : "text-text"}>
                {shortLastName(called)}
              </span>
            </>
          ) : (
            "No pick"
          )}
        </span>
      ) : null}
    </div>
  );
}

function ChampionLink({
  champion,
  href,
  onHover,
  onLeave,
  children,
}: {
  champion: FieldPlayer | undefined;
  href?: string;
  onHover?: (player: FieldPlayer, element: HTMLElement) => void;
  onLeave?: () => void;
  children: ReactNode;
}) {
  const className = "flex flex-col items-center gap-2 no-underline";
  const hoverProps = {
    onMouseEnter: (event: MouseEvent<HTMLElement>) => (champion ? onHover?.(champion, event.currentTarget) : undefined),
    onMouseLeave: onLeave,
  };
  if (href) {
    return (
      <Link to={href} state={{ fromList: true }} className={className} {...hoverProps}>
        {children}
      </Link>
    );
  }
  return (
    <span className={className} {...hoverProps}>
      {children}
    </span>
  );
}

function placeholderFor(match: BracketMatch, index: 0 | 1): string {
  if (!match.feeders) {
    return "";
  }
  const feeder = bracketMatch(match.feeders[index]);
  const number = BRACKET_MATCHES.filter((entry) => entry.stage === feeder.stage).indexOf(feeder) + 1;
  const stageShort = feeder.stage === "quarterfinal" ? "QF" : "SF";
  return `Winner of ${stageShort}${number}`;
}

function gamesFor(name: string, call: { winner: string; games?: string } | undefined): string | null {
  if (!call) {
    return null;
  }
  if (call.winner === name) {
    return "3";
  }
  return call.games ? call.games.slice(-1) : null;
}
