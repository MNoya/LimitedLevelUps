import { WHEEL_GAME_TITLE } from "../../../data/draftGames";
import { PixelWordmark } from "../PixelWordmark";
import { WheelEmoji } from "./WheelEmoji";

const WHEEL_WORDMARK = {
  image: "/games/wheel-of-fortune/wheel-title.png",
  width: 110,
  height: 20,
  title: WHEEL_GAME_TITLE,
  spriteLabel: "Spin the wheel",
};
const WHEEL_RIGHT_X = 51.6;
const BASELINE = 17.2;
const EMOJI_WIDTH = 23;
const EMOJI_HEIGHT = 25;
const EMOJI_SCALE_RATIO = 0.47;

export function WheelTitle({ scale, interactive = true }: { scale: number; interactive?: boolean }) {
  const emojiScale = scale * EMOJI_SCALE_RATIO;
  const spriteStyle = {
    left: WHEEL_RIGHT_X * scale - EMOJI_WIDTH * emojiScale,
    top: BASELINE * scale - EMOJI_HEIGHT * emojiScale,
    filter: `drop-shadow(${scale}px ${scale}px 0 #05070a)`,
  };
  return (
    <PixelWordmark
      art={WHEEL_WORDMARK}
      scale={scale}
      interactive={interactive}
      spriteStyle={spriteStyle}
      renderSprite={(spins) => <WheelEmoji spinToken={`title-${spins}`} scale={emojiScale} />}
    />
  );
}
