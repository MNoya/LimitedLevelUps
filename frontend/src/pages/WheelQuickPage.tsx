import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { SetGlyph } from "../components/Brand";
import { Container } from "../components/Container";
import { PageShell } from "../components/PageShell";
import { CardImage, CardImageMapProvider } from "../components/pod/review/ReviewCard";
import { DARK_PIXEL_BUTTON, GOLD_BUTTON, PIXEL_HEADING, PIXEL_PANEL } from "../components/draftGames/pixelStyles";
import { CardTitle } from "../components/draftGames/wheel/CardTitle";
import {
  CardZoom,
  PickingCard,
  QuickRevealCard,
  ResultChip,
  revealOutcome,
} from "../components/draftGames/wheel/PackGrid";
import { useGuideHash, useNoScrollGutter } from "../components/draftGames/wheel/pageHooks";
import { SpaceKey } from "../components/draftGames/wheel/SpaceKey";
import { WheelBackdrop } from "../components/draftGames/wheel/WheelBackdrop";
import { WheelHeader } from "../components/draftGames/wheel/WheelHeader";
import { QuickHelpDialog } from "../components/draftGames/wheel/WheelHelp";
import { useCardImageMap } from "../data/cardImages";
import { MINI_GAMES_HEADER, useFreePlayPacks, useWheelSets, type WheelPack } from "../data/draftGames";
import { useCardStats, type CardStatsLookup } from "../data/tierList";
import { cn } from "../lib/utils";
import type { ArtifactCard } from "../types/leaderboard";

type QuickMode = "easy" | "hard";

interface Candidate {
  card: number;
  pick: number | null;
}

interface PlayedRound {
  pack: WheelPack;
  card: number;
  right: boolean;
}

const SET_CHOICES = 5;
const HISTORY_ROWS = 8;
const BEST_STREAK_KEY = "wheel-of-fortune-quick-best";
const BAND_SIZE = 3;

export function WheelQuickPage() {
  useNoScrollGutter();
  const navigate = useNavigate();
  const [helpOpen, openHelp, closeHelp] = useGuideHash("quick-guide");
  const { sets } = useWheelSets();
  const [setCode, setSetCode] = useState<string | null>(null);
  const [mode, setMode] = useState<QuickMode>("easy");
  const activeSet = setCode ?? sets[0]?.code ?? null;
  const setName = (code: string) => sets.find((set) => set.code === code)?.name ?? code;
  return (
    <PageShell subtitle="WHEEL OF FORTUNE" subtitleShort={MINI_GAMES_HEADER} footer={false}>
      <Container className="draft-game pt-3 pb-4 lg:px-4 2xl:px-10">
        <WheelBackdrop />
        <div className="relative z-[1]">
          {activeSet && (
            <QuickGame
              key={`${activeSet}-${mode}`}
              setCode={activeSet}
              mode={mode}
              setChoices={sets.slice(0, SET_CHOICES).map((set) => set.code)}
              setName={setName}
              onMode={setMode}
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
  mode,
  setChoices,
  setName,
  onMode,
  onSet,
  onHelp,
  onExit,
}: {
  setCode: string;
  mode: QuickMode;
  setChoices: string[];
  setName: (code: string) => string;
  onMode: (mode: QuickMode) => void;
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
  const { packs, isPending } = useFreePlayPacks(setCode, round + 2, seed);
  const stats = useCardStats(setCode);
  const pack = packs[round];
  const images = useCardImageMap(
    useMemo(() => packs.flatMap((p) => p.pack.map((i) => ({ name: p.cards[i].n, set: p.cards[i].s }))), [packs]),
  );
  const candidates = useMemo(() => (pack ? pickCandidates(pack, mode, stats) : []), [pack, mode, stats]);
  const revealed = guess != null;
  const streak = currentStreak(history);

  const choose = (card: number) => {
    if (revealed || !pack) {
      return;
    }
    const right = candidates.find((c) => c.card === card)?.pick == null;
    const nextStreak = right ? streak + 1 : 0;
    setGuess(card);
    setHistory((played) => [...played, { pack, card, right }]);
    if (nextStreak > best) {
      setBest(nextStreak);
      localStorage.setItem(BEST_STREAK_KEY, String(nextStreak));
    }
  };
  const next = () => {
    setGuess(null);
    setRound((r) => r + 1);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space" && revealed) {
        e.preventDefault();
        next();
      }
      const slot = ["Digit1", "Digit2", "Digit3"].indexOf(e.code);
      if (slot >= 0 && candidates[slot]) {
        choose(candidates[slot].card);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const steps = history.slice(-HISTORY_ROWS).map((played) => ({
    setCode: played.pack.setCode,
    name: setName(played.pack.setCode),
    mark: played.right ? ("hit" as const) : ("miss" as const),
  }));
  const header = (className: string, compact: boolean) => (
    <WheelHeader
      setCode={setCode}
      title="Quick Mode"
      subtitle={setName(setCode)}
      progress={{ kind: "featured", steps, current: null }}
      onHelp={onHelp}
      onExit={onExit}
      compact={compact}
      className={className}
    />
  );
  const nextButton = (floating: boolean) => (
    <span key={`${round}-${revealed}`} className="flex animate-fadeUpIn">
      <button
        onClick={next}
        className={cn(GOLD_BUTTON, floating ? "h-12 gap-6 pr-2.5 pl-6 text-2xl" : "px-5 py-2.5 text-xl")}
      >
        Next Pack
        {floating && <SpaceKey />}
      </button>
    </span>
  );

  if (!pack) {
    return (
      <div className={cn(PIXEL_PANEL, "p-6 font-display text-xl text-subtle")}>
        {isPending ? "Shuffling Packs" : "No More Packs for This Set"}
      </div>
    );
  }
  const others = withoutBasics(pack.pack, pack).filter((card) => !candidates.some((c) => c.card === card));
  return (
    <CardImageMapProvider value={images}>
      <CardZoom card={zoom} onClose={() => setZoom(null)} />
      <div
        className={cn(
          "flex flex-col gap-3 pb-28 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(340px,456px)] lg:gap-x-4 lg:pb-0",
          "lg:[--quick-row:calc((100dvh-232px)/3.4)]",
        )}
      >
        {header(cn(PIXEL_PANEL, "h-[84px] px-3 py-2 lg:hidden"), true)}
        <div className="relative flex flex-col items-center gap-3 lg:h-[calc(100dvh-125px)]">
          <h2 className={cn("self-start text-2xl lg:self-center", PIXEL_HEADING)}>Which One Wheeled?</h2>
          <div
            key={pack.eventId}
            className="grid w-full grid-cols-3 gap-3 sm:gap-4 lg:max-w-[min(100%,calc(var(--quick-row)*3.014+32px))]"
          >
            {candidates.map((c) =>
              revealed ? (
                <QuickRevealCard
                  key={c.card}
                  card={pack.cards[c.card]}
                  realIndex={c.pick ?? -1}
                  guessed={guess === c.card}
                />
              ) : (
                <PickingCard
                  key={c.card}
                  card={pack.cards[c.card]}
                  pickNumber={null}
                  dealIndex={0}
                  onToggle={() => choose(c.card)}
                  onDragOut={() => {}}
                  onZoom={() => setZoom(pack.cards[c.card])}
                />
              ),
            )}
          </div>
          <div className="flex w-full items-center gap-3 lg:max-w-[min(100%,calc(var(--quick-row)*4.306+40px))]">
            <h3 className={cn("text-lg", PIXEL_HEADING)}>Rest of the Pack</h3>
            <span className={cn("ml-auto hidden lg:flex", !revealed && "invisible")}>{nextButton(true)}</span>
          </div>
          <div className="grid w-full grid-cols-4 gap-2 sm:grid-cols-6 lg:max-w-[min(100%,calc(var(--quick-row)*4.306+40px))]">
            {others.map((card) => (
              <button
                key={card}
                onClick={() => setZoom(pack.cards[card])}
                aria-label={pack.cards[card].n ?? "Card"}
                className="rounded-[4.5%/3.2%] opacity-75 transition-opacity hover:opacity-100"
              >
                <CardImage card={pack.cards[card]} className="rounded-[4.5%/3.2%]" />
              </button>
            ))}
          </div>
        </div>
        <aside
          className={cn(
            "hidden flex-col gap-5 border-[3px] border-[#1a120b] bg-[#16110c]/95 p-4 lg:flex",
            "shadow-[inset_0_0_0_2px_#5a3a1e,6px_6px_0_#05070a] lg:max-h-[calc(100dvh-125px)] lg:self-start",
          )}
        >
          {header("border-b-2 border-[#3a2a17] pb-4", false)}
          <SidebarSection title="Difficulty">
            <div className="flex gap-2">
              {(["easy", "hard"] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => onMode(option)}
                  className={cn(option === mode ? GOLD_BUTTON : DARK_PIXEL_BUTTON, "h-9 flex-1 text-lg")}
                >
                  {option === "easy" ? "Easy" : "Hard"}
                </button>
              ))}
            </div>
          </SidebarSection>
          <SidebarSection title="Set">
            <div className="flex flex-wrap gap-2">
              {setChoices.map((code) => (
                <button
                  key={code}
                  onClick={() => onSet(code)}
                  title={setName(code)}
                  aria-label={setName(code)}
                  className={cn(code === setCode ? GOLD_BUTTON : DARK_PIXEL_BUTTON, "size-10")}
                >
                  <SetGlyph code={code} size={18} className="text-current" />
                </button>
              ))}
            </div>
          </SidebarSection>
          <div className="grid grid-cols-2 gap-2 border-y-2 border-[#3a2a17] py-4 text-center">
            <Stat label="Streak" value={streak} />
            <Stat label="Best" value={best} />
          </div>
          {history.length > 0 && (
            <SidebarSection title="Your Calls">
              <div className="grid grid-cols-[minmax(0,1fr)_4rem] items-center gap-x-3 gap-y-1">
                {history
                  .slice(-HISTORY_ROWS)
                  .reverse()
                  .map((played) => (
                    <div key={played.pack.eventId} className="contents">
                      <CardTitle card={played.pack.cards[played.card]} className="shadow-[0_1px_3px_rgba(0,0,0,0.6)]" />
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
        <div
          className={cn(
            "fixed inset-x-0 bottom-0 z-20 flex h-[76px] items-center gap-3 border-t-[3px] border-[#1a120b] px-4",
            "bg-[#16110c] shadow-[inset_0_2px_0_#5a3a1e] lg:hidden",
          )}
        >
          <span className="flex min-w-0 flex-1 items-baseline gap-2">
            <span className={cn("text-3xl", PIXEL_HEADING)}>{streak}</span>
            <span className="font-display text-lg text-text">Streak</span>
            <span className="font-display text-base text-subtle">Best {best}</span>
          </span>
          <button
            onClick={() => onMode(mode === "easy" ? "hard" : "easy")}
            className={cn(DARK_PIXEL_BUTTON, "h-10 px-3 text-lg")}
          >
            {mode === "easy" ? "Easy" : "Hard"}
          </button>
          {revealed && nextButton(false)}
        </div>
      </div>
    </CardImageMapProvider>
  );
}

function SidebarSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className={cn("text-xl", PIXEL_HEADING)}>{title}</h2>
      {children}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <span className="flex flex-col items-center gap-1">
      <span className={cn("text-3xl", PIXEL_HEADING)}>{value}</span>
      <span className="font-display text-base leading-none text-subtle">{label}</span>
    </span>
  );
}

function currentStreak(history: PlayedRound[]): number {
  let streak = 0;
  for (let i = history.length - 1; i >= 0 && history[i].right; i--) {
    streak++;
  }
  return streak;
}

function pickCandidates(pack: WheelPack, mode: QuickMode, stats: CardStatsLookup | null): Candidate[] {
  const random = seededRandom(pack.eventId);
  const pickFrom = <T,>(list: T[]): T => list[Math.floor(random() * list.length)];
  const picks = pack.order
    .map((pick, index) => ({ card: pick.card, pick: index }))
    .filter((c) => !isBasicLand(pack.cards[c.card]));
  const spells = withoutBasics(pack.wheel, pack);
  const playable = spells.filter((card) => !isLowGrade(pack.cards[card], stats));
  const wheeled: Candidate = { card: pickFrom(playable.length > 0 ? playable : spells), pick: null };
  const beforeWheel = picks.slice(-BAND_SIZE);
  if (mode === "hard") {
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
