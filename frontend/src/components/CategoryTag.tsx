import type { Episode, EpisodeCategory } from "../data/episodes";
import { cn } from "../lib/utils";
import { SetGlyph } from "./Brand";

const CATEGORY_STYLE: Record<EpisodeCategory, string> = {
  "Set Review": "bg-teal text-bg",
  Draft: "bg-indigo text-bg",
  Sealed: "bg-blue text-bg",
  Rankings: "bg-purple text-bg",
  Metagame: "bg-gold text-bg",
  Coaching: "bg-pink text-bg",
  Guest: "bg-orange text-bg",
  Evergreen: "bg-green text-bg",
};

export const CATEGORY_COLOR: Record<EpisodeCategory, string> = {
  "Set Review": "text-teal",
  Draft: "text-indigo",
  Sealed: "text-blue",
  Rankings: "text-purple",
  Metagame: "text-gold",
  Coaching: "text-pink",
  Guest: "text-orange",
  Evergreen: "text-green",
};

export function CategoryTag({ category, className }: { category: EpisodeCategory; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block font-display tracking-[0.14em] uppercase text-[12.5px] leading-none px-2 py-1",
        CATEGORY_STYLE[category],
        className,
      )}
    >
      {category}
    </span>
  );
}

export function EpisodeTag({
  episode,
  glyphSize = 20,
  className,
}: {
  episode: Episode;
  glyphSize?: number;
  className?: string;
}) {
  return (
    <span className={cn("flex items-center gap-2 shrink-0", className)}>
      {episode.setCode ? (
        <SetGlyph code={episode.setCode} size={glyphSize} />
      ) : episode.category === "Evergreen" ? (
        <SetGlyph code="EVG" size={glyphSize} />
      ) : null}
      <CategoryTag category={episode.category} />
    </span>
  );
}
