import { shortDayLabel, useWheelSets } from "../../../data/draftGames";
import { useDailyTrophyRounds, type TrophyMageRound } from "../../../data/trophyMage";
import {
  DAILY_PLAY,
  DAY_DONE_ACTION,
  dayProgress,
  ENDLESS_ACTION,
  NEXT_DAY_ACTION,
  type DaySlot,
  type IntroData,
} from "./introParts";
import { TrophyHelpDialog } from "./TrophyHelp";
import { TrophyShowcase } from "./TrophyShelf";
import { daysBefore, nextOpenDay, readTrophyDay, trophyDayStorageKey } from "./useTrophyDay";

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
  const yesterday = useDailyTrophyRounds(yesterdayKey);
  const twoDaysAgo = useDailyTrophyRounds(twoDaysAgoKey);
  const progressOf = (key: string, rounds: TrophyMageRound[]) =>
    dayProgress(rounds, readTrophyDay(trophyDayStorageKey(key)));
  const progress = progressOf(dayKey, today.rounds);
  const yesterdayProgress = progressOf(yesterdayKey, yesterday.rounds);
  const twoDaysAgoProgress = progressOf(twoDaysAgoKey, twoDaysAgo.rounds);
  const showsResultHere = progress.dailyAction === DAY_DONE_ACTION;
  const nextDayKey = nextOpenDay(dayKey, dayKey);
  const newestSet = sets[0]?.code;
  const playNext = () => {
    if (nextDayKey) {
      onPlay(DAILY_PLAY, { day: nextDayKey });
    } else if (newestSet) {
      onPlay(newestSet);
    }
  };
  const todayLoaded = !today.isPending;
  const data: IntroData = {
    dayKey,
    dayLabel: shortDayLabel(dayKey),
    ...progress,
    dailyAction: showsResultHere ? (nextDayKey ? NEXT_DAY_ACTION : ENDLESS_ACTION) : progress.dailyAction,
    dayScore: showsResultHere ? { ...totalScore(progress.slots), pending: !todayLoaded } : null,
    pastDays: [
      { dayKey: yesterdayKey, slots: yesterdayProgress.slots },
      { dayKey: twoDaysAgoKey, slots: twoDaysAgoProgress.slots },
    ],
    sets,
    onDaily: showsResultHere ? playNext : () => onPlay(DAILY_PLAY),
    onResults: showsResultHere ? () => onPlay(DAILY_PLAY, { results: true }) : null,
    onRound: (round) => onPlay(DAILY_PLAY, progress.dailyAction === DAY_DONE_ACTION ? { review: round } : { round }),
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

function totalScore(slots: DaySlot[]): { points: number; max: number } {
  let points = 0;
  let max = 0;
  for (const slot of slots) {
    points += slot.points ?? 0;
    max += slot.max;
  }
  return { points, max };
}
