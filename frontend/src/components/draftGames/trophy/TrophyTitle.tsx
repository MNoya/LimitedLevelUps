import { useState } from "react";

import { TROPHY_MAGE_TITLE } from "../../../data/trophyMage";
import { SpriteStrip, TROPHY_SPRITE } from "./SpriteStrip";

const TITLE_WIDTH = 89;
const TITLE_HEIGHT = 18;
const TROPHY_LEFT = 38;
const TROPHY_TOP = 2;

export function TrophyTitle({ scale, interactive = true }: { scale: number; interactive?: boolean }) {
  const [shines, setShines] = useState(0);
  const trophy = <SpriteStrip sheet={TROPHY_SPRITE} scale={scale} restMs={2600} playToken={shines} />;
  const trophyPosition = { left: TROPHY_LEFT * scale, top: TROPHY_TOP * scale };
  const Wordmark = interactive ? "h1" : "span";
  return (
    <Wordmark
      aria-label={TROPHY_MAGE_TITLE}
      className="relative block bg-no-repeat [image-rendering:pixelated]"
      style={{
        width: TITLE_WIDTH * scale,
        height: TITLE_HEIGHT * scale,
        backgroundImage: "url(/games/trophy-mage/trophy-title.png)",
        backgroundSize: "100% 100%",
      }}
    >
      {interactive ? (
        <button
          type="button"
          aria-label="Polish the trophy"
          onClick={() => setShines((count) => count + 1)}
          className="absolute cursor-pointer transition-transform active:scale-95"
          style={trophyPosition}
        >
          {trophy}
        </button>
      ) : (
        <span className="absolute" style={trophyPosition}>
          {trophy}
        </span>
      )}
    </Wordmark>
  );
}
