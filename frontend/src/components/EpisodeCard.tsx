import { Link } from "react-router-dom";
import type { Episode } from "../data/episodes";
import { EpisodeTag } from "./CategoryTag";
import { EpisodeLinkTooltip, episodeTitleHref } from "./EpisodeLink";
import { PlayableThumbnail } from "./PlayableThumbnail";

export function EpisodeCard({
  episode,
  thumbnailPending = false,
  audioMode = false,
  detailBase = "/episodes",
}: {
  episode: Episode;
  thumbnailPending?: boolean;
  audioMode?: boolean;
  detailBase?: string;
}) {
  const internalHref = episode.slug ? `${detailBase}/${episode.slug}` : null;
  const titleHref = episodeTitleHref(episode, audioMode);

  return (
    <div className="group flex flex-col">
      <PlayableThumbnail
        episode={episode}
        thumbnailPending={thumbnailPending}
        aspect="aspect-video"
        audioMode={audioMode}
        linkTo={internalHref ?? undefined}
      />
      {internalHref ? (
        <Link to={internalHref} className="block shrink-0 mt-3 no-underline">
          <TitleBlock episode={episode} />
        </Link>
      ) : (
        <EpisodeLinkTooltip episode={episode} audioMode={audioMode}>
          <a href={titleHref} target="_blank" rel="noreferrer" className="block shrink-0 mt-3 no-underline">
            <TitleBlock episode={episode} />
          </a>
        </EpisodeLinkTooltip>
      )}
    </div>
  );
}

export function EpisodeMeta({ episode }: { episode: Episode }) {
  return (
    <span className="flex gap-x-3 font-num text-[11px] tracking-[0.06em] text-muted">
      <span>{episode.publishedLabel.toUpperCase()}</span>
      {episode.number ? <span>EP {episode.number}</span> : null}
    </span>
  );
}

function TitleBlock({ episode }: { episode: Episode }) {
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <EpisodeMeta episode={episode} />
        <EpisodeTag episode={episode} />
      </div>
      <span className="block font-body text-text text-[15px] md:text-[16px] font-medium leading-snug mt-1.5 line-clamp-2 transition-colors group-hover:text-green sm:min-h-[2.75rem]">
        {episode.title}
      </span>
    </>
  );
}
