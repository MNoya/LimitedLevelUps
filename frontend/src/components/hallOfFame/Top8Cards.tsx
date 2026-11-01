import { useLayoutEffect, useRef, type RefObject } from "react";
import { useIsMobile } from "../../lib/use-is-mobile";
import { PlayerProfileCard } from "./PlayerProfileCard";
import type { ChampionshipPlayer } from "./useChampionship";

export function Top8Cards({
  players,
  setCode,
  loading,
}: {
  players: ChampionshipPlayer[];
  setCode: string;
  loading: boolean;
}) {
  const isMobile = useIsMobile();
  const boxRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  useZoomGridToFit(boxRef, gridRef, !isMobile);

  const cards = players.map((player) => (
    <PlayerProfileCard key={player.key} player={player} setCode={setCode} loading={loading} />
  ));
  if (isMobile) {
    return <div className="flex flex-col gap-3">{cards}</div>;
  }
  return (
    <div
      ref={boxRef}
      className="flex-1 h-full self-stretch min-h-0 -mr-3 pr-3 md:-mr-6 md:pr-6 flex justify-center items-start themed-scrollbar"
    >
      <div ref={gridRef} className="shrink-0 grid gap-4">
        {cards}
      </div>
    </div>
  );
}

function useZoomGridToFit(boxRef: RefObject<HTMLElement>, gridRef: RefObject<HTMLElement>, enabled: boolean) {
  useLayoutEffect(() => {
    const box = boxRef.current;
    const grid = gridRef.current;
    if (!enabled || !box || !grid) {
      return;
    }
    const cardMinWidth = 420;
    const gap = 16;
    const minReadableScale = 0.8;
    const minWidthFor = (columns: number) => columns * cardMinWidth + (columns - 1) * gap;
    const layoutAt = (columns: number, width: number) => {
      const layoutWidth = Math.max(width, minWidthFor(columns));
      grid.style.zoom = "1";
      grid.style.marginTop = "0";
      grid.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
      grid.style.width = `${layoutWidth}px`;
      return layoutWidth;
    };
    const frame = box.parentElement?.closest("main, .overflow-y-auto") ?? box;
    const heightToFrameBottom = () => {
      const frameBottom = frame.getBoundingClientRect().bottom - parseFloat(getComputedStyle(frame).paddingBottom);
      return frameBottom - box.getBoundingClientRect().top;
    };
    const fit = () => {
      box.style.height = "";
      const width = box.clientWidth - parseFloat(getComputedStyle(box).paddingRight);
      const height = heightToFrameBottom();
      if (width === 0 || height <= 0) {
        return;
      }
      for (const columns of [4, 2]) {
        const layoutWidth = layoutAt(columns, width);
        const naturalHeight = grid.offsetHeight;
        const scale = Math.min(1, width / layoutWidth, height / naturalHeight);
        if (scale >= minReadableScale) {
          box.style.overflowY = "visible";
          grid.style.zoom = scale.toFixed(3);
          const spareHeight = Math.max(0, height - naturalHeight * scale);
          grid.style.marginTop = `${spareHeight / 2 / scale}px`;
          return;
        }
      }
      const scrollColumns = width / minWidthFor(4) >= minReadableScale ? 4 : 2;
      const layoutWidth = layoutAt(scrollColumns, width);
      box.style.overflowY = "auto";
      box.style.height = `${height}px`;
      grid.style.zoom = Math.min(1, width / layoutWidth).toFixed(3);
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(box);
    observer.observe(grid);
    return () => observer.disconnect();
  }, [boxRef, gridRef, enabled]);
}
