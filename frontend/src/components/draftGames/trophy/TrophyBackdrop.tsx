import { cn } from "../../../lib/utils";
import { TROPHY_MAGE_ART } from "../../../data/trophyMage";
import { GameBackdrop } from "../GameBackdrop";

export function TrophyBackdrop() {
  return (
    <GameBackdrop
      art={TROPHY_MAGE_ART}
      className={cn(
        "opacity-[0.24] saturate-[1.2]",
        "max-sm:h-[62%] max-sm:w-auto max-sm:max-w-none max-sm:self-center",
        "max-sm:[mask-image:linear-gradient(to_bottom,transparent,black_18%,black_78%,transparent)]",
      )}
    />
  );
}
