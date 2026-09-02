import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { PageShell } from "../components/PageShell";
import { ChamferCta, CUT_CORNER_CHAMFER } from "../components/ChamferCta";
import { DiscordIcon } from "../components/BrandIcons";
import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight, ExternalLink, Music, Play, Trophy } from "../components/Icons";
import { EpisodeTag } from "../components/CategoryTag";
import { EpisodeThumbnail } from "../components/EpisodeThumbnail";
import { EpisodeEmbed, episodePlayability } from "../components/PlayableThumbnail";
import { PlayBadge } from "../components/PlayBadge";
import { Pips } from "../components/ManaPips";
import { highlightEventLabel } from "../components/pod/EventLabel";
import { GiRoundTable } from "react-icons/gi";
import { SiPatreon, SiTwitch, SiYoutube } from "react-icons/si";
import type { IconType } from "react-icons";
import { Tooltip } from "../components/Tooltip";
import { EpisodeLinkTooltip, episodeTitleHref } from "../components/EpisodeLink";
import { AAvatar, fmtPts, SetGlyph, setGlyphCode } from "../components/Brand";
import { TcgPlayerLogo } from "../components/TcgPlayerLogo";
import { TierSetDropdown } from "../components/TierSetDropdown";
import { boardModeFor, type BoardMode } from "../components/LeaderboardTable";
import {
  CardModal,
  CardPreview,
  comparePagerOrder,
  neighborCardUrls,
  PREVIEW_EXTRAS_H,
  PREVIEW_GAP,
  PREVIEW_RATIO,
  PREVIEW_W,
  type PreviewAnchor,
} from "../components/TierGrid";
import {
  useAvailableFormats,
  useFormatLeaderboard,
  useLeaderboard,
  useRecentEpisodes,
  usePodEvents,
  useSets,
} from "../data/hooks";
import { buildTierListSets, resolveTierList, tierColor, TIER_ORDER, useTierList, type TierCard } from "../data/tierList";
import { ACTIVE_SET_CODE } from "../data/constants";
import { FMT_COLORS, shortFormat } from "../data/format-display";
import { FORMAT_OPTIONS } from "../data/filters";
import { HOST, SITE_LINKS } from "../data/site";
import { cleanPodEventName, leaderboardPath, playerPath, relativeAge, relativeAgeShort } from "../data/utils";
import type { Episode } from "../data/episodes";
import { formatDurationShort } from "../data/episodes";
import type { LeaderboardRow, PodEventSummary, SetSummary } from "../types/leaderboard";
import { cn } from "../lib/utils";

export function HomePage() {
  const { data: sets } = useSets();
  const setCode = sets?.find((s) => s.isActive)?.code ?? ACTIVE_SET_CODE;
  const { data: episodes, isLoading: episodesLoading } = useRecentEpisodes();

  return (
    <PageShell subtitle="HOME" fill>
      <div
        className={cn(
          "p-4 lg:p-5 grid gap-4 grid-cols-1 lg:h-full",
          "lg:grid-cols-[minmax(300px,360px)_minmax(0,1fr)_clamp(300px,22vw,340px)] lg:[grid-template-rows:minmax(0,1fr)]",
        )}
      >
        <div className="contents lg:flex lg:flex-col lg:gap-4 lg:min-h-0 lg:h-full">
          <IdentityPanel />
          <TierPanel />
        </div>

        <EpisodesHero
          episodes={episodes?.filter((ep) => !ep.isShort).slice(0, 4) ?? []}
          loading={episodesLoading}
          thumbnailsPending={false}
        />

        <div className="contents lg:flex lg:flex-col lg:gap-4 lg:min-h-0 lg:h-full">
          <LeaderboardPanel setCode={setCode} />
          <PodDraftsPanel setCode={setCode} />
        </div>
      </div>
    </PageShell>
  );
}

function Panel({
  title,
  to,
  corner,
  headerCenter,
  action,
  actionBorder = false,
  headerBorder = false,
  linkBody = false,
  className,
  bodyClassName,
  children,
}: {
  title: string;
  to: string;
  corner?: ReactNode;
  headerCenter?: ReactNode;
  action?: string;
  actionBorder?: boolean;
  headerBorder?: boolean;
  linkBody?: boolean;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "group bg-surface border border-border rounded-xl p-4 flex flex-col min-h-0",
        linkBody && "relative",
        className,
      )}
    >
      {linkBody ? (
        <Link
          to={to}
          aria-label={action ?? title}
          className="peer/cta absolute inset-0 z-0 rounded-xl transition-colors hover:bg-green/[0.03]"
        />
      ) : null}
      <div
        className={cn(
          "flex items-center gap-3 shrink-0",
          headerBorder ? "-mx-4 px-4 pb-3 border-b border-border" : "mb-3",
        )}
      >
        <Link
          to={to}
          className="font-display text-text text-[20px] tracking-[0.05em] no-underline hover:text-green transition-colors shrink-0 whitespace-nowrap"
        >
          {title}
        </Link>
        <div className="flex-1 min-w-0 flex justify-center">{headerCenter}</div>
        {typeof corner === "string" ? (
          <span className="mono text-[10px] tracking-[0.16em] text-muted uppercase shrink-0">{corner}</span>
        ) : (
          corner ?? null
        )}
      </div>
      <div className={cn("flex-1 min-h-0 flex flex-col", bodyClassName)}>{children}</div>
      {action ? (
        <Link
          to={to}
          className={cn(
            "relative z-0 -mx-4 -mb-4 shrink-0 flex w-[calc(100%+2rem)] items-center justify-end gap-1.5 rounded-b-xl px-4 py-2.5 font-display tracking-[0.08em] text-[15px] text-green no-underline transition-colors hover:bg-green/5 hover:text-green-2",
            linkBody && "peer-hover/cta:bg-green/5 peer-hover/cta:text-green-2",
            actionBorder && "border-t border-border",
          )}
        >
          {action} <ArrowRight size={15} />
        </Link>
      ) : null}
    </section>
  );
}

function IdentityPanel() {
  const socials: Array<{ label: string; tooltip: string; url: string; Icon?: IconType; logo?: string; sponsored?: boolean }> = [
    { label: "YouTube", tooltip: "Watch on YouTube", url: SITE_LINKS.youtube, Icon: SiYoutube },
    { label: "Twitch", tooltip: "Stream on Twitch", url: SITE_LINKS.twitch, Icon: SiTwitch },
    { label: "Patreon", tooltip: "Support on Patreon", url: SITE_LINKS.patreon, Icon: SiPatreon },
    { label: "TCGplayer", tooltip: "Sponsored by TCGplayer", url: SITE_LINKS.tcgplayer, logo: "/sponsors/tcgplayer-horizontal.png", sponsored: true },
  ];
  const offerings = ["Weekly episodes", "Set review tier lists", "Strategy discussion", "Community events"];
  const [aboutOpen, setAboutOpen] = useState(readAboutOpen);

  const toggleAbout = () => {
    setAboutOpen((open) => {
      const next = !open;
      window.localStorage.setItem(ABOUT_OPEN_KEY, next ? "1" : "0");
      return next;
    });
  };
  return (
    <section className="order-1 lg:order-none bg-surface border border-border rounded-xl p-4 flex flex-col gap-3 shrink-0">
      <h2 className="font-display text-text text-[20px] tracking-[0.05em]">
        <button
          type="button"
          onClick={toggleAbout}
          aria-expanded={aboutOpen}
          aria-label={aboutOpen ? "Collapse about the community" : "Expand about the community"}
          className="flex w-full items-center justify-between gap-3 text-left lg:pointer-events-none"
        >
          About the Community
          <ChevronDown size={22} className={cn("shrink-0 text-muted transition-transform lg:hidden", !aboutOpen && "-rotate-90")} />
        </button>
      </h2>
      <div className={cn("flex flex-col gap-3", !aboutOpen && "max-lg:hidden")}>
        <p className="text-subtle text-[13px] leading-[1.5] text-center">
          Everything you need to get better at <span className="text-green">Limited Magic</span>
        </p>
        <ul className="grid grid-cols-[auto_auto] gap-x-6 gap-y-1.5 self-center">
          {offerings.map((item) => (
            <li key={item} className="flex items-center gap-2.5 text-subtle text-[13px] leading-tight">
              <span className="w-[5px] h-[5px] shrink-0 bg-green rotate-45" />
              {item}
            </li>
          ))}
        </ul>
        <p className="text-subtle text-[13px] leading-[1.5] text-center">
          Join the <span className="text-green">Discord</span> to connect with other Limited players, draft with us and climb the leaderboard!
        </p>
        <ChamferCta
          label="JOIN THE DISCHORD"
          href={SITE_LINKS.discord}
          target="_blank"
          grow
          className="self-center mt-0.5"
          icon={
            <span className="inline-flex items-center justify-center w-[22px] h-[22px] rounded-full bg-bg text-white shrink-0">
              <DiscordIcon size={14} />
            </span>
          }
        />
        <p className="mono text-[12px] tracking-[0.04em] text-subtle text-center">
          Hosted by {HOST.name}{" "}
          <a
            href={`https://x.com/${HOST.handle}`}
            target="_blank"
            rel="noreferrer"
            className="text-subtle italic no-underline hover:text-green transition-colors"
          >
            @{HOST.handle}
          </a>
        </p>
        <div className="grid grid-cols-2 gap-2">
          {socials.map(({ label, tooltip, url, Icon, logo, sponsored }) => (
            <Tooltip
              key={label}
              label={
                <span className="inline-flex items-center gap-1.5">
                  {tooltip}
                  <ExternalLink size={12} />
                </span>
              }
              side="bottom"
            >
              <a
                href={url}
                target="_blank"
                rel={sponsored ? "sponsored noreferrer" : "noreferrer"}
                aria-label={tooltip}
                className="font-display uppercase text-[15px] tracking-[0.1em] flex items-center justify-center gap-2 bg-surface2 py-2 text-subtle no-underline hover:bg-border hover:text-green transition-colors"
                style={{ clipPath: CUT_CORNER_CHAMFER }}
              >
                {logo ? (
                  <TcgPlayerLogo className="h-[15px]" />
                ) : (
                  <>
                    {Icon ? <Icon className="text-[15px]" /> : null}
                    {label}
                  </>
                )}
              </a>
            </Tooltip>
          ))}
        </div>
      </div>
    </section>
  );
}

const ABOUT_OPEN_KEY = "llu:community-about-open";

function readAboutOpen(): boolean {
  if (typeof window === "undefined") {
    return true;
  }
  return window.localStorage.getItem(ABOUT_OPEN_KEY) !== "0";
}

const CARDS_PER_PAGE = 5;

function TierPanel() {
  const { data: sets } = useSets();
  const tierSets = useMemo(() => buildTierListSets(sets), [sets]);
  const [picked, setPicked] = useState<string | undefined>();
  const current = picked ?? tierSets[0]?.code ?? ACTIVE_SET_CODE;
  const setMeta = tierSets.find((s) => s.code === current);
  const { graders, effectiveUid } = resolveTierList(current);
  const { data } = useTierList(effectiveUid, graders);
  const rows = useMemo(() => sampleTiers(data?.filter((card) => card.inclusion_type === "Main Set")), [data]);
  const allCards = useMemo(() => rows.flatMap((row) => row.cards).sort(comparePagerOrder), [rows]);

  const [hover, setHover] = useState<{ card: TierCard; anchor: PreviewAnchor } | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedIndex = allCards.findIndex((c) => c.card_id === selectedId);
  const selectedCard = selectedIndex >= 0 ? allCards[selectedIndex] : null;

  const showPreview = (el: HTMLElement, card: TierCard) => {
    const rect = el.getBoundingClientRect();
    const previewH = PREVIEW_W * PREVIEW_RATIO + PREVIEW_EXTRAS_H;
    const centerY = rect.top + rect.height / 2;
    const top = Math.min(Math.max(centerY - previewH / 2, 8), Math.max(window.innerHeight - previewH - 8, 8));
    const onRight = rect.right + PREVIEW_GAP + PREVIEW_W <= window.innerWidth - 8;
    const left = onRight ? rect.right + PREVIEW_GAP : rect.left - PREVIEW_GAP - PREVIEW_W;
    const arrowTop = Math.min(Math.max(centerY - top, 14), previewH - 14);
    setHover({ card, anchor: { left, top, onRight, arrowTop } });
  };

  const tierDropdown = (
    <TierSetDropdown
      sets={tierSets}
      activeCode={current}
      glyphCode={setMeta ? setGlyphCode(setMeta) : current}
      label={current}
      isMobile={false}
      compact
      triggerClassName="w-[92px]"
      openOnHover
      loading={!sets}
      onChange={setPicked}
    />
  );

  return (
    <Panel title="SET REVIEW" to={`/tier-list/${current}`} corner={tierDropdown} action="Full Tier List Review" className="order-3 lg:order-none flex-1">
      {rows.length ? (
        <div className="-mx-4 flex-1 min-h-0 flex flex-col border-y border-border">
          {rows.map((row) => (
            <TierCardRow
              key={row.letter}
              row={row}
              onPreview={showPreview}
              onLeave={() => setHover(null)}
              onSelect={(card) => {
                setHover(null);
                setSelectedId(card.card_id);
              }}
            />
          ))}
        </div>
      ) : (
        <Placeholder lines={4} />
      )}

      {hover ? createPortal(<CardPreview card={hover.card} anchor={hover.anchor} />, document.body) : null}
      {selectedCard
        ? createPortal(
            <CardModal
              card={selectedCard}
              onClose={() => setSelectedId(null)}
              onPrev={selectedIndex > 0 ? () => setSelectedId(allCards[selectedIndex - 1].card_id) : undefined}
              onNext={
                selectedIndex < allCards.length - 1
                  ? () => setSelectedId(allCards[selectedIndex + 1].card_id)
                  : undefined
              }
              position={`${selectedIndex + 1} / ${allCards.length}`}
              neighborUrls={neighborCardUrls(allCards, selectedIndex)}
            />,
            document.body,
          )
        : null}
    </Panel>
  );
}

const CARD_ASPECT = "745 / 1040";

function TierCardRow({
  row,
  onPreview,
  onLeave,
  onSelect,
}: {
  row: { letter: string; color: string; cards: TierCard[] };
  onPreview: (el: HTMLElement, card: TierCard) => void;
  onLeave: () => void;
  onSelect: (card: TierCard) => void;
}) {
  const clipRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });

  const syncEdges = () => {
    const el = clipRef.current;
    if (!el) {
      return;
    }
    const maxScroll = el.scrollWidth - el.clientWidth;
    setEdges({ left: el.scrollLeft > 1, right: el.scrollLeft < maxScroll - 1 });
  };

  useEffect(() => {
    const el = clipRef.current;
    if (!el) {
      return;
    }
    syncEdges();
    const observer = new ResizeObserver(syncEdges);
    observer.observe(el);
    return () => observer.disconnect();
  }, [row.cards.length]);

  const page = (direction: 1 | -1) => {
    const el = clipRef.current;
    if (!el) {
      return;
    }
    const card = el.querySelector<HTMLElement>("[data-card]");
    const stride = card ? card.offsetWidth : el.clientWidth / CARDS_PER_PAGE;
    el.scrollBy({ left: stride * CARDS_PER_PAGE * direction, behavior: "smooth" });
  };

  return (
    <div className="group/row relative h-[84px] lg:h-auto lg:flex-1 min-h-0 flex items-stretch border-t border-border first:border-t-0">
      <span
        className="font-display w-10 shrink-0 flex items-center justify-center text-[17px] text-text bg-[#0e1218] border-r border-border"
        style={{ borderLeft: `5px solid ${row.color}` }}
      >
        {row.letter}
      </span>
      <div
        ref={clipRef}
        onScroll={syncEdges}
        className="flex-1 min-h-0 overflow-x-auto no-scrollbar flex items-center scroll-smooth py-0.5"
      >
        <div className="flex h-full items-center w-max shrink-0">
          {row.cards.map((card) => (
            <div key={card.card_id} data-card className="h-full shrink-0 pr-1.5 flex items-center">
              <LazyCardImg card={card} rootRef={clipRef} onPreview={onPreview} onLeave={onLeave} onSelect={onSelect} />
            </div>
          ))}
        </div>
      </div>
      <PageChevron direction={-1} show={edges.left} onClick={() => page(-1)} />
      <PageChevron direction={1} show={edges.right} onClick={() => page(1)} />
    </div>
  );
}

function PageChevron({ direction, show, onClick }: { direction: 1 | -1; show: boolean; onClick: () => void }) {
  const Icon = direction === 1 ? ChevronRight : ChevronLeft;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={direction === 1 ? "Show later cards" : "Show earlier cards"}
      className={cn(
        "absolute inset-y-0 z-10 flex w-12 items-center px-1.5 transition-opacity",
        direction === 1 ? "right-0 justify-end bg-gradient-to-l" : "left-10 justify-start bg-gradient-to-r",
        "from-bg/90 to-transparent",
        show ? "opacity-100" : "pointer-events-none opacity-0",
      )}
    >
      <span className="flex h-6 w-6 items-center justify-center rounded-full border border-border2 bg-surface2/90 text-text transition-colors hover:border-green hover:text-green">
        <Icon size={14} />
      </span>
    </button>
  );
}

function LazyCardImg({
  card,
  rootRef,
  onPreview,
  onLeave,
  onSelect,
}: {
  card: TierCard;
  rootRef: RefObject<HTMLDivElement>;
  onPreview: (el: HTMLElement, card: TierCard) => void;
  onLeave: () => void;
  onSelect: (card: TierCard) => void;
}) {
  const ref = useRef<HTMLImageElement>(null);
  const [load, setLoad] = useState(false);
  useEffect(() => {
    if (load) {
      return;
    }
    const el = ref.current;
    if (!el) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setLoad(true);
          observer.disconnect();
        }
      },
      { root: rootRef.current, rootMargin: "0px 300px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [load, rootRef]);

  return (
    <img
      ref={ref}
      src={load ? card.url : undefined}
      alt={card.name}
      decoding="async"
      onMouseEnter={(e) => onPreview(e.currentTarget, card)}
      onMouseLeave={onLeave}
      onClick={() => onSelect(card)}
      className="h-full w-auto rounded-[2px] border border-black bg-surface2 cursor-pointer"
      style={{ aspectRatio: CARD_ASPECT }}
    />
  );
}

function EpisodesHero({
  episodes,
  loading,
  thumbnailsPending,
}: {
  episodes: Episode[];
  loading: boolean;
  thumbnailsPending: boolean;
}) {
  return (
    <Panel
      title="LATEST CONTENT"
      to="/episodes"
      corner={
        <Link
          to="/episodes"
          className="shrink-0 flex items-center gap-1.5 font-display tracking-[0.08em] text-[15px] text-green no-underline transition-colors hover:text-green-2"
        >
          View All Episodes <ArrowRight size={15} />
        </Link>
      }
      className="order-2 lg:order-none lg:h-full"
    >
      {loading ? (
        <>
          <div className="lg:hidden flex flex-col gap-4">
            <div className="aspect-video bg-surface2 border border-border rounded-lg animate-pulse" />
            <div className="grid grid-cols-2 gap-4">
              {Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="aspect-video bg-surface2 border border-border rounded-lg animate-pulse" />
              ))}
            </div>
          </div>
          <div className="hidden lg:grid grid-cols-1 xl:grid-cols-2 gap-4 flex-1 min-h-0">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className={cn("bg-surface2 border border-border rounded-lg animate-pulse", i >= 2 && "hidden xl:block")}
              />
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="lg:hidden flex flex-col gap-4">
            {episodes[0] ? <HeroEpisodeCard episode={episodes[0]} thumbnailPending={thumbnailsPending} /> : null}
            {episodes.length > 1 ? (
              <div className="grid grid-cols-2 gap-4">
                {episodes.slice(1, 3).map((ep) => (
                  <HeroEpisodeCard key={ep.id} episode={ep} compact thumbnailPending={thumbnailsPending} />
                ))}
              </div>
            ) : null}
          </div>
          <div className="hidden lg:grid grid-cols-1 xl:grid-cols-2 gap-4 flex-1 min-h-0">
            {episodes.map((ep, i) => (
              <HeroEpisodeCard
                key={ep.id}
                episode={ep}
                thumbnailPending={thumbnailsPending}
                className={i >= 2 ? "hidden xl:flex" : undefined}
              />
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}

const episodeShortTitle = (title: string) => title.split("|")[0].trim();

function HeroEpisodeCard({
  episode,
  className,
  compact = false,
  thumbnailPending = false,
}: {
  episode: Episode;
  className?: string;
  compact?: boolean;
  thumbnailPending?: boolean;
}) {
  const [playing, setPlaying] = useState(false);
  const { canPlayAudio, playable } = episodePlayability(episode);
  const play = () => setPlaying(true);
  const titleHref = episodeTitleHref(episode);

  const thumbnail = (
    <>
      <EpisodeThumbnail
        src={episode.image}
        pending={thumbnailPending}
        className="transition-transform duration-300 group-hover/ep:scale-[1.07]"
      />
      {!compact ? (
        <span className="absolute bottom-2 left-2 text-[10px] font-medium text-white bg-black/60 rounded px-1.5 py-0.5">
          {relativeAge(episode.pubDate)}
        </span>
      ) : null}
      {!compact && episode.durationLabel ? (
        <span className="absolute bottom-2 right-2 text-[10px] font-medium text-white bg-black/60 rounded px-1.5 py-0.5">
          {episode.durationLabel}
        </span>
      ) : null}
      <span className="absolute inset-0 flex items-center justify-center bg-bg/30 opacity-0 transition-opacity group-hover/ep:opacity-100">
        <PlayBadge>{canPlayAudio ? <Music size={28} /> : <Play size={32} />}</PlayBadge>
      </span>
    </>
  );

  return (
    <div
      className={cn(
        "group/ep flex flex-col min-h-0 border border-border rounded-lg overflow-hidden bg-surface2 transition-[border-color,box-shadow] duration-150 hover:border-green hover:shadow-[0_0_8px_1px_rgba(46,232,92,0.32)]",
        className,
      )}
    >
      <div className="relative z-10 aspect-video lg:aspect-auto lg:flex-1 lg:min-h-0 overflow-hidden bg-surface">
        {playing ? (
          <EpisodeEmbed episode={episode} thumbnailPending={thumbnailPending} />
        ) : playable ? (
          <button
            type="button"
            onClick={play}
            aria-label={`Play ${episode.title}`}
            className="absolute inset-0 block w-full cursor-pointer"
          >
            {thumbnail}
          </button>
        ) : (
          <a href={episode.link} target="_blank" rel="noreferrer" className="absolute inset-0 block w-full">
            {thumbnail}
          </a>
        )}
      </div>
      {compact ? (
        <div className="shrink-0 flex items-center justify-between gap-1.5 pl-2">
          <span className="flex-1 min-w-0 text-[10px] font-medium text-white truncate">
            {relativeAgeShort(episode.pubDate)}
            {episode.durationSeconds ? ` · ${formatDurationShort(episode.durationSeconds)}` : ""}
          </span>
          <EpisodeTag episode={episode} glyphSize={14} className="gap-1" />
        </div>
      ) : (
        <EpisodeLinkTooltip episode={episode}>
          <a
            href={titleHref}
            target="_blank"
            rel="noreferrer"
            className="p-3 shrink-0 flex items-start justify-between gap-2 no-underline group-hover/ep:text-green"
          >
            <h3 className="flex-1 min-w-0 font-body text-text text-[16px] font-medium leading-snug line-clamp-2 transition-colors group-hover/ep:text-green">
              {episodeShortTitle(episode.title)}
            </h3>
            <EpisodeTag episode={episode} className="mt-0.5" />
          </a>
        </EpisodeLinkTooltip>
      )}
    </div>
  );
}

const LB_ROW_HEIGHT = 28;
const LB_CYCLE_MS = 5000;

type BoardSnapshot = { key: string; setCode: string; mode: BoardMode; rows: LeaderboardRow[] };

function LeaderboardPanel({ setCode }: { setCode: string }) {
  const { data: sets } = useSets();
  const lbSets = useMemo(() => setsNewestFirst(sets), [sets]);
  const [pickedSet, setPickedSet] = useState<string>();
  const set = pickedSet ?? setCode;
  const setMeta = lbSets.find((s) => s.code === set);

  const { data: availableFormats } = useAvailableFormats(set);
  const formats = useMemo(() => orderFormats(availableFormats), [availableFormats]);

  const [index, setIndex] = useState(0);
  const [manual, setManual] = useState<string | null>(null);
  const pausedRef = useRef(false);
  const manualRef = useRef(false);
  useEffect(() => {
    if (formats.length <= 1) {
      return;
    }
    const id = setInterval(() => {
      if (!pausedRef.current && !manualRef.current) {
        setIndex((i) => i + 1);
      }
    }, LB_CYCLE_MS);
    return () => clearInterval(id);
  }, [formats.length]);

  useEffect(() => {
    setManual(null);
    manualRef.current = false;
    setIndex(0);
  }, [set]);

  const pickFormat = (format: string) => {
    manualRef.current = true;
    setManual(format);
  };

  const current = manual ?? formats[index % formats.length] ?? "ALL";
  const isAll = current === "ALL";
  const allBoard = useLeaderboard(isAll ? set : undefined);
  const formatBoard = useFormatLeaderboard(isAll ? undefined : set, isAll ? undefined : current);
  const data = isAll ? allBoard.data : formatBoard.data;

  const listRef = useRef<HTMLDivElement>(null);
  const [maxRows, setMaxRows] = useState(7);
  useLayoutEffect(() => {
    const el = listRef.current;
    if (!el) {
      return;
    }
    const measure = () => setMaxRows(Math.max(3, Math.floor(el.clientHeight / LB_ROW_HEIGHT)));
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    measure();
    return () => observer.disconnect();
  }, []);

  const liveKey = `${set}-${current}`;
  const liveRows = data?.slice(0, maxRows) ?? [];
  const mode = boardModeFor(current);
  const to = isAll ? leaderboardPath(set) : `${leaderboardPath(set)}?format=${encodeURIComponent(current)}`;

  const [layers, setLayers] = useState<{ front: BoardSnapshot; back: BoardSnapshot | null }>(() => ({
    front: { key: liveKey, setCode: set, mode, rows: liveRows },
    back: null,
  }));
  const shownKeyRef = useRef(liveKey);
  useEffect(() => {
    if (liveRows.length === 0) {
      return;
    }
    const snapshot: BoardSnapshot = { key: liveKey, setCode: set, mode, rows: liveRows };
    const changed = shownKeyRef.current !== liveKey;
    shownKeyRef.current = liveKey;
    setLayers((prev) => ({ front: snapshot, back: changed ? prev.front : prev.back }));
    if (changed) {
      const timer = setTimeout(() => setLayers((prev) => ({ ...prev, back: null })), 240);
      return () => clearTimeout(timer);
    }
  }, [liveKey, data, maxRows]);

  const setDropdown = (
    <TierSetDropdown
      sets={lbSets}
      activeCode={set}
      glyphCode={setMeta ? setGlyphCode(setMeta) : set}
      label={set}
      isMobile={false}
      compact
      menuAlign="right"
      triggerClassName="w-[92px]"
      loading={!sets}
      onChange={setPickedSet}
    />
  );

  return (
    <Panel
      title="LEADERBOARD"
      to={to}
      corner={
        <div className="flex items-center gap-2 shrink-0">
          {setDropdown}
          <FormatDropdown formats={formats} current={current} onPick={pickFormat} />
        </div>
      }
      action="View Full leaderboard"
      actionBorder
      headerBorder
      className="order-4 lg:order-none flex-1"
    >
      <div
        ref={listRef}
        className="relative -mx-4 min-h-0 overflow-hidden h-[224px] lg:h-auto lg:flex-1"
        onMouseEnter={() => (pausedRef.current = true)}
        onMouseLeave={() => (pausedRef.current = false)}
      >
        {layers.front.rows.length === 0 && !layers.back ? (
          <Placeholder lines={5} />
        ) : (
          <>
            {layers.back ? (
              <div key={layers.back.key} className="absolute inset-0 flex h-full flex-col animate-fadeOut">
                {layers.back.rows.map((row) => (
                  <LeaderboardMiniRow key={row.slug} row={row} setCode={layers.back!.setCode} mode={layers.back!.mode} />
                ))}
                {emptyRowKeys(maxRows - layers.back.rows.length).map((key) => (
                  <LeaderboardEmptyRow key={key} />
                ))}
              </div>
            ) : null}
            <div key={layers.front.key} className="absolute inset-0 flex h-full flex-col animate-fadeIn">
              {layers.front.rows.map((row) => (
                <LeaderboardMiniRow key={row.slug} row={row} setCode={layers.front.setCode} mode={layers.front.mode} />
              ))}
              {emptyRowKeys(maxRows - layers.front.rows.length).map((key) => (
                <LeaderboardEmptyRow key={key} />
              ))}
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

const formatColor = (format: string) => FMT_COLORS[format] ?? "#5c8aff";

function FormatDropdown({
  formats,
  current,
  onPick,
}: {
  formats: string[];
  current: string;
  onPick: (format: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) {
      return;
    }
    const onClickOutside = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={cn(
          "relative flex h-7 w-[92px] items-center justify-center border px-2 font-display tracking-[0.06em] text-[18px] leading-none transition-colors",
          open ? "border-green text-green" : "border-border2 text-text hover:border-green hover:text-green",
        )}
      >
        <span key={current} className="animate-fadeIn truncate">{shortFormat(current)}</span>
        <ChevronDown
          size={14}
          strokeWidth={2.5}
          className={cn("absolute right-1.5 transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <div className="absolute right-0 top-[calc(100%+6px)] z-30 w-max overflow-hidden border border-border2 bg-surface shadow-xl">
          {formats.map((format) => (
            <button
              key={format}
              type="button"
              onClick={() => {
                onPick(format);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-2.5 border-l-2 px-3.5 py-2 text-left font-display tracking-[0.06em] text-[15px] uppercase transition-colors",
                format === current
                  ? "border-green bg-surface2 text-green"
                  : "border-transparent text-subtle hover:bg-surface2",
              )}
            >
              {format !== "ALL" && (
                <span className="h-2 w-2 shrink-0" style={{ background: formatColor(format) }} />
              )}
              {formatLabel(format)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function LeaderboardMiniRow({ row, setCode, mode }: { row: LeaderboardRow; setCode: string; mode: BoardMode }) {
  return (
    <Link
      to={playerPath(row.slug, setCode)}
      className="group/row flex flex-1 items-center gap-2.5 px-4 border-t border-border no-underline text-text transition-colors first:border-t-0 hover:bg-surface2"
      style={{ minHeight: LB_ROW_HEIGHT }}
    >
      <span className="mono w-5 shrink-0 text-center text-[12px] text-muted">{row.rank}</span>
      <AAvatar displayName={row.displayName} avatarUrl={row.avatarUrl} size={22} />
      <span className="truncate font-display text-[15px] leading-none tracking-[0.04em] transition-colors group-hover/row:text-green">
        {row.displayName.toUpperCase()}
      </span>
      <MiniRowMetric row={row} mode={mode} />
    </Link>
  );
}

function MiniRowMetric({ row, mode }: { row: LeaderboardRow; mode: BoardMode }) {
  if (mode === "direct") {
    const boxes = row.boxes ?? 0;
    return (
      <span className="ml-auto flex items-center gap-1 font-display text-[15px] leading-none tracking-[0.02em] tabular-nums">
        <span className="text-[11px]" aria-hidden="true">📦</span>
        <span className={boxes === 0 ? "text-dim" : "text-text"}>{boxes}</span>
      </span>
    );
  }
  if (mode === "lcq") {
    const earnings = row.earnings ?? 0;
    return (
      <span className="ml-auto font-display text-[15px] leading-none tracking-[0.02em] tabular-nums text-green">
        {earnings > 0 ? `$${earnings / 1000}K` : "—"}
      </span>
    );
  }
  return (
    <span className="ml-auto font-display text-[15px] leading-none tracking-[0.02em] tabular-nums text-green">
      {Number.isFinite(row.score) ? fmtPts(row.score) : "—"}
    </span>
  );
}

function emptyRowKeys(count: number): string[] {
  return Array.from({ length: Math.max(0, count) }, (_, i) => `empty-${i}`);
}

function LeaderboardEmptyRow() {
  return (
    <div
      className="flex flex-1 items-center border-t border-border first:border-t-0"
      style={{ minHeight: LB_ROW_HEIGHT }}
      aria-hidden
    />
  );
}

const FORMAT_LABEL_BY_VALUE = new Map(FORMAT_OPTIONS.map((o) => [o.value, o.label]));

function formatLabel(format: string): string {
  return FORMAT_LABEL_BY_VALUE.get(format) ?? shortFormat(format);
}

function orderFormats(available: string[] | undefined): string[] {
  const present = new Set(available ?? []);
  const ordered = FORMAT_OPTIONS.map((o) => o.value).filter((v) => v === "ALL" || present.has(v));
  const extras = (available ?? []).filter((v) => !ordered.includes(v));
  return [...ordered, ...extras];
}

function setsNewestFirst(sets: SetSummary[] | undefined): SetSummary[] {
  return [...(sets ?? [])].sort((a, b) => b.startDate.localeCompare(a.startDate));
}

function PodDraftsPanel({ setCode }: { setCode: string }) {
  const { data: sets } = useSets();
  const setMeta = sets?.find((s) => s.code === setCode);
  const { data } = usePodEvents(setCode);
  const entries = useMemo(() => splitPods(data), [data]);

  const setDisplay = (
    <span className="flex items-center gap-2 min-w-0">
      <SetGlyph code={setMeta ? setGlyphCode(setMeta) : setCode} size={18} />
      <span className="truncate font-display tracking-[0.06em] text-[17px] text-text">{setCode}</span>
    </span>
  );

  return (
    <Panel title="POD DRAFTS" to="/pods" corner={setDisplay} action="Check Draft Replays" actionBorder headerBorder className="order-5 lg:order-none">
      {entries.length ? (
        <div className="flex flex-col -mx-4">
          {entries.map((entry) => (
            <PodRow key={entry.event.slug} entry={entry} />
          ))}
        </div>
      ) : (
        <Placeholder lines={3} />
      )}
    </Panel>
  );
}

function PodRow({ entry }: { entry: PodEntry }) {
  const { event, upcoming } = entry;
  const championName = event.championDisplayName?.replace(/#.*$/, "");
  const title = cleanPodEventName(event.name, event.setCode);
  const { month, day } = podMonthDay(event);

  let sub: ReactNode;
  if (upcoming) {
    sub = <span className="truncate">{podWhenLabel(event)}</span>;
  } else if (championName) {
    sub = (
      <>
        <Trophy size={13} strokeWidth={2} className="text-gold" />
        <span className="truncate text-[12px] font-bold text-text">{championName}</span>
        {event.championRecord ? <span className="shrink-0">{event.championRecord}</span> : null}
        {event.championDeckColors ? <Pips colors={event.championDeckColors} size={11} /> : null}
      </>
    );
  } else {
    sub = <span className="truncate">{event.participantCount} drafters</span>;
  }

  const rowClassName =
    "group/pod flex items-center gap-2.5 px-4 py-2 border-t border-border first:border-t-0 no-underline transition-colors hover:bg-green/5";

  const content = (
    <>
      <span
        className={cn(
          "flex h-[40px] w-[48px] shrink-0 flex-col items-center justify-center rounded font-display leading-none",
          upcoming
            ? "border border-green/30 bg-green/10 text-green text-[11px] tracking-[0.12em]"
            : "border border-border bg-surface2",
        )}
      >
        {upcoming ? (
          "NEXT"
        ) : (
          <>
            <span className="text-[9px] tracking-[0.12em] text-muted">{month}</span>
            <span className="mt-0.5 text-[17px] tabular-nums text-text">{day}</span>
          </>
        )}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium text-text truncate">{highlightEventLabel(title)}</div>
        <div className="mono text-[12px] text-muted flex items-center gap-1.5 min-w-0">{sub}</div>
      </div>
      {upcoming ? (
        <PodCountdown target={podStartMs(event)} />
      ) : (
        <GiRoundTable size={18} className="shrink-0 text-muted transition-colors group-hover/pod:text-green" />
      )}
    </>
  );

  if (upcoming) {
    const href = SITE_LINKS.discord;
    return (
      <Tooltip label="View event on Discord" side="left">
        <a href={href} target="_blank" rel="noreferrer" className={rowClassName}>
          {content}
        </a>
      </Tooltip>
    );
  }
  const winnerQuery = event.championDisplayName
    ? `?player=${encodeURIComponent(event.championDisplayName)}`
    : "";
  return (
    <Tooltip label="View seats, logs & replays" side="left">
      <Link to={`/pods/${event.slug}${winnerQuery}`} className={rowClassName}>
        {content}
      </Link>
    </Tooltip>
  );
}

function podMonthDay(event: PodEventSummary): { month: string; day: number } {
  const stamp = event.eventTime || event.eventDate;
  const date = new Date(stamp.length <= 10 ? `${stamp}T12:00:00` : stamp);
  return {
    month: date.toLocaleString("en-US", { month: "short" }).toUpperCase(),
    day: date.getDate(),
  };
}

function Placeholder({ lines }: { lines: number }) {
  return (
    <div className="flex-1 flex flex-col gap-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-5 bg-surface2 rounded animate-pulse" />
      ))}
    </div>
  );
}

type PodEntry = { event: PodEventSummary; upcoming: boolean };

function splitPods(events: PodEventSummary[] | undefined): PodEntry[] {
  if (!events?.length) {
    return [];
  }
  const now = Date.now();
  const future = events
    .filter((e) => !e.isFinalized && podStartMs(e) >= now)
    .sort((a, b) => podStartMs(a) - podStartMs(b));
  const past = events.filter((e) => !future.includes(e));
  const entries: PodEntry[] = [];
  if (future[0]) {
    entries.push({ event: future[0], upcoming: true });
  }
  for (const event of past) {
    if (entries.length >= 3) {
      break;
    }
    entries.push({ event, upcoming: false });
  }
  return entries;
}

function PodCountdown({ target }: { target: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const remaining = target - now;
  return (
    <span className="mono shrink-0 rounded border border-border bg-surface2 px-2 py-1 text-[11px] tracking-[0.08em] tabular-nums text-subtle">
      {remaining <= 0 ? "LIVE" : formatCountdown(remaining)}
    </span>
  );
}

function formatCountdown(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const pad = (n: number) => String(n).padStart(2, "0");
  const clock = `${pad(Math.floor((totalSeconds % 86400) / 3600))}:${pad(Math.floor((totalSeconds % 3600) / 60))}:${pad(totalSeconds % 60)}`;
  return days > 0 ? `${days}d ${clock}` : clock;
}

function podStartMs(event: PodEventSummary): number {
  const stamp = event.eventTime || event.eventDate;
  return new Date(stamp.length <= 10 ? `${stamp}T12:00:00` : stamp).getTime();
}

function podWhenLabel(event: PodEventSummary): string {
  const stamp = event.eventTime || event.eventDate;
  const date = new Date(stamp.length <= 10 ? `${stamp}T12:00:00` : stamp);
  if (Number.isNaN(date.getTime())) {
    return event.eventDate;
  }
  const hasTime = Boolean(event.eventTime);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    ...(hasTime ? { hour: "numeric", minute: "2-digit" } : {}),
  });
}

const TIER_LETTERS = ["A", "B", "C", "D"] as const;

function sampleTiers(cards: TierCard[] | undefined): Array<{ letter: string; color: string; cards: TierCard[] }> {
  if (!cards?.length) {
    return [];
  }
  const orderIndex = new Map(TIER_ORDER.map((tier, i) => [tier, i]));
  const rows: Array<{ letter: string; color: string; cards: TierCard[] }> = [];
  for (const letter of TIER_LETTERS) {
    const inGrade = cards.filter((card) => card.tier?.[0] === letter && orderIndex.has(card.tier));
    inGrade.sort((a, b) => {
      const rankDiff = (orderIndex.get(a.tier) ?? 99) - (orderIndex.get(b.tier) ?? 99);
      if (rankDiff !== 0) {
        return rankDiff;
      }
      return (a.sort_key ?? 9999) - (b.sort_key ?? 9999);
    });
    if (inGrade.length) {
      rows.push({ letter, color: tierColor(letter), cards: inGrade });
    }
  }
  return rows;
}
