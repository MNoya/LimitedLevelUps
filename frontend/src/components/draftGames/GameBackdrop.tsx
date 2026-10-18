import { useEffect, useState } from "react";

import { cn } from "../../lib/utils";

export function GameBackdrop({ art, className }: { art: string; className: string }) {
  const headerHeight = useHeaderHeight();
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-x-0 bottom-0 z-0 flex justify-center overflow-hidden"
      style={{ top: headerHeight }}
    >
      <img
        src={art}
        alt=""
        className={cn(
          "size-full object-cover blur-[0.5px]",
          "sm:w-auto sm:max-w-none sm:[mask-image:linear-gradient(to_right,transparent,black_20%,black_80%,transparent)]",
          "animate-[artDrift_60s_ease-in-out_infinite_alternate]",
          className,
        )}
      />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,#0a0c10_95%)]" />
    </div>
  );
}

function useHeaderHeight(): number {
  const [height, setHeight] = useState(0);
  useEffect(() => {
    const header = document.querySelector("header");
    if (!header) {
      return;
    }
    const observer = new ResizeObserver(() => setHeight(header.getBoundingClientRect().height));
    observer.observe(header);
    return () => observer.disconnect();
  }, []);
  return height;
}
