import { daysBefore, shortDayLabel, useWheelSets } from "../../../data/draftGames";
import { useDailyTrophyRounds, type TrophyMageRound } from "../../../data/trophyMage";
import { NEXT_DAY_ACTION, RESULTS_ACTION, nextPlayAfter, readGameDay } from "../gameDay";
import { DAILY_PLAY, dayProgress, type IntroData } from "./introParts";
import { TROPHY_DAY } from "./trophyDay";
import { TrophyHelpDialog } from "./TrophyHelp";
import { TrophyShowcase } from "./TrophyShelf";

export function TrophyIntro({
  dayKey,
  onPlay,
  onHelp,
  helpOpen,
  onCloseHelp,
}: {
  dayKey: string;
  onPlay: (play: string, options?: { round?: number; review?: number; results?: boolean; day?: string }) => void;
  onHelp: () => void;
  helpOpen: boolean;
  onCloseHelp: () => void;
}) {
  const yesterdayKey = daysBefore(dayKey, 1);
  const twoDaysAgoKey = daysBefore(dayKey, 2);
  const { sets } = useWheelSets();
  const today = useDailyTrophyRounds(dayKey);
  const todayLoaded = !today.isPending;
  const yesterday = useDailyTrophyRounds(yesterdayKey, todayLoaded);
  const twoDaysAgo = useDailyTrophyRounds(twoDaysAgoKey, todayLoaded);
  const progressOf = (key: string, rounds: TrophyMageRound[]) => dayProgress(rounds, readGameDay(TROPHY_DAY, key));
  const progress = progressOf(dayKey, today.rounds);
  const yesterdayProgress = progressOf(yesterdayKey, yesterday.rounds);
  const twoDaysAgoProgress = progressOf(twoDaysAgoKey, twoDaysAgo.rounds);
  const showsResultHere = progress.dailyAction === RESULTS_ACTION;
  const nextPlay = nextPlayAfter(TROPHY_DAY, dayKey, dayKey, sets[0]?.code);
  const playNext = () => {
    if (nextPlay.label === NEXT_DAY_ACTION) {
      onPlay(DAILY_PLAY, { day: nextPlay.dayKey });
    } else if (nextPlay.setCode) {
      onPlay(nextPlay.setCode);
    }
  };
  const data: IntroData = {
    dayKey,
    dayLabel: shortDayLabel(dayKey),
    ...progress,
    dailyAction: showsResultHere ? nextPlay.label : progress.dailyAction,
    dayDone: showsResultHere,
    pastDays: [
      { dayKey: yesterdayKey, slots: yesterdayProgress.slots },
      { dayKey: twoDaysAgoKey, slots: twoDaysAgoProgress.slots },
    ],
    sets,
    onDaily: showsResultHere ? playNext : () => onPlay(DAILY_PLAY),
    onResults: showsResultHere ? () => onPlay(DAILY_PLAY, { results: true }) : null,
    onRound: (round) => onPlay(DAILY_PLAY, showsResultHere ? { review: round } : { round }),
    onDay: (pastDay) => onPlay(DAILY_PLAY, { day: pastDay }),
    onSet: (code) => onPlay(code),
    onHelp,
  };
  return (
    <div className="flex flex-1 flex-col">
      <TrophyShowcase data={data} />
      <TrophyHelpDialog
        open={helpOpen}
        onClose={onCloseHelp}
        action={{ label: data.dailyAction, onClick: data.onDaily }}
      />
    </div>
  );
}
