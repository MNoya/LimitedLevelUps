import type { Episode } from "../data/episodes";
import { EpisodeTag } from "./CategoryTag";
import { EpisodeLinkTooltip, episodeTitleHref } from "./EpisodeLink";
import { PlayableThumbnail } from "./PlayableThumbnail";
import { cn } from "../lib/utils";

export function EpisodeCard({
  episode,
  thumbnailPending = false,
  audioMode = false,
  expanded = false,
  colStart,
  rowStart,
  onPlayingChange,
}: {
  episode: Episode;
  thumbnailPending?: boolean;
  audioMode?: boolean;
  expanded?: boolean;
  colStart?: number;
  rowStart?: number;
  onPlayingChange?: (playing: boolean) => void;
}) {
  const meta = [episode.publishedLabel.toUpperCase(), episode.number ? `EP ${episode.number}` : null]
    .filter(Boolean)
    .join(" · ");
  const titleHref = episodeTitleHref(episode, audioMode);
  const placement = colStart && rowStart
    ? { gridColumn: `${colStart} / span 2`, gridRow: `${rowStart} / span 2` }
    : undefined;

  return (
    <div
      className={cn("group flex flex-col", expanded && "sm:h-full")}
      style={placement}
    >
      <PlayableThumbnail
        episode={episode}
        thumbnailPending={thumbnailPending}
        aspect={expanded ? "aspect-video sm:grow" : "aspect-video"}
        audioMode={audioMode}
        playing={expanded}
        onPlayingChange={onPlayingChange}
      />
      <EpisodeLinkTooltip episode={episode} audioMode={audioMode}>
        <a href={titleHref} target="_blank" rel="noreferrer" className="block shrink-0 mt-3 no-underline">
          <div className="flex items-center justify-between gap-2">
            <span className="mono text-[11px] tracking-[0.12em] text-muted">{meta}</span>
            <EpisodeTag episode={episode} />
          </div>
          <span className="block font-body text-text text-[15px] md:text-[16px] font-medium leading-snug mt-1.5 min-h-[2.75rem] line-clamp-2 transition-colors group-hover:text-green">
            {episode.title}
          </span>
        </a>
      </EpisodeLinkTooltip>
    </div>
  );
}
