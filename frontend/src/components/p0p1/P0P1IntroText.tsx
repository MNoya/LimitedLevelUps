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
  votingDeadline,
  scoringDate,
  phase,
  dateRange,
  multiline = false,
}: {
  setName: string;
  votingDeadline: Date;
  scoringDate: Date;
  phase: P0P1Phase;
  dateRange?: { start: string; end: string } | null;
  multiline?: boolean;
}) {
  const setName = <span className="font-semibold text-text">{setNameProp}</span>;
  const cardCount = spellOut(SLOTS.length);
  const windowText = describeDuration(scoringDate.getTime() - votingDeadline.getTime());
  const formattedRange = dateRange ? formatDateRange(dateRange.start, dateRange.end) : null;

  const sentences: ReactNode[] = buildSentences(phase, setName, cardCount, windowText, formattedRange);

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
  windowText: string,
  formattedRange: string | null,
): ReactNode[] {
  switch (phase) {
    case "voting":
      return [
        <>Put together a team of {cardCount} cards from {setName}.</>,
        <>{capitalize(windowText)} after release, teams are ranked by their total {winRateLink}.</>,
      ];
    case "postVoting":
      return [
        <>Participants have put in their predictions for {setName}.</>,
        <>Check out the most popular picks below, then come back once they're ranked by {winRateLink}, {windowText} after release.</>,
      ];
    case "midway":
      return [
        <>{setName} season is underway.</>,
        <>Check out the <strong>preliminary data</strong> below {formattedRange && <> from {formattedRange}</>}.</>,
        <>Final results coming soon.</>
      ];
    case "finalizing":
      return [
        <>{capitalize(windowText)} of {setName} drafts are in the books.</>,
        <>Showing <strong>preliminary data</strong> below{formattedRange && <> from {formattedRange}</>}.</>,
        <>Final standings coming shortly.</>,
      ];
    case "final":
      return [
        <>After {windowText}, {setName} results are in!</>,
        <>Check out the final standings based on {dataLink}.</>,
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

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function describeDuration(ms: number): string {
  const days = Math.round(ms / (24 * 60 * 60 * 1000));
  if (days % 7 === 0) {
    const weeks = days / 7;
    return `${spellOut(weeks)} ${weeks === 1 ? "week" : "weeks"}`;
  }
  return `${spellOut(days)} ${days === 1 ? "day" : "days"}`;
}

function formatDateRange(start: string, end: string): string {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${fmt(s)} – ${fmt(e)}`;
}
