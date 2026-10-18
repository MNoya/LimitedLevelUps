import { useState, type ReactNode } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { PageShell } from "../components/PageShell";
import { Container } from "../components/Container";
import { GameStatus } from "../components/draftGames/GameChrome";
import { TrophyBackdrop } from "../components/draftGames/trophy/TrophyBackdrop";
import { TrophyGame } from "../components/draftGames/trophy/TrophyGame";
import { TrophyHelpDialog } from "../components/draftGames/trophy/TrophyHelp";
import { DAILY_PLAY } from "../components/draftGames/trophy/introParts";
import { TrophyIntro } from "../components/draftGames/trophy/TrophyIntro";
import { TrophyTitle } from "../components/draftGames/trophy/TrophyTitle";
import { trophyDayStorageKey } from "../components/draftGames/trophy/useTrophyDay";
import { MINI_GAMES_HEADER, utcDayKey, useWheelSets } from "../data/draftGames";
import { useDailyTrophyRounds, useFreePlayTrophyRounds } from "../data/trophyMage";
import { cn } from "../lib/utils";

export function TrophyMageLabPage() {
  const [dayKey] = useState(utcDayKey);
  const [params, setParams] = useSearchParams();
  const [helpOpen, openHelp, closeHelp] = useGuideHash();
  const play = params.get("play");
  const exit = () => setParams({});
  const playParams = (next: string, options: { round?: number; day?: string } = {}) => {
    const search: Record<string, string> = { play: next };
    if (options.round != null) {
      search.round = String(options.round);
    }
    if (options.day) {
      search.day = options.day;
    }
    return search;
  };

  let body: ReactNode;
  if (!play) {
    body = (
      <TrophyIntro dayKey={dayKey} onPlay={(next, options) => setParams(playParams(next, options))} onHelp={openHelp} />
    );
  } else if (play === DAILY_PLAY) {
    const round = params.get("round");
    const requestedDay = params.get("day");
    const playedDay = requestedDay && isEarlierDay(requestedDay, dayKey) ? requestedDay : dayKey;
    body = (
      <DailyGame dayKey={playedDay} startAt={round == null ? null : Number(round)} onHelp={openHelp} onExit={exit} />
    );
  } else {
    body = <FreePlayGame key={play} setCode={play} onHelp={openHelp} onExit={exit} />;
  }

  return (
    <PageShell
      subtitle="TROPHY MAGE"
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
      <TrophyHelpDialog open={helpOpen} onClose={closeHelp} />
    </PageShell>
  );
}

function DailyGame({
  dayKey,
  startAt,
  onHelp,
  onExit,
}: {
  dayKey: string;
  startAt: number | null;
  onHelp: () => void;
  onExit: () => void;
}) {
  const { rounds, isPending } = useDailyTrophyRounds(dayKey);
  if (isPending) {
    return <GameStatus>Loading Today's Pods</GameStatus>;
  }
  if (rounds.length === 0) {
    return <GameStatus>No Pods to play yet</GameStatus>;
  }
  return (
    <TrophyGame
      key={dayKey}
      rounds={rounds}
      dayKey={dayKey}
      storageKey={trophyDayStorageKey(dayKey)}
      startAt={startAt}
      onHelp={onHelp}
      onExit={onExit}
    />
  );
}

function FreePlayGame({ setCode, onHelp, onExit }: { setCode: string; onHelp: () => void; onExit: () => void }) {
  const [seed] = useState(() => Math.floor(Math.random() * 1_000_000));
  const [wanted, setWanted] = useState(1);
  const { rounds, isPending, exhausted } = useFreePlayTrophyRounds(setCode, wanted, seed);
  const { sets, isPending: setsPending } = useWheelSets();
  if (!setsPending && !sets.some((set) => set.code === setCode)) {
    return <GameStatus>No Pods to play for this set yet</GameStatus>;
  }
  if (rounds.length === 0) {
    return <GameStatus>{isPending ? "Loading Pods" : "No Pods to play for this set yet"}</GameStatus>;
  }
  return (
    <TrophyGame
      rounds={rounds}
      dayKey={null}
      storageKey={null}
      exhausted={exhausted}
      onAdvance={(index) => setWanted(index + 1)}
      onHelp={onHelp}
      onExit={onExit}
    />
  );
}

function isEarlierDay(candidate: string, today: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(candidate) && candidate < today;
}

function useGuideHash(): [boolean, () => void, () => void] {
  const location = useLocation();
  const navigate = useNavigate();
  const open = location.hash === "#guide";
  const openGuide = () => navigate({ search: location.search, hash: "guide" });
  const closeGuide = () => navigate({ search: location.search, hash: "" }, { replace: true });
  return [open, openGuide, closeGuide];
}
