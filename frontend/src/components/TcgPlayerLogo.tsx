import { cn } from "../lib/utils";

const SPONSOR_IMG = "/sponsors/tcgplayer-horizontal.png";

export function TcgPlayerLogo({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("block bg-current", className)}
      style={{
        aspectRatio: "3334 / 538",
        WebkitMaskImage: `url(${SPONSOR_IMG})`,
        maskImage: `url(${SPONSOR_IMG})`,
        WebkitMaskSize: "contain",
        maskSize: "contain",
        WebkitMaskRepeat: "no-repeat",
        maskRepeat: "no-repeat",
        WebkitMaskPosition: "center",
        maskPosition: "center",
      }}
    />
  );
}
