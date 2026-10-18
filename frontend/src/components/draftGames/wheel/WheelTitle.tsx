import { useState } from "react";

import { cn } from "../../../lib/utils";
import { WHEEL_GAME_TITLE } from "../../../data/draftGames";
import { WheelEmoji } from "./WheelEmoji";

const TITLE_WIDTH = 110;
const TITLE_HEIGHT = 20;
const WHEEL_RIGHT_X = 51.6;
const BASELINE = 17.2;
const EMOJI_WIDTH = 23;
const EMOJI_HEIGHT = 25;
const EMOJI_SCALE_RATIO = 0.47;

export function WheelTitle({ scale, interactive = true }: { scale: number; interactive?: boolean }) {
  const [spins, setSpins] = useState(0);
  const emojiScale = scale * EMOJI_SCALE_RATIO;
  const emojiWidth = EMOJI_WIDTH * emojiScale;
  const Wordmark = interactive ? "h1" : "span";
  const Spinner = interactive ? "button" : "span";
  return (
    <Wordmark
      aria-label={WHEEL_GAME_TITLE}
      className="relative block bg-no-repeat [image-rendering:pixelated]"
      style={{
        width: TITLE_WIDTH * scale,
        height: TITLE_HEIGHT * scale,
        backgroundImage: "url(/games/wheel-of-fortune/wheel-title.png)",
        backgroundSize: "100% 100%",
      }}
    >
      <Spinner
        {...(interactive && { type: "button" as const, onClick: () => setSpins((count) => count + 1) })}
        aria-label={interactive ? "Spin the wheel" : undefined}
        className={cn("absolute", interactive && "cursor-pointer transition-transform active:scale-95")}
        style={{
          left: WHEEL_RIGHT_X * scale - emojiWidth,
          top: BASELINE * scale - EMOJI_HEIGHT * emojiScale,
          filter: `drop-shadow(${scale}px ${scale}px 0 #05070a)`,
        }}
      >
        <WheelEmoji spinToken={`title-${spins}`} scale={emojiScale} />
      </Spinner>
    </Wordmark>
  );
}
