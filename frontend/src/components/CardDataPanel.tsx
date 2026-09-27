import {
  cardDataUrl,
  cardDetailsUrl,
  MIN_GAMES_FOR_INFERENCE,
  type CardGrades,
  type CardStats,
  type DeckColors,
} from "../data/cardStats";
import { tierColor } from "../data/tierList";
import { cn } from "../lib/utils";
import { TEXT_OUTLINE } from "../lib/text-styles";
import { ExternalLink } from "./Icons";
import { Pips } from "./ManaPips";
import { Tooltip } from "./Tooltip";

export function CardDataPanel({
  setCode,
  stats,
  grades,
  docked,
}: {
  setCode: string;
  stats: CardStats;
  grades: CardGrades | undefined;
  docked: boolean;
}) {
  const decks = deckRows(stats, grades);
  if (docked) {
    return (
      <div className={DOCKED_GRID}>
        <div className={cn(HEADLINE_ROW, "relative")}>
          <span className="absolute -left-5 top-0 flex h-full w-[141px] items-center justify-center">
            <SourceLink setCode={setCode} mtgaId={stats.mtgaId} />
          </span>
          <span className="flex flex-1 justify-center pl-[60px]">
            {decks.length > 0 && <OverallGrade grade={grades?.all ?? null} />}
          </span>
        </div>
        <HeadlineStrip stats={stats} className={HEADLINE_ROW} />
        <div>{decks.length > 0 && <DeckChips decks={decks} compact />}</div>
        <StatLedger rows={secondaryStats(stats)} columns={1} />
      </div>
    );
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto text-text">
      {decks.length > 0 && <DeckChips decks={decks} compact={false} />}
      <StatLedger rows={fullStats(stats)} columns={1} />
    </div>
  );
}

const HEADLINE_ROW = "flex h-[68px] shrink-0 items-start pt-[15px]";
const DOCKED_GRID = cn(
  "grid min-h-0 grid-cols-[236px_minmax(0,1fr)] items-start gap-x-4",
  "overflow-y-auto px-5 pb-5 text-text",
);

interface DeckRow {
  key: string;
  pair: DeckColors | null;
  gihWr: number;
  gihGames: number;
  grade: string | undefined;
}

function deckRows(stats: CardStats, grades: CardGrades | undefined): DeckRow[] {
  const rows: DeckRow[] = [];
  for (const [pair, pairStats] of Object.entries(stats.pairs)) {
    if (pairStats?.gihWr != null && pairStats.gihGames >= MIN_GAMES_FOR_INFERENCE) {
      rows.push({ key: pair, pair, gihWr: pairStats.gihWr, gihGames: pairStats.gihGames, grade: grades?.pairs[pair] });
    }
  }
  rows.sort((a, b) => b.gihWr - a.gihWr);
  if (stats.gihWr === null) {
    return rows;
  }
  const overallGrade = grades?.all ?? undefined;
  return [{ key: "all", pair: null, gihWr: stats.gihWr, gihGames: stats.gihGames, grade: overallGrade }, ...rows];
}

function HeadlineStrip({ stats, className }: { stats: CardStats; className: string }) {
  const iwd = stats.iwd === null ? "–" : `${stats.iwd >= 0 ? "+" : ""}${(stats.iwd * 100).toFixed(1)}`;
  const cells: [string, string, string, string?][] = [
    ["ALSA", dec(stats.alsa), STAT_DESCRIPTIONS.alsa],
    ["ATA", dec(stats.ata), STAT_DESCRIPTIONS.ata],
    ["IWD", iwd, STAT_DESCRIPTIONS.iwd, stats.iwd === null ? undefined : "pp"],
  ];
  return (
    <div className={cn("flex", className)}>
      {cells.map(([caption, value, description, unit]) => (
        <HeadlineCell key={caption} caption={caption} description={description} className="flex-1">
          <span className={cn("font-display text-[22px] leading-none text-white", TEXT_OUTLINE)}>
            {value}
            {unit && <span className="ml-0.5 font-num text-[12px] lowercase">{unit}</span>}
          </span>
        </HeadlineCell>
      ))}
    </div>
  );
}

function SourceLink({ setCode, mtgaId }: { setCode: string; mtgaId: number | undefined }) {
  return (
    <a
      href={mtgaId ? cardDetailsUrl(setCode, mtgaId) : cardDataUrl(setCode)}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "flex items-center gap-1 whitespace-nowrap text-[12px] font-semibold uppercase tracking-[0.1em]",
        "leading-none text-white no-underline transition-colors hover:text-green",
        TEXT_OUTLINE,
      )}
    >
      17LANDS
      <ExternalLink size={11} />
    </a>
  );
}

function OverallGrade({ grade }: { grade: string | null }) {
  return (
    <HeadlineCell caption="GIH WR" description={STAT_DESCRIPTIONS.gihWr}>
      <span
        className={cn("font-display text-[22px] leading-none", TEXT_OUTLINE)}
        style={{ color: grade ? tierColor(grade) : "rgba(255,255,255,0.5)" }}
      >
        {grade ?? "–"}
      </span>
    </HeadlineCell>
  );
}

function HeadlineCell({
  caption,
  description,
  className,
  children,
}: {
  caption: string;
  description: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Tooltip label={description} side="top" className="z-[250] max-w-[320px]">
      <span className={cn("flex cursor-default flex-col items-center gap-2", className)}>
        <span
          className={cn(
            "text-[12px] font-semibold uppercase tracking-[0.1em] leading-none text-white",
            TEXT_OUTLINE,
          )}
        >
          {caption}
        </span>
        {children}
      </span>
    </Tooltip>
  );
}

function DeckChips({ decks, compact }: { decks: DeckRow[]; compact: boolean }) {
  return (
    <div className="flex shrink-0 border border-white/15">
      <div className={cn("flex shrink-0 flex-col bg-white/[0.04] py-[6px]", compact ? "w-[60px]" : "w-[76px]")}>
        {decks.map((deck) => (
          <span key={deck.key} className={cn("flex h-[49px] items-center justify-center", !deck.grade && "opacity-50")}>
            <DeckLabel deck={deck} />
          </span>
        ))}
      </div>
      <div className={cn("flex min-w-0 flex-1 flex-col py-[6px]", compact ? "px-2.5" : "px-3")}>
        {decks.map((deck) => (
          <Tooltip key={deck.key} label={`${int(deck.gihGames)} Games In Hand`} side="right" className="z-[250]">
            <span className={cn("flex h-[49px] items-center", !deck.grade && "opacity-50")}>
              <GradeChip deck={deck} />
            </span>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}

function GradeMark({ grade }: { grade: string | undefined }) {
  if (!grade) {
    return <span>–</span>;
  }
  return (
    <span className="relative">
      {grade[0]}
      <span className="absolute left-full">{grade.slice(1)}</span>
    </span>
  );
}

function GradeChip({ deck }: { deck: DeckRow }) {
  const color = deck.grade ? tierColor(deck.grade) : "rgba(255,255,255,0.2)";
  return (
    <span className="flex h-11 flex-1 items-stretch overflow-hidden rounded-md border-2" style={{ borderColor: color }}>
      <span
        className="flex w-14 items-center justify-center font-display text-[24px] leading-none text-bg pr-1"
        style={{ backgroundColor: color }}
      >
        <GradeMark grade={deck.grade} />
      </span>
      <span className="flex flex-1 items-center justify-center font-num text-[20px] leading-none">
        {pct(deck.gihWr)}
      </span>
    </span>
  );
}

function DeckLabel({ deck }: { deck: DeckRow }) {
  if (!deck.pair) {
    return <span className="font-display text-[20px] leading-none">AVG</span>;
  }
  return <Pips colors={deck.pair} size={16} />;
}

const STAT_ROW = "flex h-[42px] cursor-default items-center justify-between gap-3 bg-[#161b26] px-3 text-[15px]";

function StatLedger({ rows, columns }: { rows: [string, string, string][]; columns: 1 | 2 }) {
  return (
    <div
      className={cn(
        "grid shrink-0 grid-cols-1 gap-px border border-white/15 bg-white/10",
        columns === 2 && "min-[440px]:grid-cols-2",
      )}
    >
      {rows.map(([label, value, description]) => (
        <Tooltip key={label} label={description} side="bottom" align="start" className="z-[250] max-w-[320px]">
          <div className={STAT_ROW}>
            <span>{label}</span>
            <span className="font-num">{value}</span>
          </div>
        </Tooltip>
      ))}
    </div>
  );
}

function fullStats(stats: CardStats): [string, string, string][] {
  const [gp, gihGames, gpWr, ohWr, gdWr, gnsWr] = secondaryStats(stats);
  return [
    ["Average last seen at", dec(stats.alsa), STAT_DESCRIPTIONS.alsa],
    ["Average taken at", dec(stats.ata), STAT_DESCRIPTIONS.ata],
    gp,
    gihGames,
    gpWr,
    ohWr,
    gdWr,
    ["Games in hand win rate", pct(stats.gihWr), STAT_DESCRIPTIONS.gihWr],
    gnsWr,
    ["Improvement when drawn", signedPoints(stats.iwd), STAT_DESCRIPTIONS.iwd],
  ];
}

function secondaryStats(stats: CardStats): [string, string, string][] {
  return [
    ["Number of games played", int(stats.gp), STAT_DESCRIPTIONS.gp],
    ["Number of games in hand", int(stats.gihGames), STAT_DESCRIPTIONS.gihGames],
    ["Games played win rate", pct(stats.gpWr), STAT_DESCRIPTIONS.gpWr],
    ["Opening hand win rate", pct(stats.ohWr), STAT_DESCRIPTIONS.ohWr],
    ["Games drawn win rate", pct(stats.gdWr), STAT_DESCRIPTIONS.gdWr],
    ["Games not drawn win rate", pct(stats.gnsWr), STAT_DESCRIPTIONS.gnsWr],
  ];
}

const STAT_DESCRIPTIONS = {
  alsa: "Average pick number where this card was last seen in packs",
  ata: "Average pick number at which this card was taken by 17Lands drafters",
  gp: "Number of games played with this card in the maindeck",
  gihGames: "Number of times this card was drawn, either in the opening hand or later",
  gpWr: "Win rate of decks with this card in the maindeck",
  ohWr: "Win rate of games where this card was in the opening hand",
  gdWr: "Win rate of games where this card was drawn, not counting cards from the opening hand",
  gihWr: "Win rate of games where this card was drawn, either in the opening hand or later",
  gnsWr: "Win rate of games where this card was in the maindeck, but was never drawn",
  iwd: "Difference between Games in hand win rate and Games not drawn win rate",
};

const pct = (value: number | null) => (value === null ? "–" : `${(value * 100).toFixed(1)}%`);
const signedPoints = (value: number | null) =>
  value === null ? "–" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}pp`;
const dec = (value: number | null) => (value === null ? "–" : value.toFixed(2));
const int = (value: number) => value.toLocaleString("en-US");
