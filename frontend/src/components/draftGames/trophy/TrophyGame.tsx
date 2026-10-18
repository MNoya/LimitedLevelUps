import { useEffect, useState } from "react";
import { ChevronLeft } from "lucide-react";

import { SetGlyph } from "../../Brand";
import { LuScrollText } from "../../Icons";
import { podDraftLogHref } from "../../pod/podLinks";
import { cn } from "../../../lib/utils";
import { shortDayLabel, useWheelSets, type RoundMark } from "../../../data/draftGames";
import {
  ALL_RECORDS,
  EMPTY_CALLS,
  scoreTrophyRound,
  TROPHY_FREE_PLAY_LABEL,
  TROPHY_RECORD,
  trophyMark,
  type TrophyCalls,
  type TrophyMageDeck,
  type TrophyMageRound,
  type TrophyRecord,
  type TrophyScore,
} from "../../../data/trophyMage";
import {
  ACCENT_BUTTON,
  DARK_PIXEL_BUTTON,
  HARD_TEXT_SHADOW,
  PIXEL_HEADING,
  PIXEL_PANEL,
  WAITING_PIXEL_BUTTON,
} from "../pixelStyles";
import { DeckTile, type DeckReveal } from "./DeckTile";
import { RecordText } from "./RecordChip";
import { useTrophyDay } from "./useTrophyDay";

const REVEAL_STEP_MS = 260;
const MARK_FILL: Record<RoundMark, string> = {
  hit: "bg-green text-[#0b1a10]",
  close: "bg-[#f6c95e] text-[#1a120b]",
  miss: "bg-red text-[#1a0b0b]",
};

export function TrophyGame({
  rounds,
  dayKey,
  storageKey,
  exhausted = false,
  onExit,
  onHelp,
  onAdvance,
  startAt = null,
}: {
  rounds: TrophyMageRound[];
  dayKey: string | null;
  storageKey: string | null;
  exhausted?: boolean;
  onExit: () => void;
  onHelp: () => void;
  onAdvance?: (index: number) => void;
  startAt?: number | null;
}) {
  const { day, setDraft, lockIn, goTo, advance, finish } = useTrophyDay(storageKey, rounds, startAt);
  const { sets } = useWheelSets();
  const [freshReveal, setFreshReveal] = useState(false);
  const [focusIndex, setFocusIndex] = useState(0);
  const featured = dayKey != null;
  const finished = featured && day.advanced >= rounds.length;
  const viewIndex = Math.min(day.current, rounds.length - 1);
  const round: TrophyMageRound | undefined = rounds[viewIndex];
  const locked = round ? day.locked[round.eventId] : undefined;
  const calls = locked ?? (round ? (day.drafts[round.eventId] ?? EMPTY_CALLS) : EMPTY_CALLS);
  const score = round && locked ? scoreTrophyRound(round, locked) : null;
  const nextOpen = featured ? nextUnplayedRound(rounds, day.locked, viewIndex) : null;
  const setName = (code: string) => sets.find((set) => set.code === code)?.name ?? code;
  const ready = round != null && round.decks.every((deck) => callFor(calls, deck) != null) && calls.crown != null;

  const pick = (record: TrophyRecord) => {
    const deck = round?.decks[focusIndex];
    if (!round || !deck || locked) {
      return;
    }
    const next = assign(calls, deck.key, callFor(calls, deck) === record ? null : record);
    setDraft(round.eventId, next);
    const open = nextOpenDeck(round.decks, next, focusIndex);
    if (open != null) {
      setFocusIndex(open);
    }
  };
  const confirm = () => {
    if (!round || locked || !ready) {
      return;
    }
    lockIn(round.eventId, calls);
    setFreshReveal(true);
    setFocusIndex(
      Math.max(
        0,
        round.decks.findIndex((deck) => deck.record === TROPHY_RECORD),
      ),
    );
  };
  const next = () => {
    setFreshReveal(false);
    setFocusIndex(0);
    if (!featured) {
      advance();
      onAdvance?.(day.advanced + 1);
    } else if (nextOpen == null) {
      finish();
    } else {
      goTo(nextOpen);
    }
  };
  const selectRound = (index: number) => {
    setFreshReveal(false);
    setFocusIndex(0);
    goTo(index);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!round || document.querySelector('[role="dialog"]') || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        if (locked) {
          next();
        } else {
          confirm();
        }
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        const delta = event.key === "ArrowLeft" ? -1 : 1;
        setFocusIndex((index) => (index + delta + round.decks.length) % round.decks.length);
      }
      const recordIndex = Number(event.key) - 1;
      if (recordIndex >= 0 && recordIndex < ALL_RECORDS.length) {
        pick(ALL_RECORDS[recordIndex]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (finished) {
    return <TrophySummary rounds={rounds} lockedCalls={day.locked} setName={setName} onExit={onExit} />;
  }
  if (!round) {
    return (
      <div className={cn(PIXEL_PANEL, "mx-auto mt-10 max-w-md p-6 text-center text-lg")}>
        {exhausted ? "Every Pod in this set is played" : "Loading Pods"}
        <button onClick={onExit} className={cn(DARK_PIXEL_BUTTON, "mt-4 px-4 py-2 text-lg")}>
          Menu
        </button>
      </div>
    );
  }

  const decks = round.decks;
  const focused = decks[Math.min(focusIndex, decks.length - 1)];
  const trophyDeck = decks.find((deck) => deck.record === TROPHY_RECORD);
  const revealFor = (deck: TrophyMageDeck): DeckReveal | null => {
    if (!locked) {
      return null;
    }
    const isTrophy = deck.record === TROPHY_RECORD;
    const others = decks.filter((d) => d.record !== TROPHY_RECORD);
    const delayMs = isTrophy ? others.length * REVEAL_STEP_MS + 300 : others.indexOf(deck) * REVEAL_STEP_MS;
    return { crowned: locked.crown === deck.key, delayMs: freshReveal ? delayMs : 0 };
  };
  const thumb = (deck: TrophyMageDeck) => (
    <DeckTile
      key={deck.key}
      deck={deck}
      name={`Deck ${decks.indexOf(deck) + 1}`}
      eventId={round.eventId}
      eventSlug={round.eventSlug}
      call={callFor(calls, deck)}
      reveal={revealFor(deck)}
      compact
      selected={deck === focused}
      onActivate={() => setFocusIndex(decks.indexOf(deck))}
      className="min-h-0 flex-1"
    />
  );
  const recordPicker = locked ? undefined : (
    <div className="flex gap-2">
      {ALL_RECORDS.map((record) => (
        <RecordButton
          key={record}
          record={record}
          active={callFor(calls, focused) === record}
          onClick={() => pick(record)}
        />
      ))}
    </div>
  );
  const draftHref =
    locked && trophyDeck
      ? podDraftLogHref(round.eventSlug, { playerSlug: trophyDeck.playerSlug, seatIndex: trophyDeck.seatIndex })
      : undefined;
  const action = locked ? (
    <button
      key="next"
      onClick={next}
      className={cn(ACCENT_BUTTON, "animate-fadeUpIn px-6 py-3 text-2xl")}
      style={{ animationDelay: freshReveal ? "900ms" : "0ms" }}
    >
      {featured && nextOpen == null ? "Today's Score" : "Next Pod"}
    </button>
  ) : (
    <button
      key={ready ? "ready" : "waiting"}
      onClick={confirm}
      disabled={!ready}
      className={cn(ready ? ACCENT_BUTTON : WAITING_PIXEL_BUTTON, "px-6 py-3 text-2xl")}
    >
      Confirm
    </button>
  );
  const helpButton = (
    <button onClick={onHelp} aria-label="How to Play" className={cn(DARK_PIXEL_BUTTON, "size-10 shrink-0 text-xl")}>
      ?
    </button>
  );
  const draftLogLink = draftHref && (
    <a
      href={draftHref}
      target="_blank"
      rel="noopener"
      aria-label="Draft Log"
      className={cn(DARK_PIXEL_BUTTON, "h-10 shrink-0 px-3 text-lg max-sm:w-10 max-sm:px-0")}
    >
      <LuScrollText size={18} aria-hidden="true" />
      <span className="max-sm:hidden">Draft Log</span>
    </a>
  );
  const roundInfo = (
    <RoundInfo
      setCode={round.setCode}
      title={featured ? `${setName(round.setCode)} #${viewIndex + 1}` : setName(round.setCode)}
      subtitle={featured && dayKey ? shortDayLabel(dayKey) : TROPHY_FREE_PLAY_LABEL}
      steps={
        featured
          ? rounds.map((r) => (day.locked[r.eventId] ? trophyMark(scoreTrophyRound(r, day.locked[r.eventId])) : null))
          : null
      }
      current={viewIndex}
      freePoints={featured ? null : freePlayPoints(rounds, day.locked)}
      onSelect={selectRound}
      onExit={onExit}
    />
  );

  return (
    <div className="flex h-[calc(100dvh-8.5rem)] gap-4 max-lg:h-[calc(100dvh-5rem)] max-lg:flex-col max-lg:gap-2">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {decks.map((deck, i) => (
          <DeckTile
            key={deck.key}
            deck={deck}
            name={`Deck ${i + 1}`}
            eventId={round.eventId}
            eventSlug={round.eventSlug}
            call={callFor(calls, deck)}
            reveal={revealFor(deck)}
            overlay={recordPicker}
            className={deck === focused ? "min-h-0 flex-1" : "hidden"}
          />
        ))}
      </div>
      <div className={cn(PIXEL_PANEL, "flex shrink-0 flex-col gap-2 p-2 lg:hidden")}>
        <div className="grid h-20 grid-cols-3 gap-2">{decks.map(thumb)}</div>
        <div className="flex items-center gap-2">
          {roundInfo}
          {draftLogLink}
          {helpButton}
        </div>
        {score && <RoundScore score={score} />}
        <div className="flex [&>button]:w-full">{action}</div>
      </div>
      <aside className={cn(PIXEL_PANEL, "flex w-[340px] shrink-0 flex-col gap-3 p-3 max-lg:hidden")}>
        <div className="flex items-center gap-2">
          {roundInfo}
          {helpButton}
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          {decks.map((deck) => (
            <div key={deck.key} className="flex min-h-0 flex-1 flex-col">
              {thumb(deck)}
            </div>
          ))}
        </div>
        {score && <RoundScore score={score} />}
        <div className="flex flex-col gap-2 [&>*]:w-full">
          {draftLogLink}
          {action}
        </div>
      </aside>
    </div>
  );
}

function RoundInfo({
  setCode,
  title,
  subtitle,
  steps,
  current,
  freePoints,
  onSelect,
  onExit,
}: {
  setCode: string;
  title: string;
  subtitle: string;
  steps: (RoundMark | null)[] | null;
  current: number;
  freePoints: number | null;
  onSelect: (index: number) => void;
  onExit: () => void;
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3">
      <button onClick={onExit} aria-label="Menu" className={cn(DARK_PIXEL_BUTTON, "size-10 shrink-0")}>
        <ChevronLeft size={20} strokeWidth={3} />
      </button>
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <SetGlyph code={setCode} size={20} className="shrink-0 text-[#fff1d6]" />
          <span className={cn("truncate font-display text-xl leading-none text-text", HARD_TEXT_SHADOW)}>{title}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={cn("mr-1 text-base max-sm:hidden", PIXEL_HEADING)}>{subtitle}</span>
          {steps?.map((mark, i) => (
            <button
              key={i}
              onClick={() => onSelect(i)}
              aria-label={`Pod ${i + 1}`}
              className={cn(
                "grid size-6 place-items-center border-2 border-[color:var(--px-ink)] pt-0.5 font-display text-sm",
                "shadow-[2px_2px_0_#05070a]",
                mark ? MARK_FILL[mark] : "bg-[#2b3445] text-subtle",
                i === current && "outline outline-2 outline-offset-1 outline-[color:var(--px-accent)]",
              )}
            >
              {i + 1}
            </button>
          ))}
          {freePoints != null && (
            <span className="font-display text-lg leading-none text-text">{freePoints} Points</span>
          )}
        </div>
      </div>
    </div>
  );
}

function RecordButton({ record, active, onClick }: { record: TrophyRecord; active: boolean; onClick: () => void }) {
  const activeFill =
    record === TROPHY_RECORD
      ? "bg-[linear-gradient(180deg,#fff3cf,#f6c95e_45%,#cf8e2c)] text-[#1a120b]"
      : "bg-[color:var(--px-accent)] text-[color:var(--px-ink)]";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex min-w-16 items-center justify-center gap-1.5 border-[3px] border-[color:var(--px-ink)] px-3 pt-2 pb-1.5",
        "font-display text-2xl leading-none shadow-[3px_3px_0_#05070a] transition-transform active:translate-y-0.5",
        "max-sm:min-w-[4.25rem]",
        active ? activeFill : "bg-[#2b3445] text-text hover:brightness-125",
      )}
    >
      <RecordText record={record} />
    </button>
  );
}

function RoundScore({ score }: { score: TrophyScore }) {
  return (
    <div className="flex w-full items-center justify-center gap-4 animate-fadeUpIn lg:justify-between">
      <span className={cn("text-2xl", PIXEL_HEADING)}>{score.crowned ? "Trophy Found" : "Trophy Missed"}</span>
      <span className="font-display text-2xl leading-none text-text">
        {score.points}
        <span className="text-lg text-subtle"> of {score.max} Points</span>
      </span>
    </div>
  );
}

function TrophySummary({
  rounds,
  lockedCalls,
  setName,
  onExit,
}: {
  rounds: TrophyMageRound[];
  lockedCalls: Record<string, TrophyCalls>;
  setName: (code: string) => string;
  onExit: () => void;
}) {
  let points = 0;
  let max = 0;
  const rows = rounds.map((round, i) => {
    const score = scoreTrophyRound(round, lockedCalls[round.eventId] ?? EMPTY_CALLS);
    points += score.points;
    max += score.max;
    return { round, score, label: `${setName(round.setCode)} #${i + 1}` };
  });
  return (
    <div className={cn(PIXEL_PANEL, "mx-auto mt-6 flex max-w-lg flex-col gap-4 p-6")}>
      <h2 className={cn("text-3xl", PIXEL_HEADING)}>Today's Score</h2>
      <div className="font-display text-5xl leading-none text-text">
        {points}
        <span className="text-2xl text-subtle"> of {max}</span>
      </div>
      <ul className="flex flex-col gap-2">
        {rows.map(({ round, score, label }) => (
          <li key={round.eventId} className="flex items-center justify-between text-lg">
            <span>{label}</span>
            <span className={cn("font-display text-xl", score.crowned ? "text-green" : "text-red")}>
              {score.points} of {score.max}
            </span>
          </li>
        ))}
      </ul>
      <button onClick={onExit} className={cn(ACCENT_BUTTON, "px-6 py-3 text-2xl")}>
        Menu
      </button>
    </div>
  );
}

function callFor(calls: TrophyCalls, deck: TrophyMageDeck): TrophyRecord | null {
  if (calls.crown === deck.key) {
    return TROPHY_RECORD;
  }
  return calls.records[deck.key] ?? null;
}

function assign(calls: TrophyCalls, deckKey: string, record: TrophyRecord | null): TrophyCalls {
  const records = { ...calls.records };
  delete records[deckKey];
  let crown = calls.crown === deckKey ? null : calls.crown;
  if (record === TROPHY_RECORD) {
    crown = deckKey;
  } else if (record) {
    records[deckKey] = record;
  }
  return { crown, records };
}

function nextOpenDeck(decks: TrophyMageDeck[], calls: TrophyCalls, from: number): number | null {
  for (let step = 1; step < decks.length; step++) {
    const index = (from + step) % decks.length;
    if (callFor(calls, decks[index]) == null) {
      return index;
    }
  }
  return null;
}

function nextUnplayedRound(
  rounds: TrophyMageRound[],
  locked: Record<string, TrophyCalls>,
  current: number,
): number | null {
  for (let step = 1; step < rounds.length; step++) {
    const index = (current + step) % rounds.length;
    if (!locked[rounds[index].eventId]) {
      return index;
    }
  }
  return null;
}

function freePlayPoints(rounds: TrophyMageRound[], locked: Record<string, TrophyCalls>): number {
  let points = 0;
  for (const round of rounds) {
    if (locked[round.eventId]) {
      points += scoreTrophyRound(round, locked[round.eventId]).points;
    }
  }
  return points;
}
