import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
import { useNavigate } from "react-router-dom";

import { Container } from "../components/Container";
import { PageShell } from "../components/PageShell";
import { CardImage, CardImageMapProvider } from "../components/pod/review/ReviewCard";
import { GOLD_BUTTON, PIXEL_HEADING, PIXEL_PANEL } from "../components/draftGames/pixelStyles";
import { CardTitle } from "../components/draftGames/wheel/CardTitle";
import {
  CardZoom,
  PickingCard,
  QuickRevealCard,
  ResultChip,
  revealOutcome,
} from "../components/draftGames/wheel/PackGrid";
import { releaseFocus, useGuideHash, useNoScrollGutter } from "../components/draftGames/wheel/pageHooks";
import { SpaceKey } from "../components/draftGames/wheel/SpaceKey";
import { WheelBackdrop } from "../components/draftGames/wheel/WheelBackdrop";
import { LoadingLabel } from "../components/draftGames/GameChrome";
import { WheelTitle } from "../components/draftGames/wheel/WheelTitle";
import { WheelHeader, type WheelProgress } from "../components/draftGames/wheel/WheelHeader";
import { WheelSetDropdown } from "../components/draftGames/wheel/WheelSetDropdown";
import {
  DIFFICULTY_LABEL,
  difficultyKey,
  QuickHelpDialog,
  type QuickDifficulty,
} from "../components/draftGames/wheel/WheelHelp";
import { useCardImageMap } from "../data/cardImages";
import {
  ALL_SETS_CODE,
  MINI_GAMES_HEADER,
  useFreePlayPacks,
  useWheelSets,
  type WheelPack,
  type WheelSetOption,
} from "../data/draftGames";
import { useCardStats, type CardStatsLookup } from "../data/tierList";
import { cn } from "../lib/utils";
import type { ArtifactCard } from "../types/leaderboard";

interface Candidate {
  card: number;
  pick: number | null;
}

interface PlayedRound {
  pack: WheelPack;
  candidates: Candidate[];
  card: number;
  right: boolean;
}

const HISTORY_ROWS = 8;
const PHONE_HISTORY = 6;
const CANDIDATE_DEAL_STEP_MS = 60;
const REST_DEAL_START_MS = 260;
const REST_DEAL_STEP_MS = 25;
const REST_GAP_PX = 8;
const PHONE_BOTTOM_GAP_PX = 12;
const CARD_ASPECT = 488 / 680;
const FILL_HEIGHT_TOLERANCE_PX = 4;
const DESKTOP_REST_SIZE = {
  "--rest-cols": "var(--rest-half)",
  "--rest-w": [
    "min(150px",
    "calc((100cqh * 0.25 - 16px) * 0.7176)",
    "calc((100cqw - (var(--rest-cols) - 1) * 8px) / var(--rest-cols) - 0.5px))",
  ].join(", "),
} as CSSProperties;
const BEST_STREAK_KEY = "wheel-of-fortune-quick-best";
const BAND_SIZE = 3;

export function WheelQuickPage() {
  useNoScrollGutter();
  const navigate = useNavigate();
  const [helpOpen, openHelp, closeHelp] = useGuideHash("quick-guide");
  const { sets } = useWheelSets();
  const [setCode, setSetCode] = useState<string | null>(null);
  const [difficulty, setDifficulty] = useState<QuickDifficulty>("easy");
  const activeSet = setCode ?? sets[0]?.code ?? null;
  const setName = (code: string) =>
    code === ALL_SETS_CODE ? "All Sets" : (sets.find((set) => set.code === code)?.name ?? code);
  return (
    <PageShell
      subtitle="WHEEL OF FORTUNE"
      titleHref="/wheel-of-fortune"
      subtitleShort={MINI_GAMES_HEADER}
      phoneTitle={<WheelTitle scale={2} interactive={false} />}
      footer={false}
    >
      <Container className="draft-game pt-3 pb-4 lg:px-4 2xl:px-10">
        <WheelBackdrop />
        <div className="relative z-[1]">
          {!activeSet && (
            <div className="flex flex-col gap-3 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(340px,456px)] lg:gap-x-4">
              <div className={cn(PIXEL_PANEL, "h-[74px] lg:hidden")} />
              <QuickLoading />
              <div className={cn(PIXEL_PANEL, "hidden lg:block lg:h-[calc(100dvh-125px)]")} />
            </div>
          )}
          {activeSet && (
            <QuickGame
              key={activeSet}
              setCode={activeSet}
              difficulty={difficulty}
              sets={sets}
              setName={setName}
              onDifficulty={setDifficulty}
              onSet={setSetCode}
              onHelp={openHelp}
              onExit={() => navigate("/wheel-of-fortune")}
            />
          )}
        </div>
      </Container>
      <QuickHelpDialog open={helpOpen} onClose={closeHelp} />
    </PageShell>
  );
}

function QuickGame({
  setCode,
  difficulty,
  sets,
  setName,
  onDifficulty,
  onSet,
  onHelp,
  onExit,
}: {
  setCode: string;
  difficulty: QuickDifficulty;
  sets: WheelSetOption[];
  setName: (code: string) => string;
  onDifficulty: (difficulty: QuickDifficulty) => void;
  onSet: (code: string) => void;
  onHelp: () => void;
  onExit: () => void;
}) {
  const [seed] = useState(() => Math.floor(Math.random() * 1_000_000));
  const [round, setRound] = useState(0);
  const [guess, setGuess] = useState<number | null>(null);
  const [history, setHistory] = useState<PlayedRound[]>([]);
  const [best, setBest] = useState(() => Number(localStorage.getItem(BEST_STREAK_KEY) ?? 0));
  const [zoom, setZoom] = useState<ArtifactCard | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);
  const { packs, isPending } = useFreePlayPacks(setCode, round + 2, seed);
  const pack = packs[round];
  const stats = useCardStats(pack?.setCode ?? setCode);
  const images = useCardImageMap(
    useMemo(() => packs.flatMap((p) => p.pack.map((i) => ({ name: p.cards[i].n, set: p.cards[i].s }))), [packs]),
  );
  const candidates = useMemo(() => (pack ? pickCandidates(pack, difficulty, stats) : []), [pack, difficulty, stats]);
  const viewed = viewing == null ? null : history[viewing];
  const shownPack = viewed ? viewed.pack : pack;
  const shownCandidates = viewed ? viewed.candidates : candidates;
  const shownGuess = viewed ? viewed.card : guess;
  const revealed = shownGuess != null;
  const streak = currentStreak(history);

  const choose = (card: number) => {
    if (guess != null || viewed || !pack) {
      return;
    }
    const right = candidates.find((c) => c.card === card)?.pick == null;
    const nextStreak = right ? streak + 1 : 0;
    setGuess(card);
    setHistory((played) => [...played, { pack, candidates, card, right }]);
    if (nextStreak > best) {
      setBest(nextStreak);
      localStorage.setItem(BEST_STREAK_KEY, String(nextStreak));
    }
  };
  const next = () => {
    setGuess(null);
    setRound((r) => r + 1);
  };
  const advance = () => (viewed ? setViewing(null) : next());
  const changeDifficulty = (option: QuickDifficulty) => {
    if (option === difficulty) {
      return;
    }
    if (guess != null) {
      next();
    }
    setViewing(null);
    setHistory([]);
    onDifficulty(option);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space" && revealed) {
        e.preventDefault();
        releaseFocus();
        advance();
      }
      const slot = ["Digit1", "Digit2", "Digit3"].indexOf(e.code);
      if (slot >= 0 && candidates[slot]) {
        choose(candidates[slot].card);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const playedSteps = history.map((played) => ({
    setCode: played.pack.setCode,
    name: setName(played.pack.setCode),
    mark: played.right ? ("hit" as const) : ("miss" as const),
    id: played.pack.eventId,
  }));
  const pendingStep =
    pack && guess == null ? [{ setCode: pack.setCode, name: setName(pack.setCode), mark: null, id: pack.eventId }] : [];
  const recentSteps = (count: number) => [...playedSteps, ...pendingStep].slice(-count);
  const progressFor = (count: number): WheelProgress => {
    const steps = recentSteps(count);
    const firstShown = playedSteps.length + pendingStep.length - steps.length;
    const shownIndex = viewing ?? (pendingStep.length > 0 ? playedSteps.length : null);
    const current = shownIndex == null ? null : shownIndex - firstShown;
    const onSelect = (i: number) => {
      const index = firstShown + i;
      setViewing(index < history.length ? index : null);
    };
    return { kind: "featured", steps, current: current != null && current >= 0 ? current : null, onSelect };
  };
  const header = (className: string, compact: boolean, action?: ReactNode, center?: ReactNode) => (
    <WheelHeader
      action={action}
      center={center}
      setCode={setCode === ALL_SETS_CODE ? (pack?.setCode ?? null) : setCode}
      title="Quick Mode"
      progress={progressFor(compact ? PHONE_HISTORY : HISTORY_ROWS)}
      onHelp={onHelp}
      onExit={onExit}
      compact={compact}
      className={className}
    />
  );

  const restRef = useRef<HTMLDivElement>(null);
  const restCount = shownPack ? withoutBasics(shownPack.pack, shownPack).length - shownCandidates.length : 0;
  const phoneRestFit = usePhoneRestFit(restRef, restCount);

  if (!shownPack && !isPending) {
    return <div className={cn(PIXEL_PANEL, "p-6 font-display text-xl text-subtle")}>No More Packs for This Set</div>;
  }
  const others = shownPack
    ? withoutBasics(shownPack.pack, shownPack).filter((card) => !shownCandidates.some((c) => c.card === card))
    : [];
  return (
    <CardImageMapProvider value={images}>
      <CardZoom card={zoom} onClose={() => setZoom(null)} />
      <div className="flex flex-col gap-3 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(340px,456px)] lg:gap-x-4">
        {header(
          cn(PIXEL_PANEL, "px-3 py-2 lg:hidden"),
          true,
          <span className="flex items-center gap-3">
            <span className="flex items-baseline gap-2 font-display text-base leading-none text-subtle">
              <span>
                Streak <span className={cn("text-lg", streakTone(streak))}>{streak}</span>
              </span>
              <span>
                Best <span className="text-lg text-[#f6c95e]">{best}</span>
              </span>
            </span>
          </span>,
          <span className="flex items-center gap-2">
            <WheelSetDropdown sets={sets} value={setCode} onChange={onSet} compact includeAll />
            <button
              onClick={() => changeDifficulty(difficulty === "easy" ? "hard" : "easy")}
              aria-label={`Difficulty: ${DIFFICULTY_LABEL[difficulty]}`}
              className={cn(difficultyKey(difficulty, "framed"), "h-8 w-[5.5rem] text-lg")}
            >
              {DIFFICULTY_LABEL[difficulty]}
            </button>
          </span>,
        )}
        {shownPack ? (
          <section
            className={cn(
              "relative flex min-w-0 flex-col items-center gap-3",
              "lg:h-[calc(100dvh-125px)] lg:[container-type:size]",
            )}
            style={{ "--rest-count": others.length, "--rest-half": Math.ceil(others.length / 2) } as CSSProperties}
          >
            <div
              className={cn("flex w-full flex-col items-center gap-3", "lg:min-h-0 lg:flex-1 lg:[container-type:size]")}
            >
              <div className="flex h-11 w-full items-center justify-between max-lg:pl-2 lg:translate-y-0.5 lg:justify-center">
                <h2 className={cn("text-2xl lg:text-3xl", PIXEL_HEADING)}>Which One Wheeled?</h2>
                {revealed && (
                  <button
                    key={round}
                    onClick={advance}
                    className={cn(GOLD_BUTTON, "h-11 px-5 text-2xl animate-fadeUpIn lg:hidden")}
                  >
                    {viewed ? "Back to Pack" : "Next Pack"}
                  </button>
                )}
              </div>
              <div
                key={shownPack.eventId}
                className="grid w-full grid-cols-3 gap-3 lg:w-[min(100cqw,calc((100cqh-62px)*3*0.7176+32px))] lg:gap-4"
              >
                {shownCandidates.map((c, i) =>
                  revealed ? (
                    <QuickRevealCard
                      key={c.card}
                      card={shownPack.cards[c.card]}
                      realIndex={c.pick ?? -1}
                      guessed={shownGuess === c.card}
                    />
                  ) : (
                    <PickingCard
                      key={c.card}
                      card={shownPack.cards[c.card]}
                      pickNumber={null}
                      dealDelayMs={i * CANDIDATE_DEAL_STEP_MS}
                      onToggle={() => choose(c.card)}
                      onDragOut={() => {}}
                      onZoom={() => setZoom(shownPack.cards[c.card])}
                    />
                  ),
                )}
              </div>
            </div>
            <div
              className={cn(
                "flex w-full flex-col gap-2",
                "lg:w-[calc(var(--rest-cols)*var(--rest-w)+(var(--rest-cols)-1)*8px+6px)]",
              )}
              style={DESKTOP_REST_SIZE}
            >
              <h3 className={cn("text-2xl max-lg:pl-2 lg:text-center", PIXEL_HEADING)}>Rest of the Pack</h3>
              <div
                ref={restRef}
                className="relative mx-auto flex w-full flex-wrap justify-center gap-2"
                style={phoneRestFit ? { maxWidth: restRowWidth(phoneRestFit) } : undefined}
              >
                {others.map((card, i) => (
                  <button
                    key={`${shownPack.eventId}-${card}`}
                    onClick={() => setZoom(shownPack.cards[card])}
                    aria-label={shownPack.cards[card].n ?? "Card"}
                    style={phoneRestFit ? { width: phoneRestFit.width } : undefined}
                    className={cn(
                      "w-[calc((100%-2.5rem)/6)] rounded-[4.5%/3.2%] opacity-75 transition-opacity hover:opacity-100",
                      "lg:w-[var(--rest-w)]",
                    )}
                  >
                    <span
                      className="block animate-cardDeal"
                      style={{ animationDelay: `${REST_DEAL_START_MS + i * REST_DEAL_STEP_MS}ms` }}
                    >
                      <CardImage card={shownPack.cards[card]} className="rounded-[4.5%/3.2%]" />
                    </span>
                  </button>
                ))}
                {revealed && (
                  <span
                    className={cn(
                      "pointer-events-none absolute inset-0 z-10 hidden items-center justify-center lg:flex",
                    )}
                  >
                    <button
                      key={round}
                      onClick={advance}
                      className={cn(
                        GOLD_BUTTON,
                        "pointer-events-auto h-12 gap-6 px-6 text-2xl animate-fadeUpIn lg:pr-2.5",
                      )}
                    >
                      {viewed ? "Back to Pack" : "Next Pack"}
                      <SpaceKey />
                    </button>
                  </span>
                )}
              </div>
            </div>
          </section>
        ) : (
          <QuickLoading />
        )}
        <aside
          className={cn(
            "hidden flex-col overflow-y-auto border-[3px] border-[#1a120b] bg-[#16110c]/95 p-4 lg:flex",
            "shadow-[inset_0_0_0_2px_#5a3a1e,6px_6px_0_#05070a] lg:h-[calc(100dvh-125px)]",
          )}
        >
          {header(
            "border-b-2 border-[#3a2a17] pb-4",
            false,
            undefined,
            <WheelSetDropdown sets={sets} value={setCode} onChange={onSet} compact includeAll />,
          )}
          <SidebarSection title="Difficulty">
            <div className="flex gap-3">
              {(["easy", "hard"] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => changeDifficulty(option)}
                  aria-pressed={option === difficulty}
                  className={cn(
                    option === difficulty
                      ? difficultyKey(option, "pressed")
                      : cn(difficultyKey(option, "off"), "bg-[#2b3445] text-text shadow-[inset_0_-3px_0_#141a24]"),
                    "h-10 flex-1 text-lg",
                  )}
                >
                  {DIFFICULTY_LABEL[option]}
                </button>
              ))}
            </div>
          </SidebarSection>
          <section className="mt-4 grid grid-cols-2 gap-2 border-t-2 border-[#3a2a17] pt-4 text-center">
            <Stat label="Streak" value={streak} valueClass={streakTone(streak)} />
            <Stat label="Best" value={best} />
          </section>
          {history.length > 0 && (
            <SidebarSection title="Your Calls">
              <div className="grid grid-cols-[minmax(0,1fr)_4rem] items-center gap-x-3 gap-y-1">
                {history
                  .slice(-HISTORY_ROWS)
                  .reverse()
                  .map((played, i) => (
                    <div key={played.pack.eventId} className="contents">
                      <button
                        type="button"
                        onClick={() => setViewing(history.length - 1 - i)}
                        aria-label={`View the ${played.pack.cards[played.card].n ?? "card"} pack`}
                        className={cn(
                          "min-w-0 text-left transition-transform hover:-translate-y-0.5",
                          viewed === played && "ring-2 ring-[#f6c95e]",
                        )}
                      >
                        <CardTitle
                          card={played.pack.cards[played.card]}
                          className="shadow-[0_1px_3px_rgba(0,0,0,0.6)]"
                        />
                      </button>
                      <ResultChip
                        yourIndex={-1}
                        outcome={revealOutcome(played.right ? -1 : 0, -1)}
                        className="w-16 text-base"
                      />
                    </div>
                  ))}
              </div>
            </SidebarSection>
          )}
        </aside>
      </div>
    </CardImageMapProvider>
  );
}

function usePhoneRestFit(ref: RefObject<HTMLDivElement>, count: number): RestFit | null {
  const [fit, setFit] = useState<RestFit | null>(null);
  useLayoutEffect(() => {
    const grid = ref.current;
    if (!grid || count === 0) {
      return;
    }
    const measure = () => {
      if (window.innerWidth >= 1024) {
        setFit(null);
        return;
      }
      const box = grid.getBoundingClientRect();
      const height = window.innerHeight - box.top - PHONE_BOTTOM_GAP_PX;
      const available = grid.parentElement?.clientWidth ?? box.width;
      setFit(bestRestFit(count, available, height));
    };
    measure();
    const observer = new ResizeObserver(measure);
    for (let node: Element | null = grid; node; node = node.parentElement) {
      for (let above = node.previousElementSibling; above; above = above.previousElementSibling) {
        observer.observe(above);
      }
    }
    document.fonts.ready.then(measure);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [ref, count]);
  return fit;
}

interface RestFit {
  columns: number;
  width: number;
}

function bestRestFit(count: number, width: number, height: number): RestFit {
  let best: RestFit = { columns: 3, width: 0 };
  for (let columns = 3; columns <= 7; columns++) {
    const rows = Math.ceil(count / columns);
    const byWidth = (width - (columns - 1) * REST_GAP_PX) / columns;
    const byHeight = ((height - (rows - 1) * REST_GAP_PX) / rows) * CARD_ASPECT;
    const card = Math.floor(Math.min(byWidth, byHeight));
    if (card > best.width + FILL_HEIGHT_TOLERANCE_PX) {
      best = { columns, width: card };
    }
  }
  return best;
}

function restRowWidth(fit: RestFit): number {
  return fit.columns * fit.width + (fit.columns - 1) * REST_GAP_PX;
}

function QuickLoading() {
  return (
    <section className="flex flex-col items-center gap-3 max-lg:min-h-[60dvh] lg:h-[calc(100dvh-125px)]">
      <h2
        className={cn(
          "flex h-11 w-full items-center text-2xl lg:translate-y-0.5 lg:text-3xl max-lg:pl-2 lg:justify-center",
          PIXEL_HEADING,
        )}
      >
        Which One Wheeled?
      </h2>
      <div className="flex w-full flex-1 items-center justify-center lg:pb-[25%]">
        <LoadingLabel label="Shuffling the Packs" className="text-3xl" />
      </div>
    </section>
  );
}

function SidebarSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      className={cn(
        "mt-4 flex flex-col gap-3 border-t-2 border-[#3a2a17] pt-4",
        "first-of-type:mt-0 first-of-type:border-t-0",
      )}
    >
      <h2 className={cn("text-2xl", PIXEL_HEADING)}>{title}</h2>
      {children}
    </section>
  );
}

function Stat({ label, value, valueClass }: { label: string; value: number | string; valueClass?: string }) {
  return (
    <span className="flex flex-col items-center gap-1">
      <span className={cn("text-3xl", PIXEL_HEADING, valueClass)}>{value}</span>
      <span className="font-display text-base leading-none text-subtle">{label}</span>
    </span>
  );
}

function streakTone(streak: number): string {
  if (streak >= 7) {
    return "text-[#ff5a3c] [text-shadow:2px_2px_0_#05070a,0_0_14px_rgba(255,90,60,0.75)]";
  }
  if (streak >= 5) {
    return "text-[#ff9f43] [text-shadow:2px_2px_0_#05070a,0_0_10px_rgba(255,159,67,0.55)]";
  }
  if (streak >= 3) {
    return "text-[#f6c95e]";
  }
  if (streak >= 1) {
    return "text-text";
  }
  return "text-subtle";
}

function currentStreak(history: PlayedRound[]): number {
  let streak = 0;
  for (let i = history.length - 1; i >= 0 && history[i].right; i--) {
    streak++;
  }
  return streak;
}

function pickCandidates(pack: WheelPack, difficulty: QuickDifficulty, stats: CardStatsLookup | null): Candidate[] {
  const random = seededRandom(pack.eventId);
  const pickFrom = <T,>(list: T[]): T => list[Math.floor(random() * list.length)];
  const picks = pack.order
    .map((pick, index) => ({ card: pick.card, pick: index }))
    .filter((c) => !isBasicLand(pack.cards[c.card]));
  const spells = withoutBasics(pack.wheel, pack);
  const playable = spells.filter((card) => !isLowGrade(pack.cards[card], stats));
  const wheeled: Candidate = { card: pickFrom(playable.length > 0 ? playable : spells), pick: null };
  const beforeWheel = picks.slice(-BAND_SIZE);
  if (difficulty === "hard") {
    const first = pickFrom(beforeWheel);
    const second = pickFrom(beforeWheel.filter((c) => c !== first));
    return [first, second, wheeled].sort(() => random() - 0.5);
  }
  const opening = picks.slice(0, BAND_SIZE);
  return [pickFrom(opening), pickFrom(beforeWheel), wheeled].sort(() => random() - 0.5);
}

function isLowGrade(card: ArtifactCard, stats: CardStatsLookup | null): boolean {
  const grade = stats?.gradesFor(card.n ?? "")?.all;
  return grade != null && (grade.startsWith("D") || grade.startsWith("F"));
}

function withoutBasics(cards: number[], pack: WheelPack): number[] {
  return cards.filter((card) => !isBasicLand(pack.cards[card]));
}

function isBasicLand(card: ArtifactCard): boolean {
  return Boolean(card.type?.includes("Basic")) || BASIC_LAND_NAMES.has(card.n ?? "");
}

const BASIC_LAND_NAMES = new Set(["Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"]);

function seededRandom(key: string): () => number {
  let state = 0;
  for (const char of key) {
    state = (state * 31 + char.charCodeAt(0)) >>> 0;
  }
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}
