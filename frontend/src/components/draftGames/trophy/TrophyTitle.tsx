import { TROPHY_GAME_TITLE } from "../../../data/draftGames";
import { PixelWordmark } from "../PixelWordmark";
import { SpriteStrip, TROPHY_SPRITE } from "./SpriteStrip";

const TROPHY_WORDMARK = {
  image: "/games/trophy-mage/trophy-title.png",
  width: 89,
  height: 18,
  title: TROPHY_GAME_TITLE,
  spriteLabel: "Polish the trophy",
};
const TROPHY_LEFT = 38;
const TROPHY_TOP = 2;

export function TrophyTitle({ scale, interactive = true }: { scale: number; interactive?: boolean }) {
  return (
    <PixelWordmark
      art={TROPHY_WORDMARK}
      scale={scale}
      interactive={interactive}
      spriteStyle={{ left: TROPHY_LEFT * scale, top: TROPHY_TOP * scale }}
      renderSprite={(shines) => <SpriteStrip sheet={TROPHY_SPRITE} scale={scale} restMs={2600} playToken={shines} />}
    />
  );
}
