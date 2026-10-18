import { useState } from "react";

import { WHEEL_GAME_TITLE } from "../../../data/draftGames";
import { WheelEmoji } from "./WheelEmoji";

const TITLE_WIDTH = 110;
const TITLE_HEIGHT = 20;
const WHEEL_RIGHT_X = 51.6;
const BASELINE = 17.2;
const EMOJI_WIDTH = 23;
const EMOJI_HEIGHT = 25;
const EMOJI_SCALE_RATIO = 0.47;

export function WheelTitle({ scale }: { scale: number }) {
  const [spins, setSpins] = useState(0);
  const emojiScale = scale * EMOJI_SCALE_RATIO;
  const emojiWidth = EMOJI_WIDTH * emojiScale;
  return (
    <h1
      aria-label={WHEEL_GAME_TITLE}
      className="relative bg-no-repeat [image-rendering:pixelated]"
      style={{
        width: TITLE_WIDTH * scale,
        height: TITLE_HEIGHT * scale,
        backgroundImage: "url(/games/wheel-of-fortune/wheel-title.png)",
        backgroundSize: "100% 100%",
      }}
    >
      <button
        type="button"
        aria-label="Spin the wheel"
        onClick={() => setSpins((count) => count + 1)}
        className="absolute cursor-pointer transition-transform active:scale-95"
        style={{
          left: WHEEL_RIGHT_X * scale - emojiWidth,
          top: BASELINE * scale - EMOJI_HEIGHT * emojiScale,
          filter: `drop-shadow(${scale}px ${scale}px 0 #05070a)`,
        }}
      >
        <WheelEmoji spinToken={`title-${spins}`} scale={emojiScale} />
      </button>
    </h1>
  );
}
