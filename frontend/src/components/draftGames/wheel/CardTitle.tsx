import type { ReactNode } from "react";

import { Pips } from "../../ManaPips";
import { CardImage, useCardImageMapContext } from "../../pod/review/ReviewCard";
import { cardLayout } from "../../../data/cardImages";
import { frontFace } from "../../../lib/cardSlug";
import { cn } from "../../../lib/utils";
import type { ArtifactCard } from "../../../types/leaderboard";

const TITLE_ASPECT = "aspect-[432/42]";
const TITLE_FRAME = cn("relative w-full overflow-hidden rounded-[3.8%/40%] bg-surface2", TITLE_ASPECT);
const PILL_COLORS: Record<string, string> = {
  W: "#ece6d2",
  U: "#3f86c8",
  B: "#86888c",
  R: "#c8492f",
  G: "#3e9152",
  M: "#cfa640",
  C: "#9aa3ab",
};

export function CardTitle({ card, className }: { card: ArtifactCard; className?: string }) {
  const frame = titleFrame(card, cardLayout(useCardImageMapContext(), card.n, card.s));
  if (frame === "pill") {
    return <ColorPill card={card} className={className} />;
  }
  if (frame === "sideways") {
    return (
      <div className={cn("flex w-full items-center", TITLE_ASPECT, className)}>
        <div className="relative aspect-[432/32] w-full overflow-hidden rounded-[2.8%/40%] bg-surface2">
          <div
            className={cn(
              "absolute top-0 left-[-8.37%] w-[80.13%] origin-top-left",
              card.type?.includes("Room") ? "mt-[-2.3%]" : "mt-[-4.9%]",
            )}
            style={{ transform: "translateX(139.34%) rotate(90deg)" }}
          >
            <CardImage card={card} />
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className={cn(TITLE_FRAME, className)}>
      <div className="absolute top-0 left-[-4.98%] w-[110.1%]">
        <div className="mt-[-6.28%]">
          <CardImage card={card} />
        </div>
      </div>
    </div>
  );
}

export function TitleSlot({ className, children }: { className?: string; children?: ReactNode }) {
  return <div className={cn("flex w-full items-center px-3", TITLE_ASPECT, className)}>{children}</div>;
}

function titleFrame(card: ArtifactCard, layout: string | undefined): "upright" | "sideways" | "pill" {
  const type = card.type ?? "";
  if (type.includes("Battle")) {
    return "pill";
  }
  if (!card.n?.includes("//")) {
    return "upright";
  }
  if (layout) {
    return layout === "split" ? "sideways" : "upright";
  }
  if (type.includes("Room") || /^(Instant|Sorcery)[^/]* \/\/ (Instant|Sorcery)/.test(type)) {
    return "sideways";
  }
  const facesKnown = type.includes("//");
  const uprightFront = /Creature|Artifact|Adventure|Omen|Saga|Aura/.test(type);
  return facesKnown || uprightFront ? "upright" : "pill";
}

function ColorPill({ card, className }: { card: ArtifactCard; className?: string }) {
  const colors = card.c ?? [];
  const isLand = card.type?.includes("Land") ?? false;
  let base = PILL_COLORS[colors[0] ?? "C"] ?? PILL_COLORS.C;
  if (colors.length > 1) {
    base = PILL_COLORS.M;
  }
  const lightRow = colors.length === 1 && colors[0] === "W";
  const textColor = lightRow ? "text-[#1a1712]" : "text-white [text-shadow:0_0_2px_#000,0_1px_2px_#000]";
  const fill =
    `linear-gradient(180deg, color-mix(in srgb, ${base} 55%, white) 0%, ${base} 38%, ` +
    `color-mix(in srgb, ${base} 85%, black) 62%, color-mix(in srgb, ${base} 65%, black) 100%)`;
  return (
    <div className={cn("w-full rounded-full bg-[#0d0d0f] p-[2px]", TITLE_ASPECT, className)}>
      <div
        className="flex h-full items-center gap-2 rounded-full border border-white/40 pr-1.5 pl-3"
        style={{ background: fill }}
      >
        <span className={cn("truncate font-serif text-[15px] font-bold", textColor)}>{frontFace(card.n ?? "")}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          {!isLand && colors.length > 0 && <Pips colors={colors.join("")} size={16} />}
        </span>
      </div>
    </div>
  );
}
