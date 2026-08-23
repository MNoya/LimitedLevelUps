import { Fragment, type ReactNode } from "react";
import { SLOTS } from "../../data/p0p1Slots";
import type { P0P1Phase } from "../../data/p0p1Results";

const SEVENTEEN_LANDS_URL = "https://www.17lands.com/card_data";

const winRateLink = (
  <a
    href={SEVENTEEN_LANDS_URL}
    target="_blank"
    rel="noreferrer"
    className="text-green hover:underline underline-offset-2"
  >
    17Lands GIH win rate
  </a>
);

const dataLink = (
  <a
    href={SEVENTEEN_LANDS_URL}
    target="_blank"
    rel="noreferrer"
    className="text-green hover:underline underline-offset-2"
  >
    17Lands data
  </a>
);

export function P0P1IntroText({
  setName: setNameProp,
  phase,
  dateRange,
  multiline = false,
}: {
  setName: string;
  phase: P0P1Phase;
  dateRange?: { start: string; end: string } | null;
  multiline?: boolean;
}) {
  const setName = <span className="font-semibold text-text">{setNameProp}</span>;
  const cardCount = spellOut(SLOTS.length);
  const formattedRange = dateRange ? formatDateRange(dateRange.start, dateRange.end) : null;

  const sentences: ReactNode[] = buildSentences(phase, setName, cardCount, formattedRange);

  return (
    <>
      {sentences.map((sentence, i) => (
        <Fragment key={i}>
          {i > 0 && (multiline ? <br /> : " ")}
          {sentence}
        </Fragment>
      ))}
    </>
  );
}

function buildSentences(
  phase: P0P1Phase,
  setName: ReactNode,
  cardCount: string,
  formattedRange: string | null,
): ReactNode[] {
  switch (phase) {
    case "loading":
      return [
        <span className="inline-block h-3.5 w-64 bg-surface2 animate-pulse align-middle" />,
        <span className="inline-block h-3.5 w-80 bg-surface2 animate-pulse align-middle" />,
      ];
    case "voting":
      return [
        <>Put together a team of {cardCount} cards from {setName}</>,
        <>Four weeks after voting, teams are ranked by their total {winRateLink}</>,
      ];
    case "postVoting":
      return [
        <>Participants have put in their predictions for {setName}</>,
        <>Check out the most popular picks below, then come back once they're ranked by {winRateLink}, four weeks after voting</>,
      ];
    case "midway":
      return [
        <>{setName} season is underway</>,
        <>Check out the <strong>preliminary data</strong> below {formattedRange && <> from {formattedRange}</>}</>,
        <>Final results coming soon</>
      ];
    case "final":
      return [
        <>After four weeks, {setName} results are in!</>,
        <>Check out the final standings based on {dataLink}</>,
      ];
  }
}

const NUMBER_WORDS = [
  "zero", "one", "two", "three", "four", "five", "six", "seven",
  "eight", "nine", "ten", "eleven", "twelve",
];

function spellOut(n: number): string {
  return NUMBER_WORDS[n] ?? String(n);
}

function formatDateRange(start: string, end: string): string {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${fmt(s)} – ${fmt(e)}`;
}
