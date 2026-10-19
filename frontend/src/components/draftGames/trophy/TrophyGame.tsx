import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { ChevronLeft, Play, Trophy } from "lucide-react";

import { SetGlyph } from "../../Brand";
import { LuScrollText } from "../../Icons";
import { Pips } from "../../ManaPips";
import { podDraftLogHref } from "../../pod/podLinks";
import { cn } from "../../../lib/utils";
import { setShortLabel, useWheelSets } from "../../../data/draftGames";
import {
  EMPTY_CALLS,
  ALL_RECORDS,
  callFor,
  scoreTrophyRound,
  TROPHY_RECORD,
  type TrophyCalls,
  type TrophyMageDeck,
  type TrophyMageRound,
  type TrophyRecord,
  type TrophyScore,
} from "../../../data/trophyMage";
import { ACCENT_BUTTON, DARK_PIXEL_BUTTON, HARD_TEXT_SHADOW, PIXEL_PANEL } from "../pixelStyles";
import { SpaceKey } from "../wheel/SpaceKey";
import { DeckCard, type DeckFrame } from "./DeckCard";
import { DeckViewer } from "./DeckViewer";
import { SCORE_LABEL, TrophyRecap } from "./TrophyRecap";
import { TrophyLoading, TrophyNotice } from "./introParts";
import { CallTag, ResultTag } from "./RecordChip";
import { useDeckImage } from "./useDeckImage";
import { useTrophyDay } from "./useTrophyDay";

type Outcome = "found" | "missed";

const FIRST_FLIP_MS = 350;
const FLIP_MS = 500;
const INPUT_PAUSE_MS = 600;
const DOUBLE_TAP_MS = 300;
const PRIMARY = "primary";
const REVIEW_BACK_LABEL = "Back";
const NEXT_POD_LABEL = "Next";
const OUTCOME_FILL: Record<Outcome, string> = {
  found: "bg-[linear-gradient(180deg,#fff3cf,#f6c95e_45%,#cf8e2c)] text-[#1a120b]",
  missed: "bg-[#8a94a8] text-[#0b1430]",
};
const OUTCOME_TEXT: Record<Outcome, string> = { found: "text-[#f6c95e]", missed: "text-[#aab3c5]" };
const WAITING_BUTTON = cn(ACCENT_BUTTON, "pointer-events-none opacity-40 saturate-50");

interface RoundInfo {
  title: string;
  setCodes: string[];
  outcomes: (Outcome | null)[] | null;
  current: number;
  freePoints: number | null;
  onSelect: (index: number) => void;
  onExit: () => void;
  onHelp: () => void;
}

export function TrophyGame({
  rounds,
  dayKey,
  storageKey,
  exhausted = false,
  onExit,
  onHelp,
  onAdvance,
  onPlayDay,
  onPlaySet,
  onDayDone,
  onReview,
  onEndReview,
  startAt = null,
  reviewIndex = null,
  showResults = false,
}: {
  rounds: TrophyMageRound[];
  dayKey: string | null;
  storageKey: string | null;
  exhausted?: boolean;
  onExit: () => void;
  onHelp: () => void;
  onAdvance?: (index: number) => void;
  onPlayDay?: (dayKey: string) => void;
  onPlaySet?: (setCode: string) => void;
  onDayDone?: () => void;
  onReview?: (index: number, replace?: boolean) => void;
  onEndReview?: () => void;
  startAt?: number | null;
  reviewIndex?: number | null;
  showResults?: boolean;
}) {
  const { day, setDraft, lockIn, goTo, advance, finish } = useTrophyDay(storageKey, rounds, startAt);
  const { sets } = useWheelSets();
  const featured = dayKey != null;
  const finished = featured && day.advanced >= rounds.length;
  const reviewing = finished && reviewIndex != null && rounds[reviewIndex] != null;
  const viewIndex = reviewing ? reviewIndex : Math.min(day.current, rounds.length - 1);
  const round: TrophyMageRound | undefined = rounds[viewIndex];
  const setName = (code: string) => {
    const shortNames: Record<string, string> = { MSH: "Marvel", SOS: "Strixhaven" };
    return shortNames[code] ?? sets.find((set) => set.code === code)?.name ?? code;
  };
  const [finishedNow, setFinishedNow] = useState(false);
  const endsOnHome = finished && !reviewing && finishedNow && !showResults;
  const review = (index: number) => onReview?.(index);

  useEffect(() => {
    if (endsOnHome) {
      onDayDone?.();
    }
  }, [endsOnHome, onDayDone]);

  if (endsOnHome) {
    return null;
  }
  if (finished && !reviewing) {
    return (
      <TrophyRecap
        rounds={rounds}
        day={day}
        dayKey={dayKey}
        onReview={review}
        onPlayDay={onPlayDay}
        onPlaySet={onPlaySet}
        onExit={onExit}
      />
    );
  }
  if (!round) {
    return exhausted ? <TrophyNotice label="Every Pod in this set is played" onExit={onExit} /> : <TrophyLoading />;
  }

  const nextOpen = featured ? nextUnplayedRound(rounds, day.locked, viewIndex) : null;
  let nextLabel = NEXT_POD_LABEL;
  if (reviewing) {
    nextLabel = REVIEW_BACK_LABEL;
  } else if (featured && nextOpen == null) {
    nextLabel = SCORE_LABEL;
  }
  const upcoming = featured ? (nextOpen == null ? undefined : rounds[nextOpen]) : rounds[viewIndex + 1];
  const next = () => {
    if (reviewing) {
      onEndReview?.();
    } else if (!featured) {
      advance();
      onAdvance?.(day.advanced + 1);
    } else if (nextOpen == null) {
      finish();
      setFinishedNow(true);
    } else {
      goTo(nextOpen);
    }
  };
  const info: RoundInfo = {
    title: setName(round.setCode),
    setCodes: rounds.map((r) => r.setCode),
    outcomes: featured ? rounds.map((r) => outcomeFor(r, day.locked[r.eventId])) : null,
    current: viewIndex,
    freePoints: featured ? null : freePlayPoints(rounds, day.locked, round.eventId),
    onSelect: reviewing ? (index) => onReview?.(index, true) : goTo,
    onExit,
    onHelp,
  };

  return (
    <>
      <RoundView
        key={round.eventId}
        round={round}
        calls={day.locked[round.eventId] ?? day.drafts[round.eventId] ?? EMPTY_CALLS}
        locked={day.locked[round.eventId] != null}
        onDraft={(calls) => setDraft(round.eventId, calls)}
        onLock={(calls) => lockIn(round.eventId, calls)}
        onNext={next}
        nextLabel={nextLabel}
        info={info}
      />
      {upcoming && <PreloadRound round={upcoming} />}
    </>
  );
}

function RoundView({
  round,
  calls,
  locked,
  onDraft,
  onLock,
  onNext,
  nextLabel,
  info,
}: {
  round: TrophyMageRound;
  calls: TrophyCalls;
  locked: boolean;
  onDraft: (calls: TrophyCalls) => void;
  onLock: (calls: TrophyCalls) => void;
  onNext: () => void;
  nextLabel: string;
  info: RoundInfo;
}) {
  const decks = round.decks;
  const trophyDeck = decks.find((deck) => deck.record === TROPHY_RECORD) ?? decks[0];
  const [flipped, setFlipped] = useState(locked ? decks.length : 0);
  const [loaded, setLoaded] = useState<Set<string>>(() => new Set());
  const [viewing, setViewing] = useState<number | null>(null);
  const pausedUntil = useRef(0);
  const lastTap = useRef({ control: "", at: 0 });
  const revealDone = locked && flipped >= decks.length;
  const decksReady = locked || decks.every((deck) => loaded.has(deck.key));
  const score = scoreTrophyRound(round, calls);
  const outcome: Outcome = score.crowned ? "found" : "missed";

  useEffect(() => {
    if (revealDone) {
      pausedUntil.current = performance.now() + INPUT_PAUSE_MS;
    }
  }, [revealDone]);

  useEffect(() => {
    if (!locked || flipped >= decks.length) {
      return;
    }
    const timer = window.setTimeout(() => setFlipped((count) => count + 1), flipped === 0 ? FIRST_FLIP_MS : FLIP_MS);
    return () => window.clearTimeout(timer);
  }, [locked, flipped, decks.length]);

  const markLoaded = useCallback(
    (key: string) => setLoaded((current) => (current.has(key) ? current : new Set(current).add(key))),
    [],
  );
  const repeatedTap = (control: string) => {
    const now = performance.now();
    const repeated = lastTap.current.control === control && now - lastTap.current.at < DOUBLE_TAP_MS;
    lastTap.current = { control, at: now };
    return repeated || (control === PRIMARY && now < pausedUntil.current);
  };
  const pickCrown = (deck: TrophyMageDeck) => {
    if (!locked && decksReady && calls.crown !== deck.key && !repeatedTap(deck.key)) {
      onDraft(assign(calls, deck.key, TROPHY_RECORD));
    }
  };
  const place = (deck: TrophyMageDeck, record: TrophyRecord) => {
    if (!repeatedTap(deck.key)) {
      onDraft(assign(calls, deck.key, callFor(calls, deck) === record ? null : record));
    }
  };
  const look = (index: number) => {
    if ((!locked || revealDone) && !repeatedTap(PRIMARY)) {
      setViewing(index);
    }
  };
  const primary = () => {
    if (repeatedTap(PRIMARY)) {
      return;
    }
    if (!locked) {
      if (calls.crown) {
        setViewing(null);
        onLock(calls);
      }
    } else if (revealDone) {
      onNext();
    } else {
      setFlipped(decks.length);
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.repeat || event.metaKey || event.ctrlKey || event.altKey || document.querySelector('[role="dialog"]')) {
        return;
      }
      const focused = document.activeElement;
      const typing = focused?.matches("input, textarea, select") ?? false;
      const keyboardFocus = focused?.matches("a:focus-visible, button:focus-visible") ?? false;
      if (typing || keyboardFocus) {
        return;
      }
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        primary();
        return;
      }
      pickByKey(event.key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function pickByKey(key: string) {
    const deck = decks[Number(key) - 1];
    if (deck) {
      pickCrown(deck);
    }
  }
  const flippedDeck = (deck: TrophyMageDeck) => locked && decks.indexOf(deck) < flipped;
  const deckFrame = (deck: TrophyMageDeck): DeckFrame => {
    if (deck === trophyDeck && flippedDeck(deck)) {
      return calls.crown === deck.key ? "crowned" : "trophy";
    }
    return calls.crown === deck.key && !flippedDeck(deck) ? "picked" : "idle";
  };
  const deckFooter = (deck: TrophyMageDeck): ReactNode => {
    const call = callFor(calls, deck);
    if (locked) {
      if (flippedDeck(deck)) {
        return <ResultTag call={call} actual={deck.record} className="text-lg lg:text-2xl" />;
      }
      return call ? <CallTag record={call} className="text-lg lg:text-2xl" /> : null;
    }
    if (!hasCalls) {
      return (
        <button
          type="button"
          onClick={() => pickCrown(deck)}
          disabled={!decksReady}
          className={cn(
            decksReady ? DARK_PIXEL_BUTTON : WAITING_BUTTON,
            "h-9 px-3 text-lg shadow-[4px_4px_0_#05070a] hover:shadow-[5px_6px_0_#05070a] lg:h-11 lg:text-xl",
            decksReady && "group-hover/bar:-translate-y-0.5 group-hover/bar:shadow-[5px_6px_0_#05070a]",
            decksReady && "group-hover/bar:brightness-110",
            decksReady && "hover:text-[color:var(--px-accent)] group-hover/bar:text-[color:var(--px-accent)]",
          )}
        >
          <Trophy size={16} strokeWidth={2.5} />
          Pick This Deck
        </button>
      );
    }
    return ALL_RECORDS.map((record) => (
      <RecordButton
        key={record}
        record={record}
        active={call === record}
        beckon={call == null && record !== TROPHY_RECORD}
        onClick={() => place(deck, record)}
      />
    ));
  };

  const hasCalls = calls.crown != null || Object.keys(calls.records).length > 0;
  const allPlaced = decks.every((deck) => callFor(calls, deck) != null);
  let actionLabel = "Confirm";
  let actionStyle = allPlaced ? ACCENT_BUTTON : cn(ACCENT_BUTTON, "bg-[linear-gradient(180deg,#b9d9e6,#6fa9c4)]");
  if (locked) {
    actionLabel = nextLabel;
    actionStyle = ACCENT_BUTTON;
  }
  const actionButton = (locked ? revealDone : calls.crown != null) && (
    <button
      key={actionLabel}
      onClick={primary}
      className={cn(actionStyle, "px-5 py-3 text-2xl animate-fadeUpIn lg:h-14 lg:gap-4 lg:py-0 lg:pr-2.5")}
    >
      {actionLabel === NEXT_POD_LABEL && <Play size={20} className="fill-current" />}
      {actionLabel}
      <SpaceKey />
    </button>
  );
  const outcomes = info.outcomes?.map((value, i) => (i === info.current && !revealDone ? null : value)) ?? null;
  const total = info.freePoints == null ? null : info.freePoints + score.points;
  const headerInfo: RoundInfo = { ...info, outcomes };
  const draftLog = (
    <a
      href={podDraftLogHref(round.eventSlug, { playerSlug: trophyDeck.playerSlug, seatIndex: trophyDeck.seatIndex })}
      target="_blank"
      rel="noopener"
      className={cn(DARK_PIXEL_BUTTON, "h-8 shrink-0 px-2.5 text-base max-sm:w-8 max-sm:px-0 lg:h-10 lg:text-lg")}
    >
      <LuScrollText size={16} aria-hidden="true" />
      <span className="max-sm:hidden">Draft Log</span>
    </a>
  );
  const status = revealDone ? (
    <RoundResult score={score} outcome={outcome} total={total} />
  ) : (
    <RoundPrompt
      locked={locked}
      crownPicked={calls.crown != null}
      allPlaced={allPlaced}
      unplaced={decks.filter((deck) => callFor(calls, deck) == null).length}
      decksReady={decksReady}
    />
  );

  return (
    <div
      onClick={(event) => {
        if (event.detail > 0) {
          (document.activeElement as HTMLElement | null)?.blur();
        }
      }}
      className={cn(
        "flex h-[calc(100dvh-5rem)] flex-col gap-2",
        "lg:grid lg:h-[calc(100dvh-8.5rem)] lg:grid-cols-3 lg:grid-rows-[1fr_auto_1fr] lg:gap-4 lg:pb-[4.5rem]",
        "lg:mx-[calc(50%-50vw+1rem)]",
      )}
    >
      {decks.map((deck, i) => (
        <DeckCard
          key={deck.key}
          deck={deck}
          name={`Deck ${i + 1}`}
          eventId={round.eventId}
          frame={deckFrame(deck)}
          footer={deckFooter(deck)}
          onLook={() => look(i)}
          onReady={() => markLoaded(deck.key)}
          className="max-lg:flex-1 lg:row-start-2"
          imageClassName="lg:aspect-[2/1] lg:flex-none"
          footerEnd={deck === trophyDeck && flippedDeck(deck) ? draftLog : undefined}
          banner={deck === trophyDeck && flippedDeck(deck) ? <PlayerLabel name={deck.displayName} /> : undefined}
          onBarClick={!locked && !hasCalls && decksReady ? () => pickCrown(deck) : undefined}
        />
      ))}
      <section className={cn(PIXEL_PANEL, "flex shrink-0 flex-col gap-2.5 p-2.5 lg:hidden")}>
        <div className="relative flex items-center justify-between gap-2.5">
          <span className="flex items-center gap-2.5">
            <RoundMenu info={headerInfo} />
          </span>
          <RoundName info={headerInfo} className="pointer-events-none flex-1 items-center" />
          <RoundTiles info={headerInfo} />
        </div>
        <div className="flex min-h-[3.875rem] items-center justify-center gap-3">
          {revealDone ? (
            <div className="grid w-full grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 animate-fadeUpIn">
              <RoundPoints score={score} total={total} className="flex-col items-center gap-1" />
              <RoundOutcome outcome={outcome} />
              <div className="flex justify-end [&>button]:px-4">{actionButton}</div>
            </div>
          ) : (
            <div className="flex w-full justify-center text-center [&>button]:w-full [&>button]:max-w-72">
              {actionButton || status}
            </div>
          )}
        </div>
      </section>
      <section
        className={cn(
          PIXEL_PANEL,
          "col-span-full row-start-3 grid min-h-[5.5rem] grid-cols-3 items-center gap-4 self-center py-3",
          "max-lg:hidden",
        )}
      >
        <div className="relative flex h-full items-center gap-4 pl-5 [container-type:inline-size]">
          <RoundMenu info={headerInfo} />
          {headerInfo.outcomes ? (
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
              <RoundTiles info={headerInfo} />
              <RoundName
                info={headerInfo}
                className="absolute top-1/2 left-full ml-5 w-max max-w-[calc(50cqw-5.5rem)] -translate-y-1/2"
              />
            </div>
          ) : (
            <RoundName info={headerInfo} className="flex-1 items-center pr-5" />
          )}
        </div>
        <div className="flex justify-center text-center [&>button]:min-w-48">{actionButton || status}</div>
        <div className="flex justify-center">{revealDone && status}</div>
      </section>
      {viewing != null && (
        <DeckViewer
          decks={decks}
          index={viewing}
          eventId={round.eventId}
          footerFor={deckFooter}
          action={revealDone ? null : actionButton}
          onPickKey={pickByKey}
          onPrimary={revealDone ? () => setViewing(null) : primary}
          onIndex={setViewing}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  );
}

function RoundMenu({ info }: { info: RoundInfo }) {
  return (
    <>
      <button
        onClick={info.onExit}
        aria-label="Menu"
        className={cn(DARK_PIXEL_BUTTON, "h-10 shrink-0 pr-3 pl-2 text-lg max-sm:w-10 max-sm:px-0")}
      >
        <ChevronLeft size={18} strokeWidth={3} />
        <span className="max-sm:hidden">Menu</span>
      </button>
      <HelpButton onHelp={info.onHelp} />
    </>
  );
}

function RoundName({ info, className }: { info: RoundInfo; className?: string }) {
  const nameRef = useRef<HTMLSpanElement>(null);
  useFitToParentWidth(nameRef, info.title);
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span
        ref={nameRef}
        className={cn("whitespace-nowrap font-display text-xl leading-none text-text lg:text-3xl", HARD_TEXT_SHADOW)}
      >
        {info.title}
      </span>
    </div>
  );
}

function useFitToParentWidth(ref: RefObject<HTMLElement | null>, text: string) {
  useLayoutEffect(() => {
    const element = ref.current;
    const parent = element?.parentElement;
    if (!element || !parent) {
      return;
    }
    const minFontPx = 12;
    const fit = () => {
      element.style.fontSize = "";
      const naturalWidth = element.scrollWidth;
      const room = parent.clientWidth;
      if (naturalWidth > room && room > 0) {
        const baseFontPx = parseFloat(getComputedStyle(element).fontSize);
        element.style.fontSize = `${Math.max(minFontPx, (baseFontPx * room) / naturalWidth)}px`;
      }
    };
    fit();
    document.fonts.ready.then(fit);
    const observer = new ResizeObserver(fit);
    observer.observe(parent.parentElement ?? parent);
    window.addEventListener("resize", fit);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", fit);
    };
  }, [ref, text]);
}

function RoundTiles({ info }: { info: RoundInfo }) {
  return (
    <div className="flex shrink-0 items-center gap-1.5">
      {info.outcomes?.map((outcome, i) => (
        <button
          key={i}
          onClick={() => info.onSelect(i)}
          aria-label={`Pod ${i + 1}: ${setShortLabel(info.setCodes[i])}`}
          className={cn(
            "grid size-9 place-items-center border-2 border-[color:var(--px-ink)] lg:size-11",
            "shadow-[2px_2px_0_#05070a]",
            outcome ? OUTCOME_FILL[outcome] : "border-dashed border-[#4a5a78] bg-transparent text-[#fff1d6]",
            i === info.current && "border-[#9ff3ff]",
          )}
        >
          <SetGlyph code={info.setCodes[i]} size={20} className={outcome ? "text-[#0b1430]" : undefined} />
        </button>
      ))}
    </div>
  );
}

function HelpButton({ onHelp, className }: { onHelp: () => void; className?: string }) {
  return (
    <button
      onClick={onHelp}
      aria-label="How to Play"
      className={cn(DARK_PIXEL_BUTTON, "size-10 shrink-0 text-xl", className)}
    >
      ?
    </button>
  );
}

function RoundPrompt({
  locked,
  crownPicked,
  allPlaced,
  unplaced,
  decksReady,
}: {
  locked: boolean;
  crownPicked: boolean;
  allPlaced: boolean;
  unplaced: number;
  decksReady: boolean;
}) {
  if (locked || allPlaced || !decksReady) {
    return null;
  }
  let heading = "Which deck went 3-0?";
  if (crownPicked) {
    heading = unplaced === 1 ? "Place the last deck" : "Place the other two";
  }
  return (
    <h2 className={cn("font-display text-3xl leading-none text-text max-lg:text-2xl xl:text-4xl", HARD_TEXT_SHADOW)}>
      {heading}
    </h2>
  );
}

function RoundResult({ score, outcome, total }: { score: TrophyScore; outcome: Outcome; total: number | null }) {
  return (
    <div className="flex items-baseline justify-between gap-4 animate-fadeUpIn">
      <RoundOutcome outcome={outcome} />
      <RoundPoints score={score} total={total} />
    </div>
  );
}

function RoundOutcome({ outcome }: { outcome: Outcome }) {
  return (
    <span className={cn("font-display text-2xl leading-none lg:text-3xl", HARD_TEXT_SHADOW, OUTCOME_TEXT[outcome])}>
      {outcome === "found" ? "Correct" : "Missed"}
    </span>
  );
}

function RoundPoints({ score, total, className }: { score: TrophyScore; total: number | null; className?: string }) {
  return (
    <span className={cn("flex items-baseline gap-4", className)}>
      <span className="font-display text-2xl leading-none text-text lg:text-3xl">
        {total == null ? score.points : `+${score.points}`}
        <span className="text-lg text-subtle lg:text-xl">
          {total == null ? ` of ${score.max} Points` : ` ${pointsWord(score.points)}`}
        </span>
      </span>
      {total != null && (
        <span className="font-display text-2xl leading-none text-text lg:text-3xl">
          {total}
          <span className="text-lg text-subtle lg:text-xl"> Total</span>
        </span>
      )}
    </span>
  );
}

function pointsWord(points: number): string {
  return points === 1 ? "Point" : "Points";
}

function PlayerLabel({ name }: { name: string }) {
  return (
    <span
      className={cn(
        "border-[3px] border-[color:var(--px-ink)] bg-[color:var(--px-panel)] px-3 py-1.5 whitespace-nowrap",
        "text-lg font-semibold text-text shadow-[3px_3px_0_#05070a] animate-fadeUpIn lg:text-xl",
      )}
    >
      {name}
    </span>
  );
}

function RecordButton({
  record,
  active,
  beckon,
  onClick,
}: {
  record: TrophyRecord;
  active: boolean;
  beckon: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "relative flex h-9 min-w-11 items-center justify-center border-2 border-[color:var(--px-ink)] px-2 pt-1",
        "font-display text-lg leading-none shadow-[2px_2px_0_#05070a] transition-transform active:translate-y-0.5",
        "lg:h-10 lg:min-w-14 lg:text-xl xl:h-11 xl:text-2xl 2xl:min-w-20",
        active
          ? "bg-[color:var(--px-accent)] text-[color:var(--px-ink)]"
          : "bg-[#2b3445] text-text hover:brightness-125",
      )}
    >
      {beckon && (
        <span className="pointer-events-none absolute -inset-0.5 animate-pulse border-2 border-[color:var(--px-accent)]" />
      )}
      {record}
    </button>
  );
}

function PreloadRound({ round }: { round: TrophyMageRound }) {
  return (
    <div aria-hidden className="hidden">
      {round.decks.map((deck) => (
        <PreloadDeck key={deck.key} deck={deck} eventId={round.eventId} />
      ))}
    </div>
  );
}

function PreloadDeck({ deck, eventId }: { deck: TrophyMageDeck; eventId: string }) {
  const { url } = useDeckImage(deck, eventId);
  return url ? <img src={url} alt="" /> : null;
}

function outcomeFor(round: TrophyMageRound, locked: TrophyCalls | undefined): Outcome | null {
  if (!locked) {
    return null;
  }
  return scoreTrophyRound(round, locked).crowned ? "found" : "missed";
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

function freePlayPoints(rounds: TrophyMageRound[], locked: Record<string, TrophyCalls>, current: string): number {
  let points = 0;
  for (const round of rounds) {
    if (round.eventId !== current && locked[round.eventId]) {
      points += scoreTrophyRound(round, locked[round.eventId]).points;
    }
  }
  return points;
}
