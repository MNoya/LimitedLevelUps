import type { CSSProperties } from "react";

import { SetGlyph } from "../../Brand";
import { cn } from "../../../lib/utils";

export function CardBack({ code, index, className }: { code: string | null; index: number; className?: string }) {
  return (
    <span
      className={cn(
        "relative block aspect-[5/7] overflow-hidden rounded-[6%] animate-cardDeal [container-type:inline-size]",
        "bg-[#0b0806] p-[3.5%] shadow-[0_10px_20px_rgba(0,0,0,0.55)]",
        className,
      )}
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <span className="relative block size-full overflow-hidden rounded-[2%]" style={CARD_BACK_FRAME}>
        <CardBackFace />
        <span
          className={cn(
            "pointer-events-none absolute inset-0 translate-x-[-120%]",
            "bg-[linear-gradient(115deg,transparent_30%,rgba(255,255,255,0.3)_45%,transparent_60%)]",
            "group-hover:translate-x-[120%] group-hover:transition-transform group-hover:duration-700",
          )}
        />
        {code && (
          <span className="absolute inset-0 grid place-items-center animate-fadeIn">
            <SetGlyph
              code={code}
              size="50cqw"
              className={cn("drop-shadow-[0_0_1px_#1a120b] drop-shadow-[1px_2px_0_rgba(0,0,0,0.55)]", "text-[#fff1d6]")}
            />
          </span>
        )}
      </span>
    </span>
  );
}

const NOISE_FILTER = [
  "<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'>",
  "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.035' numOctaves='4' seed='4'/>",
  "<feColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.5 0'/></filter>",
  "<rect width='100%' height='100%' filter='url(%23n)'/></svg>",
].join("");
const NOISE = `url("data:image/svg+xml,${NOISE_FILTER}")`;
const CARD_BACK_FRAME: CSSProperties = {
  background: [
    NOISE,
    "radial-gradient(ellipse at 88% 10%, #b3a03a 0%, transparent 42%)",
    "radial-gradient(ellipse at 10% 75%, #2e280c 0%, transparent 55%)",
    "radial-gradient(ellipse at 82% 86%, #7a4e1e 0%, transparent 32%)",
    "linear-gradient(160deg, #5e5419, #403912 60%, #4b3c15)",
  ].join(", "),
  backgroundSize: "70cqw 70cqw, auto, auto, auto, auto",
};
const CARD_BACK_OVAL: CSSProperties = {
  background: [NOISE, "radial-gradient(ellipse at 50% 42%, #b67c3f 0%, #a06a32 60%, #8c5c2b 100%)"].join(", "),
  backgroundSize: "90cqw 90cqw, auto",
  backgroundBlendMode: "soft-light, normal",
};
const CORNER_DOTS = [
  "left-[5%] top-[3.5%]",
  "right-[5%] top-[3.5%]",
  "left-[5%] bottom-[3.5%]",
  "right-[5%] bottom-[3.5%]",
];
function CardBackFace() {
  return (
    <>
      <span className="absolute inset-[2.5%] border border-black/55 shadow-[inset_0_0_0_1px_rgba(214,190,90,0.22)]" />
      {CORNER_DOTS.map((position) => (
        <span
          key={position}
          className={cn(
            "absolute size-[6.5cqw] rounded-full bg-[radial-gradient(circle_at_40%_35%,#ff9a5c,#d2481c_65%,#9c2f10)]",
            "shadow-[0_0_0_1px_rgba(0,0,0,0.45)]",
            position,
          )}
        />
      ))}
      <span
        className={cn(
          "absolute inset-[4.3%_6.5%] rounded-[50%] border-[2.2cqw] border-[#8d8be0]",
          "shadow-[0_0_0_1.5px_#120c07,inset_0_0_0_1px_rgba(0,0,0,0.45)]",
        )}
        style={CARD_BACK_OVAL}
      />
    </>
  );
}
