import { shortDayLabel, useWheelSets } from "../../../data/draftGames";
import { useDailyTrophyRounds } from "../../../data/trophyMage";
import { DAILY_PLAY, dayProgress, type IntroData } from "./introParts";
import { TrophyShowcase } from "./TrophyShelf";
import { readTrophyDay, trophyDayStorageKey } from "./useTrophyDay";

export function TrophyIntro({
  dayKey,
  onPlay,
  onHelp,
}: {
  dayKey: string;
  onPlay: (play: string, options?: { round?: number; day?: string }) => void;
  onHelp: () => void;
}) {
  const { sets } = useWheelSets();
  const { rounds } = useDailyTrophyRounds(dayKey);
  const day = readTrophyDay(trophyDayStorageKey(dayKey));
  const data: IntroData = {
    dayKey,
    dayLabel: shortDayLabel(dayKey),
    ...dayProgress(rounds, day),
    sets,
    onDaily: () => onPlay(DAILY_PLAY),
    onRound: (round) => onPlay(DAILY_PLAY, { round }),
    onDay: (pastDay) => onPlay(DAILY_PLAY, { day: pastDay }),
    onSet: (code) => onPlay(code),
    onHelp,
  };
  return <TrophyShowcase data={data} />;
}
