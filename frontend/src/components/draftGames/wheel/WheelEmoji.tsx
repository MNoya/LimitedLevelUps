import { useEffect, useRef } from "react";

const FRAMES = 32;
const FRAME_WIDTH = 23;
const FRAME_HEIGHT = 25;
const LAUNCH_TURNS_PER_SECOND = { min: 2, max: 3.2 };
const DRAG_SECONDS = 1.2;
const FRICTION_TURNS_PER_SECOND_SQUARED = 0.052;

export function WheelEmoji({ spinToken, scale = 2 }: { spinToken: string | null; scale?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const restingTurns = useRef(Math.random());

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }
    const showTurns = (turns: number) => {
      const frame = Math.floor(turns * FRAMES) % FRAMES;
      element.style.backgroundPosition = `${-frame * FRAME_WIDTH * scale}px 0`;
    };
    showTurns(restingTurns.current);
    if (!spinToken || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    const { min, max } = LAUNCH_TURNS_PER_SECOND;
    const launch = min + Math.random() * (max - min);
    const frictionSpeed = FRICTION_TURNS_PER_SECOND_SQUARED * DRAG_SECONDS;
    const stopAt = DRAG_SECONDS * Math.log(1 + launch / frictionSpeed);
    const startTurns = restingTurns.current;
    const turnsAt = (t: number) =>
      startTurns + (launch + frictionSpeed) * DRAG_SECONDS * (1 - Math.exp(-t / DRAG_SECONDS)) - frictionSpeed * t;
    const started = performance.now();
    let request = 0;
    const draw = (now: number) => {
      const t = Math.min((now - started) / 1000, stopAt);
      restingTurns.current = turnsAt(t);
      showTurns(restingTurns.current);
      if (t < stopAt) {
        request = requestAnimationFrame(draw);
      }
    };
    request = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(request);
  }, [spinToken, scale]);

  return (
    <span
      ref={ref}
      aria-hidden
      className="block shrink-0 [image-rendering:pixelated]"
      style={{
        width: FRAME_WIDTH * scale,
        height: FRAME_HEIGHT * scale,
        backgroundImage: "url(/games/wheel-of-fortune/wheel-emoji.png)",
        backgroundSize: `${FRAME_WIDTH * FRAMES * scale}px ${FRAME_HEIGHT * scale}px`,
      }}
    />
  );
}
