import { useState, type ComponentType, type CSSProperties, type ReactNode } from "react";

import { cn } from "../../lib/utils";

export interface WordmarkArt {
  image: string;
  width: number;
  height: number;
  title: string;
  spriteLabel: string;
}

export function PixelWordmark({
  art,
  scale,
  interactive,
  spriteStyle,
  renderSprite,
}: {
  art: WordmarkArt;
  scale: number;
  interactive: boolean;
  spriteStyle: CSSProperties;
  renderSprite: (playToken: number) => ReactNode;
}) {
  const [plays, setPlays] = useState(0);
  const Wordmark = interactive ? "h1" : "span";
  return (
    <Wordmark
      aria-label={art.title}
      className="relative block bg-no-repeat [image-rendering:pixelated]"
      style={{
        width: art.width * scale,
        height: art.height * scale,
        backgroundImage: `url(${art.image})`,
        backgroundSize: "100% 100%",
      }}
    >
      {interactive ? (
        <button
          type="button"
          aria-label={art.spriteLabel}
          onClick={() => setPlays((count) => count + 1)}
          className="absolute cursor-pointer transition-transform active:scale-95"
          style={spriteStyle}
        >
          {renderSprite(plays)}
        </button>
      ) : (
        <span className="absolute" style={spriteStyle}>
          {renderSprite(plays)}
        </span>
      )}
    </Wordmark>
  );
}

export function ResponsiveWordmark({
  wordmark: Wordmark,
  phone,
  desktop,
  short,
  phoneClassName,
}: {
  wordmark: ComponentType<{ scale: number }>;
  phone: number | null;
  desktop: number;
  short: number;
  phoneClassName?: string;
}) {
  return (
    <>
      {phone != null && (
        <div className={cn("sm:hidden", phoneClassName)}>
          <Wordmark scale={phone} />
        </div>
      )}
      <div className="hidden sm:block [@media(max-height:760px)]:hidden">
        <Wordmark scale={desktop} />
      </div>
      <div className="hidden [@media(max-height:760px)]:sm:block">
        <Wordmark scale={short} />
      </div>
    </>
  );
}
