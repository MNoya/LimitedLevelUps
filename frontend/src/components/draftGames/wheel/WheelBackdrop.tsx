import { WHEEL_GAME_ART } from "../../../data/draftGames";
import { GameBackdrop } from "../GameBackdrop";

export function WheelBackdrop() {
  return <GameBackdrop art={WHEEL_GAME_ART} className="opacity-[0.17] saturate-[1.3] contrast-[1.1]" />;
}
