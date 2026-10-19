import { useEffect, useRef } from "react";

import { cn } from "../../../lib/utils";

export interface SpriteSheet {
  src: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
  fps: number;
}

export const TROPHY_SPRITE: SpriteSheet = {
  src: "/games/trophy-mage/trophy-emoji.png",
  frameWidth: 13,
  frameHeight: 15,
  frames: 24,
  fps: 12,
};

export interface PixelSheet {
  src: string;
  frameWidth: number;
  frameHeight: number;
  frames: number;
}

export const CLEAN_TROPHY_SPRITE: SpriteSheet = { ...TROPHY_SPRITE, src: "/games/trophy-mage/trophy-clean.png" };

export function PixelFrame({
  sheet,
  scale,
  frame = 0,
  className,
}: {
  sheet: PixelSheet;
  scale: number;
  frame?: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn("block shrink-0 [image-rendering:pixelated]", className)}
      style={{
        width: sheet.frameWidth * scale,
        height: sheet.frameHeight * scale,
        backgroundImage: `url(${sheet.src})`,
        backgroundSize: `${sheet.frameWidth * sheet.frames * scale}px ${sheet.frameHeight * scale}px`,
        backgroundPosition: `${-(frame % sheet.frames) * sheet.frameWidth * scale}px 0`,
      }}
    />
  );
}

export function SpriteStrip({
  sheet,
  scale,
  restMs = 0,
  playToken,
  className,
}: {
  sheet: SpriteSheet;
  scale: number;
  restMs?: number;
  playToken?: string | number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }
    const showFrame = (frame: number) => {
      element.style.backgroundPosition = `${-frame * sheet.frameWidth * scale}px 0`;
    };
    showFrame(0);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    const playMs = (sheet.frames * 1000) / sheet.fps;
    const loopMs = playMs + restMs;
    const started = performance.now();
    let request = 0;
    const draw = (now: number) => {
      const elapsed = (now - started) % loopMs;
      showFrame(elapsed < playMs ? Math.floor((elapsed / 1000) * sheet.fps) % sheet.frames : 0);
      request = requestAnimationFrame(draw);
    };
    request = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(request);
  }, [sheet, scale, restMs, playToken]);

  return (
    <span
      ref={ref}
      aria-hidden
      className={cn("block shrink-0 [image-rendering:pixelated]", className)}
      style={{
        width: sheet.frameWidth * scale,
        height: sheet.frameHeight * scale,
        backgroundImage: `url(${sheet.src})`,
        backgroundSize: `${sheet.frameWidth * sheet.frames * scale}px ${sheet.frameHeight * scale}px`,
      }}
    />
  );
}
