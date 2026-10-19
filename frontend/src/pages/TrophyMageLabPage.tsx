import { useState, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { PageShell } from "../components/PageShell";
import { Container } from "../components/Container";
import { TrophyBackdrop } from "../components/draftGames/trophy/TrophyBackdrop";
import { TrophyGame } from "../components/draftGames/trophy/TrophyGame";
import { TrophyHelpDialog } from "../components/draftGames/trophy/TrophyHelp";
import { DAILY_PLAY, TrophyLoading, TrophyNotice } from "../components/draftGames/trophy/introParts";
import { TrophyIntro } from "../components/draftGames/trophy/TrophyIntro";
import { TrophyTitle } from "../components/draftGames/trophy/TrophyTitle";
import { trophyDayStorageKey } from "../components/draftGames/trophy/useTrophyDay";
import { useGuideHash, useNoScrollGutter } from "../components/draftGames/wheel/pageHooks";
import { MINI_GAMES_HEADER, gameDayKey, useWheelSets } from "../data/draftGames";
import { TROPHY_DAILY_ROUNDS, useDailyTrophyRounds, useFreePlayTrophyRounds } from "../data/trophyMage";
import { cn } from "../lib/utils";

const REVIEW_PARAM = "review";
const ROUND_PARAM = "round";
const INVALID_ROUND = -1;
const RESET_PARAM = "reset";
const RESULTS_PARAM = "results";
const TROPHY_PATH = "/trophy-mage";
const DAY_SEGMENT = /^\d{4}-\d{2}-\d{2}$/;

interface PlayOptions {
  round?: number;
  review?: number;
  results?: boolean;
}

export function TrophyMageLabPage() {
  useState(clearSavedDaysOnRequest);
  const [dayKey] = useState(gameDayKey);
  const [params] = useSearchParams();
  const { play: playSegment } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  useNoScrollGutter();
  const [helpOpen, openHelp, closeHelp] = useGuideHash("guide");
  const goTo = (segment: string | null, search: Record<string, string> = {}, replace = false) =>
    navigate(
      {
        pathname: segment ? `${TROPHY_PATH}/${segment}` : TROPHY_PATH,
        search: new URLSearchParams(search).toString(),
        hash: "",
      },
      { replace },
    );
  const closeGuide = () => {
    closeHelp();
    (document.activeElement as HTMLElement | null)?.blur();
  };
  const exit = () => goTo(null);
  const playDay = (day: string, options: PlayOptions = {}) => goTo(day, playSearch(options));

  const play = playSegment ?? null;
  if (play && DAY_SEGMENT.test(play) && play > dayKey) {
    return <Navigate to={{ pathname: `${TROPHY_PATH}/${dayKey}`, search: params.toString() }} replace />;
  }
  let body: ReactNode;
  if (!play) {
    body = (
      <TrophyIntro
        dayKey={dayKey}
        onPlay={(next, options = {}) =>
          next === DAILY_PLAY ? playDay(options.day ?? dayKey, options) : goTo(next.toLowerCase())
        }
        onHelp={openHelp}
        helpOpen={helpOpen}
        onCloseHelp={closeGuide}
      />
    );
  } else if (DAY_SEGMENT.test(play)) {
    const startAt = roundIndexParam(params, ROUND_PARAM);
    const reviewIndex = roundIndexParam(params, REVIEW_PARAM);
    if (startAt === INVALID_ROUND || reviewIndex === INVALID_ROUND) {
      const canonical = new URLSearchParams(params);
      canonical.delete(ROUND_PARAM);
      canonical.delete(REVIEW_PARAM);
      return <Navigate to={{ pathname: location.pathname, search: canonical.toString() }} replace />;
    }
    const playedDay = play;
    body = (
      <DailyGame
        dayKey={playedDay}
        startAt={startAt}
        reviewIndex={reviewIndex}
        showResults={params.has(RESULTS_PARAM)}
        onReview={(index, replace) => goTo(playedDay, playSearch({ review: index }), replace)}
        onEndReview={() => {
          if (location.key === "default") {
            goTo(playedDay, {}, true);
          } else {
            navigate(-1);
          }
        }}
        onHelp={openHelp}
        onExit={exit}
        onPlayDay={(day) => playDay(day)}
        onPlaySet={(code) => goTo(code.toLowerCase())}
        onDayDone={() => goTo(playedDay, playSearch({ results: true }))}
      />
    );
  } else {
    const setCode = play.toUpperCase();
    body = <FreePlayGame key={setCode} setCode={setCode} onHelp={openHelp} onExit={exit} />;
  }

  return (
    <PageShell
      subtitle="TROPHY MAGE"
      titleHref="/trophy-mage"
      subtitleShort={MINI_GAMES_HEADER}
      phoneTitle={play ? <TrophyTitle scale={2} interactive={false} /> : undefined}
      footer={false}
    >
      <Container
        className={cn(
          "draft-game game-theme-ice pt-3 pb-4",
          play ? "max-lg:pt-2 max-lg:pb-2" : "flex flex-1 flex-col max-sm:pb-2 [@media(max-height:760px)]:sm:pb-1",
        )}
      >
        <TrophyBackdrop />
        <div className={cn("relative z-[1]", !play && "flex flex-1 flex-col")}>{body}</div>
      </Container>
      {play && <TrophyHelpDialog open={helpOpen} onClose={closeGuide} />}
    </PageShell>
  );
}

function DailyGame({
  dayKey,
  startAt,
  reviewIndex,
  showResults,
  onReview,
  onEndReview,
  onHelp,
  onExit,
  onPlayDay,
  onPlaySet,
  onDayDone,
}: {
  dayKey: string;
  startAt: number | null;
  reviewIndex: number | null;
  showResults: boolean;
  onReview: (index: number, replace?: boolean) => void;
  onEndReview: () => void;
  onHelp: () => void;
  onExit: () => void;
  onPlayDay: (dayKey: string) => void;
  onPlaySet: (setCode: string) => void;
  onDayDone: () => void;
}) {
  const { rounds, isPending } = useDailyTrophyRounds(dayKey);
  if (isPending) {
    return <TrophyLoading />;
  }
  if (rounds.length === 0) {
    return <TrophyNotice label="No Pods to play yet" onExit={onExit} />;
  }
  return (
    <TrophyGame
      key={dayKey}
      rounds={rounds}
      dayKey={dayKey}
      storageKey={trophyDayStorageKey(dayKey)}
      startAt={startAt}
      reviewIndex={reviewIndex}
      showResults={showResults}
      onReview={onReview}
      onEndReview={onEndReview}
      onPlayDay={onPlayDay}
      onPlaySet={onPlaySet}
      onDayDone={onDayDone}
      onHelp={onHelp}
      onExit={onExit}
    />
  );
}

function FreePlayGame({ setCode, onHelp, onExit }: { setCode: string; onHelp: () => void; onExit: () => void }) {
  const [seed] = useState(() => Math.floor(Math.random() * 1_000_000));
  const [wanted, setWanted] = useState(2);
  const { rounds, isPending, exhausted } = useFreePlayTrophyRounds(setCode, wanted, seed);
  const { sets, isPending: setsPending } = useWheelSets();
  if (!setsPending && !sets.some((set) => set.code === setCode)) {
    return <TrophyNotice label="No Pods to play for this set yet" onExit={onExit} />;
  }
  if (rounds.length === 0) {
    if (isPending) {
      return <TrophyLoading />;
    }
    return <TrophyNotice label="No Pods to play for this set yet" onExit={onExit} />;
  }
  return (
    <TrophyGame
      rounds={rounds}
      dayKey={null}
      storageKey={null}
      exhausted={exhausted}
      onAdvance={(index) => setWanted(index + 2)}
      onHelp={onHelp}
      onExit={onExit}
    />
  );
}

function playSearch(options: PlayOptions): Record<string, string> {
  const search: Record<string, string> = {};
  if (options.round != null) {
    search[ROUND_PARAM] = String(options.round + 1);
  }
  if (options.review != null) {
    search[REVIEW_PARAM] = String(options.review + 1);
  }
  if (options.results) {
    search[RESULTS_PARAM] = "1";
  }
  return search;
}

function roundIndexParam(params: URLSearchParams, name: string): number | null {
  const value = params.get(name);
  if (value == null) {
    return null;
  }
  const roundNumber = Number(value);
  if (!Number.isInteger(roundNumber) || roundNumber < 1 || roundNumber > TROPHY_DAILY_ROUNDS) {
    return INVALID_ROUND;
  }
  return roundNumber - 1;
}

function clearSavedDaysOnRequest() {
  const url = new URL(window.location.href);
  if (!import.meta.env.DEV || !url.searchParams.has(RESET_PARAM)) {
    return;
  }
  const savedDayPrefix = trophyDayStorageKey("");
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith(savedDayPrefix)) {
      localStorage.removeItem(key);
    }
  }
  url.searchParams.delete(RESET_PARAM);
  window.history.replaceState(window.history.state, "", url);
}
