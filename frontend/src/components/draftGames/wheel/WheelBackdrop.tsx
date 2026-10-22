import { WHEEL_GAME_ART } from "../../../data/draftGames";
import { cn } from "../../../lib/utils";
import { GameBackdrop } from "../GameBackdrop";

export function WheelBackdrop() {
  return (
    <GameBackdrop
      art={WHEEL_GAME_ART}
      className={cn(
        "opacity-[0.17] saturate-[1.3] contrast-[1.1]",
        "max-sm:h-[62%] max-sm:w-auto max-sm:max-w-none max-sm:self-center",
        "max-sm:[mask-image:linear-gradient(to_bottom,transparent,black_18%,black_78%,transparent)]",
      )}
    />
  );
}
